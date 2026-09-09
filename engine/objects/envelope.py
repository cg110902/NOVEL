"""对象包络视图：把各表条目投影为统一 Object 信封（只读，不另存）。

信封形状：{id, kind, status, asserted, derived, prov}。
现阶段 kind 识别只靠 id 前缀 + 所在表；跨表拆分（persons/items/…）是后话，
包络 API 先立住，调用方不感知底层表结构。
"""
from __future__ import annotations

from typing import Any

_PREFIX_KIND = (
    ("p_", "person"), ("it_", "item"), ("fac_", "faction"), ("loc_", "location"),
    ("GUN-", "foreshadow"), ("MIS-", "misunderstanding"), ("KNO-", "knowledge"),
    ("EVT-", "event"), ("LOCK-", "lock"), ("COG-", "belief"), ("MS-", "milestone"),
    ("CLK-", "clock"),
)


def kind_of_id(obj_id: Any) -> str:
    """由 id 前缀判定对象类；未知返回 \"unknown\"（绝不抛）。"""
    s = str(obj_id or "").strip()
    for prefix, kind in _PREFIX_KIND:
        if s.startswith(prefix):
            return kind
    return "unknown"


def to_envelope(kind: str, entry: dict, derived: dict | None = None,
                prov: dict | None = None) -> dict[str, Any]:
    """把一条表记录包成 Object 信封（浅拷贝，不动源数据）。"""
    entry = entry if isinstance(entry, dict) else {}
    return {
        "id": entry.get("id") or entry.get("name") or "",
        "kind": kind or "unknown",
        "status": entry.get("status") or entry.get("life_status") or "",
        "asserted": dict(entry),
        "derived": dict(derived or {}),
        "prov": dict(prov or {}),
    }
