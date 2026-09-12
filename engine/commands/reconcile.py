"""卷末对账大修（D2）：`python studio.py reconcile vol_XX --write`。

定位：投影必然有损（十一表是正文的 lossy projection），误差逐章累积——
每卷末做一次**周期性维护**（如同数据库的 full rebuild）。本命令只做机械部分：
全书不变量复扫、本卷 8 探针批量重跑、高危字段变更史、投影 diff 候选清单，
产出 `log/review/reconcile_vol_XX.md` 工作单；LLM 重读对账是仪式不是代码
（按 AGENTS 宪法由主控派发临时沙盒 Reader，对着清单裁决而非大海捞针）。
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

from .. import audit, changelog, common, evidence, state

# 高危字段：改错代价最高的实体字段（对账重点盯防）
_HIGH_RISK_FIELDS = ("tier_rank", "tier_name", "holder", "life_status", "charges",
                     "max_charges", "faction")


def _vol_chapters(book: Path, vol: str) -> list[int]:
    d = book / "manuscript" / vol / "final"
    if not d.is_dir():
        return []
    nums = sorted({n for n in (common.chapter_number_from_name(f.name)
                               for f in d.glob("*.md")) if n})
    return nums


def _gather(book: Path, vol: str) -> dict:
    nums = _vol_chapters(book, vol)
    if not nums:
        raise ValueError(f"未找到 {vol} 的定稿章节（manuscript/{vol}/final/ 为空或不存在）")
    lo, hi = nums[0], nums[-1]

    # ① 全书不变量复扫
    data = {k: state.load_state(book, k) for k in state.STATE_KEYS}
    verify_errors = state.verify_data(data)
    cl_ok, cl_msg = changelog.verify(book)

    # ② 本卷 8 探针批量重跑
    audit_hits: list[dict] = []
    audit_errors: list[str] = []
    for n in nums:
        try:
            rep = audit.run_audit(book, f"ch_{n:03d}")
        except (ValueError, OSError) as exc:
            audit_errors.append(f"ch_{n:03d}: {exc}")
            continue
        if rep.get("error"):
            audit_errors.append(f"ch_{n:03d}: {rep['error']}")
            continue
        for c in rep.get("candidates", []) or []:
            audit_hits.append({"ch": f"ch_{n:03d}", **{k: c.get(k) for k in
                                                        ("id", "probe", "title", "description", "summary", "detail")
                                                        if c.get(k) is not None}})

    # ③ 本卷高危字段变更史（changelog）
    # 窗口口径 = seq 区间 (前卷末封存, 本卷末封存]：能正确纳入章间手术刀事件
    # （其 ch=None，按章过滤会漏）；本卷末封存之后的手术归下一卷对账。
    high_risk: list[dict] = []
    if changelog.active(book):
        hi_seq = changelog.seal_seq_for(book, hi) or 0
        lo_seq = changelog.seal_seq_for(book, lo - 1) or 0
        _ent_tables = (*state.KIND_TABLES, state.LEGACY_ENTITIES_KEY)
        for ev in changelog.iter_events(book):   # 流式：千章书全量物化会 OOM（FIX-5c）
            if ev.get("kind") or ev.get("table") not in _ent_tables:
                continue
            seq = int(ev.get("seq") or 0)
            if not (lo_seq < seq <= hi_seq):
                continue
            path = str(ev.get("path") or "")
            if not any(path == f or path.endswith(f".{f}") for f in _HIGH_RISK_FIELDS):
                continue
            high_risk.append({k: ev.get(k) for k in
                              ("seq", "ts", "ch", "source", "op", "path",
                               "before", "after", "op_id")})
        high_risk.sort(key=lambda e: -int(e.get("seq") or 0))

    # ④ 投影 diff 工位
    #   4a. 正文出现但未登记的候选专名（本卷合计 ≥2 次）
    #   4b. 台账 active 实体、本卷正文零出现
    vol_text = ""
    for _tok, n, text in evidence.final_chapters(book):
        if lo <= n <= hi:
            vol_text += text + "\n"
    ents = state.merged_entities_view(data)
    registered = set()
    for e in ents:
        registered.add(str(e.get("name", "")))
        registered.update(str(a) for a in e.get("aliases", []) if a)
    proj = common.load_json(book / "project.json", default={}) or {}
    stopwords = {str(w) for w in (proj.get("generic_stopwords") or [])}
    stopwords |= {str(w) for w in (proj.get("candidate_stopwords") or [])}

    token_counts = evidence.proper_noun_tokens(vol_text)
    unregistered = [{"name": t, "count": c} for t, c in
                    sorted(token_counts.items(), key=lambda kv: (-kv[1], kv[0]))
                    if c >= 2 and t not in registered and t not in stopwords][:20]

    absent = []
    for e in ents:
        if e.get("status", "active") != "active":
            continue
        names = [str(e.get("name", ""))] + [str(a) for a in e.get("aliases", []) if a]
        names = [n for n in names if n]
        if names and not any(evidence.count_aliases(vol_text, names).values()):
            absent.append({"name": names[0], "type": e.get("type", "")})
    absent = absent[:30]

    return {"vol": vol, "lo": lo, "hi": hi, "chapters": nums,
            "verify_errors": verify_errors[:12],
            "verify_error_count": len(verify_errors),
            "changelog": {"ok": cl_ok, "msg": cl_msg},
            "audit_hits": audit_hits[:24], "audit_hit_count": len(audit_hits),
            "audit_errors": audit_errors,
            "high_risk": high_risk[:24], "high_risk_count": len(high_risk),
            "unregistered": unregistered, "absent_entities": absent}


def _clip(v, n: int = 40) -> str:
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[:n] + "…"


def render_reconcile_md(payload: dict, book_name: str) -> str:
    vol = payload["vol"]
    L: list[str] = []
    L.append(f"# 卷末对账大修工作单 · {vol}（{book_name}）")
    L.append("")
    L.append(f"> 范围：ch_{payload['lo']:03d} ~ ch_{payload['hi']:03d}"
             f"（{len(payload['chapters'])} 章） ｜ 生成：{datetime.datetime.now().isoformat(timespec='seconds')}")
    L.append("> 本单由引擎机械生成（0 Token）；第五节的 LLM 对账仪式由主控派发，对着清单裁决。")
    L.append("")
    L.append("## 一、全书不变量复扫")
    L.append(f"- verify_data errors：**{payload['verify_error_count']}**"
             + ("" if payload['verify_error_count'] == 0 else "（前 12 条如下）"))
    for e in payload["verify_errors"]:
        L.append(f"  - ❌ {e}")
    cl = payload["changelog"]
    L.append(f"- changelog 一致性（fold == 磁盘）：{'✅ ' + cl['msg'] if cl['ok'] else '❌ ' + cl['msg']}")
    L.append("- 分数曲线：`python studio.py check --trend`")
    L.append("")
    L.append("## 二、本卷机械探针复扫（8 探针 × 本卷各章）")
    L.append(f"- 命中 **{payload['audit_hit_count']}** 条"
             + ("" if payload['audit_hit_count'] == 0 else "（前 24 条如下，按章复核）"))
    for h in payload["audit_hits"]:
        desc = h.get("title") or h.get("description") or h.get("summary") or h.get("detail") or ""
        L.append(f"  - {h.get('ch')} [{h.get('probe')}] {_clip(desc, 60)}")
    for e in payload["audit_errors"]:
        L.append(f"  - ⚠️ {e}")
    L.append("")
    L.append("## 三、本卷高危字段变更史（位阶/持有/生死/充能/阵营）")
    L.append(f"- 变更 **{payload['high_risk_count']}** 处"
             + ("" if payload['high_risk_count'] == 0 else "（新→旧，前 24 条）"))
    for h in payload["high_risk"]:
        L.append(f"  - {h.get('ch')} [{h.get('source')}] {h.get('path')}: "
                 f"{_clip(h.get('before'))} → {_clip(h.get('after'))}")
    L.append("")
    L.append("## 四、投影 diff 工位（正文 vs 十一表，主控裁决）")
    L.append("### 4a. 正文出现但未登记的候选专名（本卷 ≥2 次）")
    if payload["unregistered"]:
        for u in payload["unregistered"]:
            L.append(f"  - [ ] `{u['name']}`×{u['count']} —— 登记 entities or 判噪声")
    else:
        L.append("  - （无）")
    L.append("### 4b. 台账 active 实体、本卷正文零出现")
    if payload["absent_entities"]:
        for a in payload["absent_entities"]:
            L.append(f"  - [ ] {a['name']}（{a['type'] or '?'}）—— 退场 retire or 下卷提及")
    else:
        L.append("  - （无）")
    L.append("")
    L.append("## 五、LLM 对账仪式（主控派发临时沙盒，引擎不管）")
    L.append("- [ ] 派发临时沙盒 Reader 重读本卷全部 final，与十一表逐项对账（重点：第四节清单）")
    L.append("- [ ] 差异并入下一章在途提案（`state/inbox/ch_XXX.json`）随 sync 合并")
    L.append("- [ ] 对账后跑 `python studio.py ledger recompute` + `python studio.py check` 确认平账")
    L.append("- [ ] 卷末执行 `python studio.py state rollup " + vol + "` 生成下卷前情态势")
    L.append("")
    return "\n".join(L)


def cmd_reconcile(args) -> int:
    from ._shared import usage_error, ws_gate, ws_gate_code
    book = ws_gate(args)
    if book is None:
        return ws_gate_code()
    vol = str(getattr(args, "vol", "") or "").strip()
    js = bool(getattr(args, "json", False))
    try:
        payload = _gather(book, vol)
    except ValueError as exc:
        return usage_error(str(exc), args, vol=vol)
    if js:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    text = render_reconcile_md(payload, book.name)
    if getattr(args, "write", False):
        out = book / "log" / "review" / f"reconcile_{vol}.md"
        if out.is_file():
            print(f"❌ {out.relative_to(book)} 已存在（对账工作单不覆盖；重跑请先人工归档旧单）")
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"📋 卷末对账工作单已落盘：{out.relative_to(book)}")
        print(f"   机械账：verify errors {payload['verify_error_count']} ｜ 探针命中 {payload['audit_hit_count']}"
              f" ｜ 高危变更 {payload['high_risk_count']} ｜ 候选专名 {len(payload['unregistered'])}"
              f" ｜ 零出现实体 {len(payload['absent_entities'])}")
        print("   下一步：按第五节派发 LLM 对账仪式")
        return 0
    print(text)
    return 0
