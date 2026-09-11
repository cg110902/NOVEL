"""派生计算：derived = f(十一表真值 + final 正文)。

四节派生（line_temps / scene_violations / holder_orphans / knowledge_flags）
各自 try/except 独立：单节异常只记 stats["section_error:<节>"]=1 并留空节，
绝不污染他节、绝不阻断 sync 封存（bug 宁可表现为"本节缺失"不能表现为"封存失败"）。

v2 增量：
- line_temps 含已闭环线快照（temp="closed"，供 seal/回放读"当时已闭环"）；
- scene_violations 每条带 level（error=硬伤 | warning=待核对），并对账
  present_refs ↔ present_characters 双口径（present_refs_mismatch）；
- knowledge_flags 加 B2 穿帮探针：belief.since_ch 早于真相 EVT 章 →
  verdict=contradicted（detail 注明穿帮嫌疑）；
- stats 加 story_day（current.time_day，0=未声明）与 registry_problems。
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from .registry import build_registry, resolve_ref

_TEMP_MAP = {"working": "hot", "fuzzy": "warm", "impression": "cold", "never": "never"}

_LINE_ARRS = (("foreshadow", "foreshadows"),
              ("misunderstanding", "misunderstandings"),
              ("knowledge", "knowledge"))


# sealed line_temps 的定位：memory.line_memory_map 的封存快照（档案）＋ derived_stale 的
# 比对输入。所有判定一律用现算 fresh（check/verify/proposal 均直调 memory），sealed 只读不判。
# 全派生分工：knowledge_flags→check 上账；holders/scene→verify/双轨已覆盖故不上；temps→档案。


def _derive_line_temps(book: Path, data: dict[str, dict]) -> list[dict]:
    from .. import memory as memory_mod
    from .. import state as state_mod
    out = []
    for r in memory_mod.line_memory_map(book):
        entry: dict = {
            "id": r["id"],
            "kind": r["kind"],
            "temp": _TEMP_MAP.get(r.get("tier"), "never"),
        }
        # Optional 字段：按 schema_gen 全局规则，显式 null 非法，None 时应省略而非写 null
        if r.get("last_seen_ch") is not None:
            entry["last_seen_ch"] = r.get("last_seen_ch")
        if r.get("gap") is not None:
            entry["gap"] = r.get("gap")
        # status 可能为空字符串，但不应为 None
        st = r.get("status", "")
        if st is not None and str(st) != "":
            entry["status"] = str(st)
        out.append(entry)
    # 已闭环线逐条快照（temp=closed，不参与温度排序；闭环口径=各线种 resolved 值）
    lines = data.get("lines", {}) or {}
    closed = []
    for kind, arr in _LINE_ARRS:
        try:
            resolved = str(state_mod.line_kind_spec(kind).get("resolved", "")).strip().lower()
        except (ValueError, KeyError, AttributeError):
            resolved = "resolved"
        for g in lines.get(arr) or []:
            if not isinstance(g, dict):
                continue
            if str(g.get("status", "")).strip().lower() == resolved:
                # closed 线的 last_seen_ch/gap 本就无意义，按落盘完整性闸门省略而非写 null
                closed_entry: dict = {
                    "id": str(g.get("id", "")),
                    "kind": kind,
                    "temp": "closed",
                }
                st2 = g.get("status", "")
                if st2 is not None and str(st2) != "":
                    closed_entry["status"] = str(st2)
                closed.append(closed_entry)
    # 为保证事件溯源折叠稳定性（fold 哈希一致），line_temps 必须按稳定键排序，
    # 而非按 gap 动态排序（gap 会随章节推进变化，导致 diff 无法捕捉重排序，verify 失败）。
    # 展示层的“越冷越前”排序由 memory.line_memory_map 负责，派生层仅需稳定存储。
    out.sort(key=lambda r: r["id"])
    closed.sort(key=lambda r: r["id"])
    return out + closed


def _derive_scene(book: Path, data: dict[str, dict], reg: dict) -> list[dict]:
    out: list[dict] = []
    cur = data.get("current", {}) or {}
    for name in (cur.get("present_characters") or []):
        name = str(name or "").strip()
        if not name:
            continue
        ent = resolve_ref(reg, name)
        if ent is None:
            out.append({"code": "present_unregistered", "level": "error",
                        "msg": f"在场「{name}」未登记", "refs": [name]})
        elif str(ent.get("life_status") or "") == "deceased":
            out.append({"code": "present_deceased", "level": "error",
                        "msg": f"在场「{name}」已离世", "refs": [name]})
    refs = [str(r or "").strip() for r in (cur.get("present_refs") or []) if str(r or "").strip()]
    for ref in refs:
        if resolve_ref(reg, ref) is None:
            out.append({"code": "ref_unresolved", "level": "warning",
                        "msg": f"present_refs「{ref}」无法寻址", "refs": [ref]})
    for key in ("pov_ref", "place_ref"):
        v = str(cur.get(key) or "").strip()
        if v and resolve_ref(reg, v) is None:
            out.append({"code": "ref_unresolved", "level": "warning",
                        "msg": f"{key}「{v}」无法寻址", "refs": [v]})
    # A4：双口径对账——refs 解析名集合 vs present_characters 名集合
    chars = {str(c or "").strip() for c in (cur.get("present_characters") or []) if str(c or "").strip()}
    if refs and chars:
        ref_names = set()
        for r in refs:
            ent = resolve_ref(reg, r)
            if isinstance(ent, dict) and ent.get("name"):
                ref_names.add(str(ent["name"]))
        only_ref = sorted(ref_names - chars)
        only_char = sorted(chars - ref_names)
        if only_ref or only_char:
            detail = []
            if only_ref:
                detail.append("仅 refs 有：" + "、".join(only_ref))
            if only_char:
                detail.append("仅 present_characters 有：" + "、".join(only_char))
            out.append({"code": "present_refs_mismatch", "level": "warning",
                        "msg": "在场双口径不一致（" + "；".join(detail)
                               + "）——以 refs 解析为准或补齐另一口径",
                        "refs": ["current"]})
    return out


def _derive_holders(data: dict[str, dict], reg: dict) -> list[dict]:
    out: list[dict] = []
    for e in ((data.get("entities") or {}).get("entries") or []):
        holder = str((e or {}).get("holder") or "").strip()
        if not holder:
            continue
        ent = resolve_ref(reg, holder)
        if ent is None:
            out.append({"item": str(e.get("name", "")), "holder": holder, "reason": "unregistered"})
        elif str(ent.get("life_status") or "") == "deceased":
            out.append({"item": str(e.get("name", "")), "holder": holder, "reason": "deceased"})
    return out


def _derive_knowledge(data: dict[str, dict]) -> list[dict]:
    from .. import common as common_mod
    out: list[dict] = []
    lines = data.get("lines", {}) or {}
    by_line: dict[str, dict] = {}
    for arr in ("foreshadows", "misunderstandings", "knowledge"):
        for g in (lines.get(arr) or []):
            if isinstance(g, dict) and g.get("id"):
                by_line[str(g["id"])] = g
    events_by_id = {str(e.get("id")): e for e in ((data.get("timeline") or {}).get("events") or [])
                    if isinstance(e, dict) and e.get("id")}
    lock_ids = {str(e.get("id")) for e in ((data.get("locked") or {}).get("entries") or [])
                if isinstance(e, dict) and e.get("id")}
    for c in ((data.get("cognition") or {}).get("entries") or []):
        if not isinstance(c, dict):
            continue
        tref = str(c.get("truth_ref") or "").strip()
        if not tref:
            continue
        cid, char, kind = str(c.get("id", "")), str(c.get("character", "")), str(c.get("kind", ""))
        if tref in events_by_id:
            # B2 穿帮探针：认知建立章早于真相事件章 → 角色"预知"了尚未发生的事
            ev = events_by_id[tref]
            bch = common_mod.chapter_token_to_num(c.get("since_ch"))
            ech = common_mod.chapter_token_to_num(ev.get("chapter"))
            if bch and ech and bch < ech:
                out.append({"cog_id": cid, "character": char, "truth_ref": tref,
                            "verdict": "contradicted",
                            "detail": f"穿帮嫌疑：{char} 于 ch_{bch:03d} 已知晓"
                                      f" ch_{ech:03d} 才发生的 {tref}（预知/泄密/记错章）"})
            else:
                out.append({"cog_id": cid, "character": char, "truth_ref": tref,
                            "verdict": "aligned", "detail": "锚点事实存在"})
            continue
        if tref in lock_ids:
            out.append({"cog_id": cid, "character": char, "truth_ref": tref,
                        "verdict": "aligned", "detail": "锚点事实存在"})
            continue
        g = by_line.get(tref)
        if g is None:
            out.append({"cog_id": cid, "character": char, "truth_ref": tref,
                        "verdict": "unresolved", "detail": "真相锚点不存在（编号写错或尚未登记）"})
            continue
        st = str(g.get("status", ""))
        if tref.startswith("MIS-") and st == "Resolved" and kind == "misunderstanding":
            out.append({"cog_id": cid, "character": char, "truth_ref": tref,
                        "verdict": "contradicted",
                        "detail": "该误会已澄清，角色仍持旧认知（故意滞后请忽略）"})
        elif tref.startswith("KNO-") and st == "Revealed" and kind == "misunderstanding":
            out.append({"cog_id": cid, "character": char, "truth_ref": tref,
                        "verdict": "contradicted", "detail": "秘密已揭示，角色认知仍为误解"})
        else:
            out.append({"cog_id": cid, "character": char, "truth_ref": tref,
                        "verdict": "aligned", "detail": f"锚点状态 {st}，认知未冲突"})
    return out


def _derive_stats(data: dict[str, dict], reg: dict, line_temps: list[dict]) -> dict[str, int]:
    clocks = ((data.get("timeline") or {}).get("clocks") or [])
    n_closed = sum(1 for r in line_temps if r.get("temp") == "closed")
    story_day = (data.get("current") or {}).get("time_day")
    return {
        "entities": len((data.get("entities") or {}).get("entries") or []),
        "lines_open": len(line_temps) - n_closed,
        "lines_closed": n_closed,
        "events": len((data.get("timeline") or {}).get("events") or []),
        "clocks_active": sum(1 for c in clocks if str((c or {}).get("status", "")).lower() == "active"),
        "beliefs": len((data.get("cognition") or {}).get("entries") or []),
        "locks": len((data.get("locked") or {}).get("entries") or []),
        "story_day": story_day if isinstance(story_day, int) and not isinstance(story_day, bool) else 0,
        "registry_problems": len(reg.get("problems") or []),
    }


def compute_derived(book: Path, sealed_ch: str = "") -> dict[str, Any]:
    """计算派生全量（纯读，不落盘）。sealed_ch 为封存章号（可空=试算）。"""
    from .. import state as state_mod
    book = Path(book)
    data = {k: state_mod.load_state(book, k) for k in state_mod.ASSERTED_KEYS}
    data["entities"] = {"entries": state_mod.merged_entities_view(data)}
    reg = build_registry(data.get("entities") or {})
    stats: dict[str, int] = {}
    sections: dict[str, Any] = {}
    jobs = (
        ("line_temps", lambda: _derive_line_temps(book, data)),
        ("scene_violations", lambda: _derive_scene(book, data, reg)),
        ("holder_orphans", lambda: _derive_holders(data, reg)),
        ("knowledge_flags", lambda: _derive_knowledge(data)),
    )
    for name, fn in jobs:
        try:
            sections[name] = fn()
        except Exception:
            sections[name] = []
            stats[f"section_error:{name}"] = 1
    try:
        stats.update(_derive_stats(data, reg, sections["line_temps"]))
    except Exception:
        stats["section_error:stats"] = 1
    return {"schema_version": "novel-studio.derived/v1", "sealed_ch": sealed_ch,
            "sealed_at": datetime.datetime.now().isoformat(timespec="seconds"),
            **sections, "stats": stats}


def seal_derived(book: Path, ch: str) -> dict:
    """计算并落盘派生表（sync 封存 / state recompute 的唯一写口）。"""
    from .. import state as state_mod
    payload = compute_derived(book, sealed_ch=ch)
    state_mod.save_state(book, "derived", payload, source="derived", ch=ch)
    return {"sealed_ch": ch,
            "line_temps": len(payload["line_temps"]),
            "scene_violations": len(payload["scene_violations"]),
            "holder_orphans": len(payload["holder_orphans"]),
            "knowledge_flags": len(payload["knowledge_flags"])}
