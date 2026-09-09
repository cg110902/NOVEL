"""卷级 rollup：前卷世界态势摘要 —— 上下文经济学（PLAN_CONSISTENCY_50W D1）。

问题：第 200 章时实体几百个，pack 装配成本 O(全书)。解法与 LSM-tree 分层
合并同构：**历史越远粒度越粗**——每卷封存后生成一份卷末态势快照
（state/rollups/vol_XX.json，确定性派生、零 Token），pack 给后卷章节装配时
注入「前情卷末态势」块（预算上限 500 token，超限按优先级裁剪，不挤 p0 主体），
使装配成本回到 O(当前卷)。

与 changelog/snapshot 的分工：snapshot 是精确回滚点，changelog 是字段级事件史，
rollup 是**给写作上下文用的粗粒度态势摘要**——三者粒度不同、用途不同。
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from . import common, evidence, state

ROLLUP_SCHEMA = "novel-studio.rollup/v1"
ROLLUP_DIR = "rollups"
# 实体只保留「写后卷必须知道的」字段（丢失的细节走 lore/entity 卡按需取）
_ENTITY_FIELDS = ("id", "name", "type", "tier_rank", "tier_name", "life_status",
                  "status", "holder", "charges", "max_charges", "faction")
# pack 注入块的 token 预算上限（超限按优先级从尾部裁剪）
PRIOR_VOLUMES_TOKEN_CAP = 500


def rollups_dir(book: Path) -> Path:
    return state.state_dir(book) / ROLLUP_DIR


def _vol_num(vol: str) -> int:
    digits = "".join(c for c in str(vol) if c.isdigit())
    return int(digits) if digits else 0


def build_rollup(book: Path, vol: str) -> dict:
    """从当前八表确定性生成卷末态势摘要（纯派生，不写盘）。"""
    vol = str(vol).strip()
    if _vol_num(vol) <= 0:
        raise ValueError(f"非法卷名: {vol!r}（示例: vol_02）")
    finals = evidence.final_chapters(book)
    at_final_ch = max((n for _, n, _ in finals), default=0)

    cur = state.load_state(book, "current")
    ents = state.load_state(book, "entities")
    lines = state.load_state(book, "lines")
    ledger = state.load_state(book, "ledger")
    tl = state.load_state(book, "timeline")
    syn = state.load_state(book, "synopsis")

    entities_out = []
    for e in ents.get("entries", []) or []:
        if e.get("status", "active") != "active":
            continue
        row = {k: e[k] for k in _ENTITY_FIELDS if e.get(k) not in (None, "", [])}
        if row.get("name"):
            entities_out.append(row)

    open_lines = []
    for kind, arr in (("foreshadow", "foreshadows"),
                      ("misunderstanding", "misunderstandings"),
                      ("knowledge", "knowledge")):
        spec = state.line_kind_spec(kind)
        for g in lines.get(arr, []) or []:
            if str(g.get("status", "")).strip().lower() == str(spec["resolved"]).lower():
                continue
            open_lines.append({
                "id": str(g.get("id", "")), "kind": kind,
                "label": str(g.get("name") or g.get("parties") or g.get("secret") or "")[:24],
                "status": str(g.get("status", "")),
                "target_ch": g.get("target_ch"),
                "weight": g.get("level" if kind == "misunderstanding" else "weight", 1),
            })

    pools = {k: {"name": v.get("name", k), "current": v.get("current", 0)}
             for k, v in (ledger.get("pools") or {}).items()}

    return {
        "schema": ROLLUP_SCHEMA,
        "vol": vol,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "at_final_ch": at_final_ch,
        "current": {k: v for k, v in cur.items()
                    if k not in ("present_characters",) and v not in ("", [], None)},
        "entities": entities_out,
        "open_lines": sorted(open_lines, key=lambda r: (
            0 if isinstance(r.get("target_ch"), int) else 1, -(r.get("weight") or 1))),
        "ledger": pools,
        "milestones_pending": [{"id": m.get("id"), "title": m.get("title"),
                                "target_ch": m.get("target_ch")}
                               for m in tl.get("milestones", []) or []
                               if m.get("status") == "pending"],
        "clocks_active": [{"name": c.get("name"), "target_ch": c.get("target_ch"),
                           "urgency": c.get("urgency"), "desc": c.get("desc")}
                          for c in tl.get("clocks", []) or []
                          if str(c.get("status", "Active")).lower() == "active"],
        "book_logline": str(syn.get("book_logline") or ""),
        "chapter_count": len(finals),
    }


def save_rollup(book: Path, vol: str) -> Path:
    data = build_rollup(book, vol)
    out = rollups_dir(book) / f"{vol}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    common.dump_json(out, data)
    return out


def available_rollups(book: Path) -> dict[int, dict]:
    """已生成的 rollup（卷号 → 数据）。"""
    out: dict[int, dict] = {}
    d = rollups_dir(book)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("vol_*.json")):
        try:
            data = common.load_json(p)
        except (ValueError, OSError):
            continue
        if isinstance(data, dict) and data.get("schema") == ROLLUP_SCHEMA:
            n = _vol_num(p.stem)
            if n:
                out[n] = data
    return out


def _fmt_target(t) -> str:
    return f"ch_{t:03d}" if isinstance(t, int) else (str(t) if t else "长线")


def prior_volumes_digest(book: Path, cur_vol: str) -> list[str]:
    """给 pack p0 的「前情卷末态势」摘要行（按优先级排序，token 超限从尾部裁剪）。

    优先级（先保留的更重要）：世界速写 > 关键实体 > 未兑线索 > 资金池 > 时钟/里程碑。
    """
    cur_n = _vol_num(cur_vol)
    priors = {n: r for n, r in available_rollups(book).items() if n < cur_n}
    if not priors:
        return []
    lines: list[str] = []
    for n in sorted(priors):
        r = priors[n]
        vol = r.get("vol", f"vol_{n:02d}")
        head = f"【{vol} 卷末态势·至 ch_{r.get('at_final_ch', 0):03d}】"
        cur = r.get("current", {})
        posture = " ｜ ".join(str(v) for k, v in
                              ((k, cur.get(k)) for k in ("time", "region", "location",
                                                         "power_level", "situation"))
                              if v)
        lines.append(f"{head}{posture}" if posture else head)
        # 关键实体：有位阶 / 非存活 / 有充能道具 的优先（读者记忆的承重墙）
        ents = r.get("entities", [])
        key_ents = [e for e in ents
                    if e.get("tier_rank") or (e.get("life_status") and e["life_status"] != "alive")
                    or e.get("charges") is not None]
        for e in key_ents[:8]:
            tags = []
            if e.get("tier_name"):
                tags.append(e["tier_name"])
            if e.get("life_status") and e["life_status"] != "alive":
                tags.append(e["life_status"])
            if e.get("holder"):
                tags.append(f"持有:{e['holder']}")
            if e.get("charges") is not None:
                tags.append(f"余{e.get('charges')}次")
            lines.append(f"- {e.get('name', '?')}{'（' + '，'.join(str(t) for t in tags) + '）' if tags else ''}")
        open_lines = r.get("open_lines", [])
        if open_lines:
            tops = open_lines[:4]
            summary = "；".join(f"{x['id']}《{x['label']}》→{_fmt_target(x.get('target_ch'))}"
                               for x in tops)
            lines.append(f"- 未兑线 {len(open_lines)} 条（前四：{summary}）")
        pools = {k: v for k, v in (r.get("ledger") or {}).items()
                 if isinstance(v, dict) and v.get("current")}
        if pools:
            lines.append("- 资金池：" + "，".join(f"{v.get('name', k)}×{v['current']}"
                                                for k, v in list(pools.items())[:5]))
        clocks = r.get("clocks_active", [])
        for c in clocks[:3]:
            lines.append(f"- 悬顶：「{c.get('name')}」→{_fmt_target(c.get('target_ch'))}"
                         + (f"（{c.get('desc')}）" if c.get("desc") else ""))
        ms = r.get("milestones_pending", [])
        if ms:
            lines.append("- 待达里程碑：" + "；".join(
                f"{m.get('title')}@{_fmt_target(m.get('target_ch'))}" for m in ms[:3]))
    # token 预算：超限从尾部裁（尾部=优先级最低的时钟/里程碑/资金池）；
    # 至少保留每卷的态势头行——空摘要比超预算更有害
    while len(lines) > 1 and common.est_tokens("\n".join(lines)) > PRIOR_VOLUMES_TOKEN_CAP:
        lines.pop()
    return lines
