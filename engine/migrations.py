"""状态机版本化与迁移器：让老书在数据模型演进后依然能被新引擎打开。

设计契约：
- 版本戳：`state/state_schema.json`（不带点，确保随快照一起备份/回滚，新旧格式永远配套）。
- 版本判定：版本文件缺失 = 遗留格式（version 0，即未引入版本化之前的 3.3 时代产物）；
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
# 统一按注册表重算（ 修复：此前在第 27 行提前求值，后注册的迁移不会抬高版本号）。
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


#---------------------------------------------------------------------------
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
# v1 → v2：全局 null 闸门兼容清洗（ P2-8）
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


# ---------------------------------------------------------------------------
# v2 → v3：引入不可逆事实台账 (locked 表)
# ---------------------------------------------------------------------------
def _migrate_v2_to_v3(data: dict[str, dict]) -> tuple[dict[str, dict], list[str]]:
    """v2 → v3：引入不可逆事实台账 (locked 表)。老书若缺失自动创建空表。"""
    from . import state as state_mod

    notes: list[str] = []
    if "locked" not in data or not isinstance(data.get("locked"), dict):
        data["locked"] = state_mod.defaults_for("locked")
        notes.append("初始化第七表 locked.json（空表，配额 15 条）")
    for key in state_mod.STATE_KEYS:
        if key in data and isinstance(data[key], dict):
            cleaned = _strip_dropped(
                _normalize(data[key], state_mod._schema(key), key, notes))
            data[key] = cleaned
    return data, notes


MIGRATIONS[2] = _migrate_v2_to_v3


# ---------------------------------------------------------------------------
# v3 → v4：引入角色认知台账 (cognition 表) 与主线里程碑 (milestones)
# ---------------------------------------------------------------------------
def _migrate_v3_to_v4(data: dict[str, dict]) -> tuple[dict[str, dict], list[str]]:
    """v3 → v4：引入角色认知台账 (cognition 表) 与主线里程碑。老书若缺失自动创建空表/默认字段。"""
    from . import state as state_mod

    notes: list[str] = []
    if "cognition" not in data or not isinstance(data.get("cognition"), dict):
        data["cognition"] = state_mod.defaults_for("cognition")
        notes.append("初始化第八表 cognition.json（角色动态认知真值表）")

    if "timeline" in data and isinstance(data["timeline"], dict):
        if "milestones" not in data["timeline"]:
            data["timeline"]["milestones"] = []
            notes.append("timeline 补充 milestones 阶段里程碑航标清单")

    for key in state_mod.STATE_KEYS:
        if key in data and isinstance(data[key], dict):
            cleaned = _strip_dropped(
                _normalize(data[key], state_mod._schema(key), key, notes))
            data[key] = cleaned
    return data, notes


MIGRATIONS[3] = _migrate_v3_to_v4


# ---------------------------------------------------------------------------
# v4 → v5：对象化加法（派生表 + 事件 EVT 编号）
# ---------------------------------------------------------------------------
def _migrate_v4_to_v5(data: dict[str, dict]) -> tuple[dict[str, dict], list[str]]:
    """v4 → v5：新增派生表 derived.json；为无 id 事件分配 EVT 编号。

    只做结构补齐，不捏造事实：EVT 编号按既有 events 数组顺序分配；
    其余新字段全 Optional，老数据天然通过新闸门；末尾沿惯例全表清洗。
    """
    from . import state as state_mod

    notes: list[str] = []
    if "derived" not in data or not isinstance(data.get("derived"), dict):
        data["derived"] = state_mod.defaults_for("derived")
        notes.append("初始化第九表 derived.json（派生缓存；下次 sync 自动 seal）")
    tl = data.get("timeline")
    if isinstance(tl, dict):
        events = tl.get("events") or []
        maxn = 0
        for e in events:
            eid = str((e or {}).get("id", ""))
            if eid.startswith("EVT-") and eid[4:].isdigit():
                maxn = max(maxn, int(eid[4:]))
        n_new = 0
        for e in events:
            if isinstance(e, dict) and not e.get("id"):
                maxn += 1
                e["id"] = f"EVT-{maxn:03d}"
                n_new += 1
        if n_new:
            notes.append(f"编年史 {n_new} 条事件补 EVT 编号（按序分配）")
    for key in state_mod.STATE_KEYS:
        if key in data and isinstance(data[key], dict):
            cleaned = _strip_dropped(
                _normalize(data[key], state_mod._schema(key), key, notes))
            data[key] = cleaned
    return data, notes


MIGRATIONS[4] = _migrate_v4_to_v5


def _migrate_v5_to_v6(data: dict[str, dict]) -> tuple[dict[str, dict], list[str]]:
    """v5 → v6：entities 按 kind 物理拆为 persons/items/factions/places 四表。

    - 路由：type 归一（中文→英文、缺省→other）后按 state.TYPE_TO_TABLE；
    - 未知 type（外部手改脏数据）：兜底 persons + 记账，不丢条目；
    - entities.json 文件本身由 ensure 环节改名 .v5bak（此处只管数据）。
    若 kind 表与 legacy 并存（正常路径不会），以 legacy 拆分结果为准。
    """
    from . import state as state_mod

    notes: list[str] = []
    legacy = data.pop("entities", {}) or {}
    entries = legacy.get("entries", []) or []
    if not isinstance(entries, list):
        raise ValueError("entities.json 结构损坏（entries 非数组），请回滚快照后人工修复")
    n_alias = n_unknown = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        raw_t = e.get("type")
        canon = state_mod.canonical_entity_type(raw_t)
        if canon is None:
            n_unknown += 1
        elif isinstance(raw_t, str) and raw_t.strip() in state_mod.TYPE_ALIASES:
            n_alias += 1
    split = state_mod.split_entities_entries(entries)
    for k in state_mod.KIND_TABLES:
        data[k] = {"entries": split[k]}
    notes.append("entities {} 条按 kind 拆表：{}".format(
        len(entries),
        "、".join(f"{k}×{len(split[k])}" for k in state_mod.KIND_TABLES)))
    if n_alias:
        notes.append(f"{n_alias} 条中文 type 已归一为法定枚举")
    if n_unknown:
        notes.append(f"{n_unknown} 条未知 type 兜底归入 persons（脏数据，请复核）")
    return data, notes


MIGRATIONS[5] = _migrate_v5_to_v6

# 全部注册完成后统一重算当前版本（= 最高迁移版本 + 1）
CURRENT_STATE_VERSION = max(MIGRATIONS, default=0) + 1


# ---------------------------------------------------------------------------
# 主入口：确保状态机处于当前版本（load_state 的懒触发钩子）
# ---------------------------------------------------------------------------
def ensure_state_version(book: Path) -> dict:
    book = Path(book)
    sd = book / "state"
    key = common.norm_path_key(sd)
    from . import state as state_mod
    state_files = [sd / f"{k}.json" for k in state_mod.STATE_KEYS]
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
        _leg = sd / "entities.json"
        if _leg.is_file():
            raw["entities"] = common.load_json(_leg)  # legacy 单表：供 v5→v6 迁移消费

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
            state_mod.save_state(book, k, d, source="migration")
        if v <= 5:
            # v6 拆表：entities.json 功成身退，改名留档（引擎不再读取，人可查）
            _old_ent = sd / "entities.json"
            if _old_ent.is_file():
                _old_ent.rename(sd / "entities.json.v5bak")
                notes.append("entities.json 已改名 entities.json.v5bak（留档备查）")
        # 原实现整表重写版本戳，迁移前 {created_at, version} 里的 created_at
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
