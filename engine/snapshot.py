"""快照 / 回滚 / manifest 完整性校验。

- 快照范围 = state/ 顶层的 `*.json` / `*.md` + `.applied_operations.json`（幂等登记簿随状态一起走，
  否则回滚后重放旧提案会被误判"已应用"）；inbox（processed/failed 审计）永不被快照或回滚触碰。
- manifest.json 记录每个文件的 SHA-256；回滚前逐文件验证，损坏即拒绝——静默用坏数据覆盖现场是旧工程
  明令禁止的行为，这里同样禁止。
- 快照与回滚都必须持 state 锁：并发 sync 进行中打快照会得到撕裂快照。
"""
from __future__ import annotations

import datetime
import hashlib
import re
import shutil
from pathlib import Path

from . import common, state

SNAPSHOT_DIR_NAME = "snapshots"
MANIFEST_NAME = "manifest.json"


def snapshots_root(book: Path) -> Path:
    return state.state_dir(book) / SNAPSHOT_DIR_NAME


def _state_files(book: Path) -> list[Path]:
    sd = state.state_dir(book)
    out = []
    for p in sorted(sd.iterdir()):
        if not p.is_file():
            continue
        if p.name in {".state.lock", ".engine.lock", MANIFEST_NAME}:
            continue
        if p.suffix in (".json", ".md") and (not p.name.startswith(".") or p.name == state.MARKER_NAME):
            out.append(p)
    return out


def _clean_name(name: str) -> str:
    clean = re.sub(r"[^\w\u4e00-\u9fff.-]", "_", (name or "").strip())
    if not clean or clean in {".", ".."} or ".." in clean or clean.startswith("."):
        raise ValueError(f"快照名称非法: {name!r}")
    return clean


def _manifest_of(folder: Path) -> dict:
    files = {}
    for f in sorted(folder.iterdir()):
        if f.is_file() and f.name != MANIFEST_NAME:
            files[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return {"version": 1, "files": files, "hash": common.canonical_json_hash(files)}


def create_snapshot(book: Path, snapshot_name: str) -> tuple[bool, str]:
    """持锁复制快照 + 写 manifest。返回 (ok, 消息/快照目录名)。"""
    name = _clean_name(snapshot_name)
    sd = state.state_dir(book)
    if not sd.is_dir():
        return False, f"状态目录不存在: {sd}"
    with common.file_lock(sd, name=".state.lock"):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        folder = snapshots_root(book) / f"{ts}_{name}"
        if folder.exists():
            return False, "快照目录冲突（微秒级时间戳下理论上不该发生）"
        folder.mkdir(parents=True, exist_ok=False)
        copied = []
        for f in _state_files(book):
            shutil.copy2(f, folder / f.name)
            copied.append(f.name)
        common.dump_json(folder / MANIFEST_NAME, _manifest_of(folder))
    return True, folder.name


def list_snapshots(book: Path) -> list[str]:
    root = snapshots_root(book)
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())


def _verify_manifest(folder: Path) -> tuple[bool, str]:
    mpath = folder / MANIFEST_NAME
    if not mpath.exists():
        return True, "manifest 缺失：按未校验快照处理（旧快照兼容）"
    try:
        manifest = common.load_json(mpath)
    except (ValueError, OSError) as exc:
        return False, f"manifest 解析失败，拒绝回滚: {exc}"
    bad = []
    for fname, sha in (manifest.get("files") or {}).items():
        f = folder / fname
        if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != sha:
            bad.append(fname)
    if bad:
        return False, f"快照完整性校验失败（损坏/缺失: {', '.join(bad[:5])}），拒绝回滚"
    return True, "manifest 校验通过"


def rollback_snapshot(book: Path, target: str) -> tuple[bool, str, str]:
    """回滚到匹配 target 的最新快照。返回 (ok, 消息, 已回滚快照目录名)。

    回滚前把当前 state 顶层文件备份为 pre_rollback_<ts> 快照，本身也可再回滚回去。
    """
    sd = state.state_dir(book)
    root = snapshots_root(book)
    if not root.is_dir():
        return False, "没有找到任何快照目录", ""

    def strip_ts(n: str) -> str:
        m = re.match(r"^\d{8}_\d{6}_(.+)$", n)
        return m.group(1) if m else n

    # pre_rollback_* 备份同样是合法回滚目标（docstring：本身也可再回滚回去）——
    # 排除它们会造成"snapshot list 看得见、rollback 却找不到"的自相矛盾。
    all_dirs = [d for d in root.iterdir() if d.is_dir()]
    exact = [d for d in all_dirs if strip_ts(d.name) == target]
    matched = exact or [d for d in all_dirs if target in d.name]
    if not matched:
        return False, f"未找到匹配 '{target}' 的快照", ""
    chosen = sorted(matched, reverse=True)[0]
    note = (f"模糊匹配到 {len(matched)} 个，自动选最新: {chosen.name}"
            if not exact and len(matched) > 1 else "")

    ok, msg = _verify_manifest(chosen)
    if not ok:
        return False, msg, ""
    # 完整性第二道：manifest 只保证"列出的文件没坏"，不保证六表齐全——
    # 残缺快照一旦回滚，缺的那张表会被当"回滚点不存在"直接删除，状态机当场残废。
    missing = [f"{k}.json" for k in state.STATE_KEYS if not (chosen / f"{k}.json").is_file()]
    if missing:
        return False, f"快照缺少状态文件 {'、'.join(missing)}，拒绝回滚", ""

    with common.file_lock(sd, name=".state.lock"):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_dir = root / f"pre_rollback_{ts}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        for f in _state_files(book):
            shutil.copy2(f, backup_dir / f.name)
        common.dump_json(backup_dir / MANIFEST_NAME, _manifest_of(backup_dir))
        restored = []
        restored_names = set()
        for f in sorted(chosen.iterdir()):
            if f.is_file() and f.name != MANIFEST_NAME:
                shutil.copy2(f, sd / f.name)
                restored.append(f.name)
                restored_names.add(f.name)
        # 清理快照点之后新增的顶层状态文件（不在快照 = 回滚点不存在，保留会与旧现场冲突）。
        for f in list(sd.iterdir()):
            if not f.is_file() or f.name in restored_names:
                continue
            if f.name in {".state.lock", ".engine.lock", MANIFEST_NAME}:
                continue
            if f.name.startswith(".") and f.name != state.MARKER_NAME:
                continue
            if f.suffix in (".json", ".md"):
                f.unlink()
    lines = [f"已回滚至快照 {chosen.name}（恢复 {len(restored)} 个文件）",
             f"当前状态已自动备份为 pre_rollback_{ts}"]
    if note:
        lines.append(note)
    if msg != "manifest 校验通过":
        lines.append(msg)
    return True, "；".join(lines), chosen.name


def chapter_of_snapshot(name: str) -> int | None:
    """从快照名提取基准章号（ch_007_done / …ch_007… 均可）。"""
    m = re.search(r"ch[_-]?0*(\d+)", name or "")
    return int(m.group(1)) if m else None
