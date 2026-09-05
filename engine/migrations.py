"""状态机版本化与迁移器：让老书在数据模型演进后依然能被新引擎打开。

设计契约：
- 版本戳：`state/state_schema.json`（不带点，确保随快照一起备份/回滚，新旧格式永远配套）。
- 版本判定：版本文件缺失 = 遗留格式（version 0，即未引入版本化之前的 3.1 时代产物）；
  版本高于引擎支持值 = 抛错要求升级引擎（防新数据被旧引擎误改）。
- 迁移时机：`state.load_state` 入口处懒触发（`ensure_state_version`），首次读取即迁移，
  全程不打印到 stdout（避免污染 --json 消费方），审计写 `state/migrations.log`（JSONL）。
- 安全序：先拍快照 `pre_migration_v<N>` → 内存迁移 → 闸门预验 → 全部通过才落盘 →
  写版本戳。任何一步失败都不改动任何文件，报错中给出快照回滚出口。
- 迁移边界：只修「结构」（未知键、显式 null、可从键重算的数值），**绝不捏造事实**；
  修不了的事实级损坏（如编号不合模式）如实抛错，交由人/Agent 修复后重试。
"""
from __future__ import annotations

import contextlib
import datetime
import json
from pathlib import Path
from typing import Any, Callable

from . import common

# 迁移注册表：{起始版本: 迁移函数}；函数签名 (data: dict[str, dict]) -> (data, notes)
# 引擎升级、数据模型演进时，在此追加下一级迁移函数；CURRENT_STATE_VERSION 在文件末尾
# 统一按注册表重算（QA 修复：此前在第 27 行提前求值，后注册的迁移不会抬高版本号）。
MIGRATIONS: dict[int, Callable[[dict[str, dict]], tuple[dict[str, dict], list[str]]]] = {}

VERSION_FILE = "state_schema.json"
LOG_FILE = "migrations.log"
LEGACY_VERSION = 0

# 进程内缓存：{规范化 state 目录: 已确认版本}，避免每次 load_state 重复读版本文件
_ENSURED: dict[str, int] = {}


def version_path(book: Path) -> Path:
    return Path(book) / "state" / VERSION_FILE


def read_version(book: Path) -> int:
    """读状态机版本；文件缺失按遗留格式（0）处理。损坏按 0 处理并在迁移中重建。"""
    try:
        data = common.load_json(version_path(book), default={})
    except ValueError:
        return LEGACY_VERSION
    v = data.get("version") if isinstance(data, dict) else None
    return v if isinstance(v, int) and v >= 0 else LEGACY_VERSION


def _log(book: Path, entry: dict) -> None:
    log_path = Path(book) / "state" / LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 结构清洗器：与生成 schema 协同遍历数据，修「键形状」不碰「事实」
# ---------------------------------------------------------------------------
def _allows_null(schema: dict) -> bool:
    if not isinstance(schema, dict):
        return True
    if "anyOf" in schema:
        return any(b == {"type": "null"} or b.get("type") == "null"
                   for b in schema["anyOf"] if isinstance(b, dict))
    return schema.get("type") == "null"


def _normalize(value: Any, schema: dict, path: str, notes: list[str]) -> Any:
    """按 schema 清洗：additionalProperties=false 处裁掉未知键；schema 不允许 null
    的位置丢弃 None 值键；其余原样保留（事实级内容绝不改动）。"""
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        ap = schema.get("additionalProperties", True)
        out = {}
        for k, v in value.items():
            if k in props:
                out[k] = _normalize(v, props[k], f"{path}.{k}", notes)
            elif isinstance(ap, dict):
                out[k] = _normalize(v, ap, f"{path}.{k}", notes)
            elif ap is False:
                notes.append(f"{path}: 裁掉未知字段 {k}")
            else:
                out[k] = v
        return out
    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            return [_normalize(v, items, f"{path}[{i}]", notes)
                    for i, v in enumerate(value)]
        return value
    if value is None and not _allows_null(schema):
        notes.append(f"{path}: 丢弃显式 null（键视为缺席）")
        return _DROP
    return value


_DROP = object()


def _strip_dropped(node: Any) -> Any:
    """把 _normalize 标记的 _DROP 从 dict/list 中剔除（后处理，避免边遍历边改）。"""
    if isinstance(node, dict):
        return {k: _strip_dropped(v) for k, v in node.items() if v is not _DROP}
    if isinstance(node, list):
        return [_strip_dropped(v) for v in node if v is not _DROP]
    return node


# ---------------------------------------------------------------------------
# v0（3.1 时代遗留格式）→ v1：严格闸门兼容清洗
# ---------------------------------------------------------------------------
def _migrate_v0_to_v1(data: dict[str, dict]) -> tuple[dict[str, dict], list[str]]:
    from . import state as state_mod  # 延迟导入避免循环依赖

    notes: list[str] = []
    # 1) synopsis.chapters[*].num：非正整数 → 从键重算（ch_007 → 7）；键也无法解析则丢弃该条
    syn = data.get("synopsis") or {}
    chapters = syn.get("chapters")
    if isinstance(chapters, dict):
        fixed = {}
        for c, cp in chapters.items():
            if isinstance(cp, dict) and not (isinstance(cp.get("num"), int)
                                             and not isinstance(cp.get("num"), bool)
                                             and cp["num"] >= 1):
                n = state_mod._chapter_num(str(c)) or 0
                if n >= 1:
                    cp["num"] = n
                    notes.append(f"synopsis.chapters[{c}].num 由键重算 → {n}")
                else:
                    notes.append(f"synopsis.chapters[{c}] num 无法修复且键非法，已丢弃")
                    continue
            fixed[c] = cp
        syn["chapters"] = fixed

    # 2) 各节按生成 schema 清洗（裁未知键 / 丢显式 null）
    for key in ("current", "entities", "lines", "timeline", "ledger", "synopsis"):
        if key in data and isinstance(data[key], dict):
            cleaned = _strip_dropped(
                _normalize(data[key], state_mod._schema(key), key, notes))
            data[key] = cleaned
    return data, notes


MIGRATIONS[LEGACY_VERSION] = _migrate_v0_to_v1


# ---------------------------------------------------------------------------
# v1 → v2：全局 null 闸门兼容清洗（QA P2-8）
# ---------------------------------------------------------------------------
def _migrate_v1_to_v2(data: dict[str, dict]) -> tuple[dict[str, dict], list[str]]:
    """v2 闸门对所有 Optional 字段拒绝显式 null；存量数据按当前 schema 清洗
    （丢弃 null 键 = 视为缺席，绝不触碰事实内容）。"""
    from . import state as state_mod

    notes: list[str] = []
    for key in ("current", "entities", "lines", "timeline", "ledger", "synopsis"):
        if key in data and isinstance(data[key], dict):
            cleaned = _strip_dropped(
                _normalize(data[key], state_mod._schema(key), key, notes))
            data[key] = cleaned
    return data, notes


MIGRATIONS[1] = _migrate_v1_to_v2

# 全部注册完成后统一重算当前版本（= 最高迁移版本 + 1）
CURRENT_STATE_VERSION = max(MIGRATIONS, default=0) + 1


# ---------------------------------------------------------------------------
# 主入口：确保状态机处于当前版本（load_state 的懒触发钩子）
# ---------------------------------------------------------------------------
def ensure_state_version(book: Path) -> dict:
    book = Path(book)
    sd = book / "state"
    key = common.norm_path_key(sd)
    state_files = [sd / f"{k}.json" for k in
                   ("current", "entities", "lines", "timeline", "ledger", "synopsis")]
    if not any(p.is_file() for p in state_files):
        return {"migrated": False}  # 未初始化的书：交给 load_state 的缺失报错，不播种
    cached = _ENSURED.get(key)
    if cached == CURRENT_STATE_VERSION:
        return {"migrated": False}

    v = read_version(book)
    if v == CURRENT_STATE_VERSION:
        _ENSURED[key] = v
        return {"migrated": False}

    from . import snapshot, state as state_mod
    from . import validator

    with common.file_lock(sd, name=".state.lock"):
        v = read_version(book)  # 双检：锁内再读一次，防并发抢先迁移
        if v == CURRENT_STATE_VERSION:
            _ENSURED[key] = v
            return {"migrated": False}
        if v > CURRENT_STATE_VERSION:
            raise ValueError(
                f"状态机版本 v{v} 高于当前引擎支持的 v{CURRENT_STATE_VERSION}（请升级 novel-studio 后再打开本书）")

        raw: dict[str, dict] = {}
        for k in state_mod.STATE_KEYS:
            p = sd / f"{k}.json"
            if p.is_file():
                raw[k] = common.load_json(p)

        ok, snap_name = snapshot.create_snapshot(book, f"pre_migration_v{v}")
        if not ok:
            raise ValueError(f"迁移前快照创建失败，已中止迁移（详情: {snap_name}）")

        notes: list[str] = []
        cur = v
        try:
            while cur < CURRENT_STATE_VERSION:
                step = MIGRATIONS.get(cur)
                if step is None:
                    raise ValueError(f"缺少 v{cur} → v{cur + 1} 的迁移函数（引擎缺陷，请反馈）")
                raw, step_notes = step(raw)
                notes.extend(step_notes)
                cur += 1
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"迁移执行异常（数据未改动，可回滚快照 {snap_name}）: {exc}") from exc

        # 闸门预验：迁移结果必须全部通过（否则不落盘）
        gate_errors = []
        for k, d in raw.items():
            gate_errors.extend(validator.validate(d, state_mod._schema(k)))
        if gate_errors:
            raise ValueError(
                "迁移后数据仍未通过结构闸门（事实级损坏需人工修复；"
                f"可回滚快照 {snap_name}）: " + "; ".join(gate_errors[:5]))

        for k, d in raw.items():
            state_mod.save_state(book, k, d)
        # QA P3-7：原实现整表重写版本戳，迁移前 {created_at, version} 里的 created_at
        # 被丢掉，变成 {from_version, migrated_at, version}——建档时间这个不可再生的
        # 事实就此消失。现保留既有键，只更新版本相关字段。
        _prev_stamp = common.load_json(version_path(book), default={}) or {}
        _stamp = dict(_prev_stamp)
        _stamp.update({
            "version": CURRENT_STATE_VERSION,
            "migrated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "from_version": v,
        })
        common.dump_json(version_path(book), _stamp)
        _log(book, {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                    "from": v, "to": CURRENT_STATE_VERSION,
                    "snapshot": snap_name, "notes": notes})
        _ENSURED[key] = CURRENT_STATE_VERSION
        return {"migrated": True, "from": v, "to": CURRENT_STATE_VERSION,
                "snapshot": snap_name, "notes": notes}
