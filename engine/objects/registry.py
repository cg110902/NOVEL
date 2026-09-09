"""对象注册表：id / 法定名 / 别名三键统一寻址（派生索引，不落盘）。

解决 entities 双键寻址散在 state._merge_entities 私有逻辑里、外人用不了的问题：
pack / derive / verify 都走这里，口径唯一。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def build_registry(entities_data: dict | None = None, book: Path | None = None) -> dict:
    """构建注册表。传 entities_data（dict）或 book（二选一）。

    返回 {"by_id", "by_name", "alias_to_name", "problems"}：
    - by_id: {id: entry}；by_name: {法定名: entry}；
    - alias_to_name: {别名: 法定名}（别名多主时 problems 记账，寻址取首个）；
    - problems: [{code, msg}]，code ∈ id_collision | alias_multi_owner。
    """
    if entities_data is None:
        if book is None:
            raise ValueError("build_registry 需要 entities_data 或 book 二选一")
        from .. import state as state_mod
        entities_data = state_mod.load_state(Path(book), "entities")
    entries = (entities_data or {}).get("entries", []) or []
    by_id: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    alias_to_name: dict[str, str] = {}
    alias_owners: dict[str, list[str]] = {}
    problems: list[dict] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "") or "")
        if name and name not in by_name:
            by_name[name] = e
        eid = str(e.get("id", "") or "")
        if eid:
            if eid in by_id:
                problems.append({"code": "id_collision",
                                 "msg": f"实体 id 碰撞：{eid}（{by_id[eid].get('name')} / {name}）"})
            else:
                by_id[eid] = e
        for a in (e.get("aliases") or []):
            a = str(a or "").strip()
            if a:
                alias_owners.setdefault(a, []).append(name)
    for a, owners in alias_owners.items():
        alias_to_name[a] = owners[0]
        if len(set(owners)) > 1:
            problems.append({"code": "alias_multi_owner",
                             "msg": f"别名「{a}」被多实体占用：{' / '.join(sorted(set(owners)))}"})
    return {"by_id": by_id, "by_name": by_name,
            "alias_to_name": alias_to_name, "problems": problems}


def resolve_ref(registry: dict, ref: Any) -> dict | None:
    """三键寻址：id → 法定名 → 别名；命中返回 entry，否则 None（绝不抛）。"""
    if ref is None:
        return None
    key = str(ref).strip()
    if not key:
        return None
    ent = (registry.get("by_id") or {}).get(key)
    if isinstance(ent, dict):
        return ent
    ent = (registry.get("by_name") or {}).get(key)
    if isinstance(ent, dict):
        return ent
    owner = (registry.get("alias_to_name") or {}).get(key)
    if owner:
        ent = (registry.get("by_name") or {}).get(owner)
        if isinstance(ent, dict):
            return ent
    return None
