"""章节流转命令：pack / beats / evidence / check / review / critic / graph / export。"""
from __future__ import annotations

import json
import re
import sys

from .. import audit, checks, common, evidence, scorecard, state
from .. import pack as pack_mod
from .. import graph as graph_mod
from .. import cockpit as cockpit_mod

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    _HAS_RICH = True
    console = Console()
except ImportError:
    _HAS_RICH = False
    console = None

from ._shared import _norm_ch, parse_audit_frontmatter, usage_error, ws_gate, ws_gate_code


# ---------------------------------------------------------------------------
# pack
# ---------------------------------------------------------------------------
def cmd_pack(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    js = bool(getattr(args, "json", False))

    def _err(msg: str, code: int = 2, err_code: str = "usage") -> int:
        if js:
            print(json.dumps({"ok": False, "code": err_code, "error": msg},
                             ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return code

    ch = None
    if args.chapter:
        ch = _norm_ch(args.chapter)
        if ch is None:
            return _err(f"无法解析章节编号: {args.chapter!r}（示例: 6 或 ch_006）")
    try:
        if ch is None and not args.open_path:
            return _err("pack 需要章节号（如 pack ch_006），或仅 --open <相对路径> 取原文")
        payload = (pack_mod.build_pack(book, ch, lean=args.lean, full=args.full,
                                      role=getattr(args, "as_role", "drafter"))
                 if ch else {"chapter": None})
        if args.open_path:
            payload["opened"] = pack_mod.open_file(book, args.open_path,
                                                   role=getattr(args, "as_role", "drafter"))
    except PermissionError as exc:
        # 禁读网关拦截——不是业务失败，是越权，单列退出码语义仍归 1（阻断）。
        # --json 信封统一带 ok/code，避免消费方只认 ok 的话把越权当成功。
        if js:
            print(json.dumps({"ok": False, "error": "forbidden",
                              "code": "forbidden", "path": args.open_path,
                              "as": getattr(args, "as_role", "drafter"),
                              "detail": str(exc)}, ensure_ascii=False, indent=2))
        else:
            print(f"⛔ {exc}")
        return 1
    except ValueError as exc:
        return _err(str(exc), code=1, err_code="engine")
    if js:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if ch is None:
            o = payload["opened"]
            print(f"📂 {o['path']}\n\n{o['text']}")
        else:
            print(pack_mod.render_pack(payload))
    return 0



# ---------------------------------------------------------------------------
# evidence
# ---------------------------------------------------------------------------
def cmd_evidence(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    kind, rest = args.kind, list(args.args or [])

    def _err(msg: str, code: int = 2) -> int:
        """evidence 是纯 JSON 数据命令（README 契约：输出零杂质）；用法错误同样输出
        JSON 信封（ P5 同类约定：--json 消费方永不接到裸文本 stdout）。"""
        print(json.dumps({"kind": "evidence_error", "ok": False, "code": "usage",
                          "error": msg, "evidence_kind": kind}, ensure_ascii=False))
        return code

    if kind == "all":
        if rest:
            return _err("evidence all 不接受参数（聚合全书五件套）")
        payload = {"kind": "all", "words": evidence.words(book), "style": evidence.style(book),
                   "form": evidence.form_distribution(book), "dup": evidence.dup(book),
                   "gaps": evidence.gaps(book)}
    elif kind == "file":
        if len(rest) not in (1, 2):
            return _err("evidence file 需要 <相对路径> [章节号(并入该章 editor_extra)]")
        if len(rest) == 2 and _norm_ch(rest[1]) is None:
            return _err(f"无法解析章节编号: {rest[1]!r}（示例: 6 或 ch_006）")
        payload = evidence.file_stats(book, rest[0], rest[1] if len(rest) == 2 else None)
        if payload.get("error"):
            return _err(payload["error"], code=1)
    elif kind in ("gaps", "words"):
        if rest:
            return _err(f"evidence {kind} 不接受参数，收到: {rest}")
        payload = evidence.gaps(book) if kind == "gaps" else evidence.words(book)
    elif kind == "names":
        if rest:
            return _err(f"evidence names 不接受参数，收到: {rest}")
        payload = evidence.names(book)
    elif kind in ("candidates", "prev"):
        if len(rest) != 1 or _norm_ch(rest[0]) is None:
            return _err(f"evidence {kind} 需要章节号（如: evidence {kind} ch_007）")
        ch = _norm_ch(rest[0])
        payload = evidence.candidates(book, ch) if kind == "candidates" \
            else evidence.prev_contrast(book, ch)
        if payload.get("error"):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
    elif kind == "mentions":
        if len(rest) > 1:
            return _err("evidence mentions 至多一个实体名（省略=注册表总览）")
        payload = evidence.mentions(book, rest[0] if rest else None)
        if payload.get("unknown"):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 2
    elif kind == "index":
        rebuild = any(a in ("--rebuild", "-r", "rebuild") for a in rest)
        from .. import db
        payload = db.build_or_update_index(book, force_rebuild=rebuild)
    else:
        if len(rest) > 1:
            return _err(f"evidence {kind} 至多一个章节参数")
        ch = None
        if rest:
            ch = _norm_ch(rest[0])
            if ch is None:
                return _err(f"无法解析章节编号: {rest[0]!r}（示例: 6 或 ch_006）")
        payload = evidence.dup(book, ch) if kind == "dup" else evidence.style(book, ch)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_index(args) -> int:
    book = ws_gate(args)
    if book is None:
        return ws_gate_code()
    rebuild = bool(getattr(args, "rebuild", False))
    from .. import db
    payload = db.build_or_update_index(book, force_rebuild=rebuild)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0




# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
def _bisect_scan(book) -> dict:
    """逐快照（+当前 state）跑 verify_data，定位不变量首次破坏点。

    口径诚实：只覆盖 state 级不变量（结构/schema/算术/引用闭合/前置因果）——
    叙事类检查需要稿件与全文扫描，不在快照内；缺表按默认空表处理（只校验
    存在的部分）。
    """
    from .. import snapshot as snapshot_mod
    rows: list[dict] = []
    names = snapshot_mod.list_snapshots(book)
    for name in names:
        folder = snapshot_mod.snapshots_root(book) / name
        data: dict[str, dict] = {}
        unreadable = []
        for k in state.STATE_KEYS:
            p = folder / f"{k}.json"
            if p.is_file():
                try:
                    data[k] = common.load_json(p)
                except (ValueError, OSError):
                    unreadable.append(k)
        for k in state.STATE_KEYS:
            data.setdefault(k, state.defaults_for(k))
        _leg_p = folder / "entities.json"
        if _leg_p.is_file() and not any((data.get(k) or {}).get("entries") for k in state.KIND_TABLES):
            try:
                _split = state.split_entities_entries(common.load_json(_leg_p).get("entries", []) or [])
                for k in state.KIND_TABLES:
                    data[k] = {"entries": _split[k]}
            except (ValueError, OSError):
                unreadable.append("entities")
        errs = state.verify_data(data)
        rows.append({"name": name, "chapter": snapshot_mod.chapter_of_snapshot(name),
                     "ok": not errs, "errors": errs[:3], "unreadable": unreadable})
    # 当前 state 作为最后一站
    live: dict[str, dict] = {}
    live_err: list[str] = []
    try:
        for k in state.STATE_KEYS:
            live[k] = state.load_state(book, k)
        live_err = state.verify_data(live)
    except (ValueError, OSError) as exc:
        live_err = [f"当前 state 不可读: {exc}"]
    rows.append({"name": "(当前 state)", "chapter": None,
                 "ok": not live_err, "errors": live_err[:3], "unreadable": []})
    first_break = next((r["name"] for r in rows if not r["ok"]), None)
    prev_ok = None
    if first_break:
        idx = next(i for i, r in enumerate(rows) if r["name"] == first_break)
        prev_ok = rows[idx - 1]["name"] if idx > 0 else None
    return {"rows": rows, "first_break": first_break, "previous_ok": prev_ok}


def _cmd_check_bisect(book, args) -> int:
    payload = _bisect_scan(book)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    rows = payload["rows"]
    print("🔬 快照不变量二分（verify_data 逐快照 + 当前 state）")
    for r in rows:
        mark = "✅" if r["ok"] else "❌"
        ch = f"ch_{r['chapter']:03d}" if r["chapter"] else "—"
        errs = f"  ⚠ {'；'.join(r['errors'][:2])}" if r["errors"] else ""
        print(f"  {mark} {r['name']:<44} ({ch}){errs}")
    fb, prev = payload["first_break"], payload["previous_ok"]
    if fb:
        print(f"\n ▶ 不变量首次破坏：{fb}" + (f"；上一正常：{prev}" if prev else ""))
        print("   问题引入区间 = (上一正常, 首次破坏]；取证：changelog blame / state at（事件流已激活时）")
    else:
        print("\n ▶ 全部快照与当前 state 的不变量均通过")
    return 0


def cmd_check(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    if getattr(args, "bisect", False):
        return _cmd_check_bisect(book, args)
    if getattr(args, "trend", False):
        # 分数曲线模式：不跑体检，只消费历史（测量史只增不改）
        rows = scorecard.load_scores(book)
        if args.json:
            print(json.dumps({"trend": rows}, ensure_ascii=False, indent=2))
        else:
            print(scorecard.render_trend(book))
        return 0
    if getattr(args, "accepted", False):
        # 只列基线：纯读，不跑体检、不记分
        acc = checks.load_accepted(book)
        recs = [{"fp": fp, "code": r.get("code", ""), "msg": r.get("msg", ""),
                 "ts": r.get("ts", "")} for fp, r in sorted(acc.items())]
        if args.json:
            print(json.dumps({"accepted": recs}, ensure_ascii=False, indent=2))
        elif not recs:
            print("（确认基线为空：用 check --accept <fp> 把已裁决的 warnings/infos 消音）")
        else:
            print(f"📌 确认基线（{len(recs)} 条；check --unaccept <fp> 撤销）：")
            for r in recs:
                print(f"   {r['fp']} [{r['code']}] {r['msg'][:90]}")
        return 0
    if getattr(args, "accept", None):
        # 确认消音：对 full 全量解析（已确认的也可命中→幂等提示），只记分一次？不——
        # 基线操作不是体检，不记 scorecard。
        queries = [q.strip() for q in str(args.accept).split(",") if q.strip()]
        report = checks.run_checks(book, full=True)
        done, notes = checks.accept_findings(book, report, queries)
        if args.json:
            print(json.dumps({"ok": True, "accepted": done, "notes": notes}, ensure_ascii=False))
        else:
            if done:
                print(f"✅ 已确认 {len(done)} 条：{', '.join(done)}（下次 check 自动折叠；--full 可重见）")
            for n in notes:
                print(f"   ℹ️ {n}")
            if not done and not notes:
                print("（无有效 fp，请从 check --json 的 fp 字段复制，前缀≥6 位）")
        return 0
    if getattr(args, "unaccept", None):
        queries = [q.strip() for q in str(args.unaccept).split(",") if q.strip()]
        done, notes = checks.unaccept_findings(book, queries)
        if args.json:
            print(json.dumps({"ok": True, "unaccepted": done, "notes": notes}, ensure_ascii=False))
        else:
            if done:
                print(f"↩️ 已撤销确认 {len(done)} 条：{', '.join(done)}（下次 check 恢复提醒）")
            for n in notes:
                print(f"   ℹ️ {n}")
        return 0
    report = checks.run_checks(book, full=bool(getattr(args, "full", False)))
    scorecard.append_score(book, report)  # 分数曲线积累（log/scorecard.jsonl）
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 70)
        print(f" 🩺 [全息双核体检] {book.name}")
        print("=" * 70)

        sys_h = report.get("system_health", {})
        sys_errs = sys_h.get("errors", [])
        sys_warns = sys_h.get("warnings", [])
        sys_infos = sys_h.get("infos", [])

        print(" 🖥️  【内核一：系统工程运行时健康 (System & Runtime Health)】")
        if not sys_errs and not sys_warns and not sys_infos:
            print("    ✅ 运行环境、依赖完整性与工件链健康")
        else:
            for e in sys_errs:
                print(f"    ❌ [{e['code']}] {e['msg']}")
                if e.get("remedy"):
                    print(f"       💡 [自愈方案] {e['remedy']}")
            for w in sys_warns:
                print(f"    ⚠️ [{w['code']}] {w['msg']}")
                if w.get("remedy"):
                    print(f"       💡 [建议处理] {w['remedy']}")
            for i in sys_infos:
                print(f"    ℹ️ [{i['code']}] {i['msg']}")

        print("\n 📖  【内核二：商业小说叙事与网文体感 (Narrative & Commercial Health)】")
        nar_h = report.get("narrative_health", {})
        nar_errs = nar_h.get("errors", [])
        nar_warns = nar_h.get("warnings", [])
        nar_infos = nar_h.get("infos", [])

        if not nar_errs and not nar_warns and not nar_infos:
            print("    ✅ 剧情张力、人设聚焦、伏笔与账本完全自洽")
        else:
            for e in nar_errs:
                print(f"    ❌ [{e['code']}] {e['msg']}")
                if e.get("remedy"):
                    print(f"       💡 [自愈方案] {e['remedy']}")
            for w in nar_warns:
                print(f"    ⚠️ [{w['code']}] {w['msg']}")
                if w.get("remedy"):
                    print(f"       💡 [建议处理] {w['remedy']}")
            for i in nar_infos:
                print(f"    ℹ️ [{i['code']}] {i['msg']}")

        if report.get("onboarding"):
            print("\n 📋 新书 Stage 0 待办：填实 bible/ 与 outlines/ 中的 {{slot:}} 后体检自动转绿"
                  "（开写后未填槽位将恢复阻断）")

        print("-" * 70)
        print(f" 📊 汇总：System errors {len(sys_errs)}, warnings {len(sys_warns)}"
              f" ｜ Narrative errors {len(nar_errs)}, warnings {len(nar_warns)}"
              f" ｜ 定稿章数 {report['stats'].get('final_chapters', 0)}")
        if report.get("stats", {}).get("accepted_hidden"):
            print(f" 📌 另有 {report['stats']['accepted_hidden']} 条已确认 findings 已折叠"
                  f"（check --accepted 查看，--full 重见全量）")
        _hc_note = checks.history_collapse_note(
            report.get("stats", {}).get("history_collapsed_by_code") or {})
        if _hc_note:
            print(f" {_hc_note}")
    return 0 if report["ok"] else 1



# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------
def _render_review_md(d: dict) -> str:
    qb = d["quote_balance"]
    names = "；".join(f"{e['name']}（别名：{'、'.join(e['aliases'])}）" if e["aliases"] else e["name"]
                     for e in d["proper_names"]) or "（注册表为空）"
    bal = "、".join(f"{p.get('name', pid)}（{pid}）: {p.get('current', 0)} {p.get('unit', '')}".rstrip()
                   for pid, p in sorted(d["ledger_now"].items())) or "（无池）"
    loc_str = f"{d.get('location') or '未明确'} ｜ {d.get('time') or '未明确'}"
    inj_str = f"伤势：{d.get('injury') or '完好'} ｜ 局势：{d.get('situation') or '正常'}"
    present_str = "、".join(d["present"]) if d["present"] else "（未声明）"

    L = [f"# {d['chapter']} 校对注记（四块事实结算单）", ""]
    L += ["<!-- 骨架由 `studio review new` 生成：机器数据已预填，结果与证据由主控核定。",
          "     每条结论要证据：正文引文片段，或 evidence/audit 输出（字段名+数值）——无证据打钩视为未审。",
          "     -->", ""]

    L += ["## 块一：现场结算（时地、伤势与在场角色）", ""]
    L += [f"- **时地快照**：{loc_str}",
          f"- **状态指征**：{inj_str}",
          f"- **章末在场（current）**：{present_str}",
          "- **核定结果**：", ""]

    L += ["## 块二：财务与充能结算（资金流动与道具消耗）", ""]
    L += [f"- **账本池余额**：{bal}",
          "- **关键道具 charges 消耗**：",
          "- **核定结果**：", ""]

    L += ["## 块三：因果与不可逆事实结算（LOCK 规范与线索闭环）", ""]
    if d.get("locked_now"):
        L += ["- **不可逆事实清单（LOCK 刚性约束）**："]
        L += [f"  - {lk}" for lk in d["locked_now"][:10]]
    else:
        L += ["- **不可逆事实清单**：（暂无不可逆事实登记）"]
    if d.get("due_lines"):
        L += ["- **本章到期主线/伏笔动作**："]
        L += [f"  - {dl}" for dl in d["due_lines"][:10]]
    else:
        L += ["- **本章到期主线/伏笔动作**：（无到期线索）"]
    L += ["- **核定结果**：", ""]

    L += ["## 块四：细纲契约逐条验收", ""]
    if d["acceptance"]:
        L += ["<!-- 逐条回答，格式：N. ✓/✗ + 证据（正文引文「…」或 evidence 字段=数值，如 cjk=3120） -->"]
        for i, item in enumerate(d["acceptance"], 1):
            L.append(f"{i}. {item} ")
        L.append("")
    else:
        L += ["（beats 无「验收」节——review_gate 不拦，但建议补验收条目）", ""]

    L += ["## 附：机械体检与格式扫描", ""]
    L += [f"- **标点计数**：「={qb['「']} 」={qb['」']} “={qb['“']} ”={qb['”']} 『={qb['『']} 』={qb['』']}",
          f"- **专名一致性**：{names}",
          f"- **格式残留**：{{{{slot}}}}={d['residue']['slot']} ｜ candidate_*={d['residue']['candidate']}"]
    if d.get("style_info"):
        si = d["style_info"]
        L.append(f"- **文风雷达**：平均句长 {si.get('len_mean', 0)} 字（偏离 {si.get('len_mean_delta', 0):+}） ｜ 对话占比 {si.get('dialogue_ratio', 0)}")
    L += ["- **核定结果**：", ""]
    return "\n".join(L) + "\n"


def cmd_review(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    js = bool(getattr(args, "json", False))

    def _err(msg: str, code: int = 2, err_code: str = "usage") -> int:
        if js:
            print(json.dumps({"ok": False, "code": err_code, "error": msg},
                             ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return code

    if getattr(args, "rev_action", None) != "new":
        return _err("review 需要 new 子命令，如: python studio.py review new ch_007")
    n = common.chapter_token_to_num(args.chapter)
    if n is None:
        return _err(f"无法解析章节号: {args.chapter}")
    ch = f"ch_{n:03d}"
    try:
        data = checks.review_skeleton(book, ch)
    except ValueError as exc:
        return _err(str(exc), code=1,
                    err_code="no_final" if "final" in str(exc) else "engine")
    md = _render_review_md(data)
    if getattr(args, "write", False):
        dest = book / "log" / "review" / f"{ch}.md"
        if dest.exists():
            return _err(f"{dest} 已存在——注记是主控工件，拒绝覆盖（请手工编辑）",
                        code=1, err_code="exists")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(md, encoding="utf-8")
        if getattr(args, "json", False):
            print(json.dumps({"chapter": ch, "written": str(dest.relative_to(book))}, ensure_ascii=False))
        else:
            print(f"🧾 校对注记骨架已写入: {dest}")
            print("   填写「六项核对」结果与「## 验收」逐条 ✓/✗+证据后，再组装提案并 sync。", file=sys.stderr)
        return 0
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(md)
    return 0


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------
def _render_audit_md(payload: dict) -> str:
    hard_count = payload.get("hard_count", 0)
    soft_count = payload.get("soft_count", 0)
    total = payload.get("total_candidates", 0)
    tok = payload.get("chapter", "ch_001")
    candidates = payload.get("candidates", [])

    lines = [
        "---",
        f"audit_chapter: {tok}",
        f"hard: {hard_count}",
        f"soft: {soft_count}",
        # logic：轨 3（语义逻辑与出戏审查）的确凿条目数，由 Auditor 手填、引擎不计算。
        # 与 hard 同闸：logic>0 且未 adjudicated 时 sync 拒绝封存（V3.2）。
        "logic: 0",
        "adjudicated: false",
        "---",
        "",
        f"# {tok} 事实一致性仲裁报告 (Auditor)",
        "",
        "## 📊 仲裁总览",
        f"- 机械探针扫描候选数：{total} 条",
        f"- 🔴 确凿硬矛盾候选：{hard_count} 条",
        f"- 🟡 软性存疑候选：{soft_count} 条",
        "",
        "---",
        "",
        "## 🔴 确凿硬矛盾（必须定向修复或核实排除）",
    ]
    hards = [c for c in candidates if c.get("severity") == "candidate_hard"]
    if not hards:
        lines.append("✅ 本章未检出确凿硬矛盾候选。")
    else:
        for c in hards:
            lines.append(f"- **[{c['id']}] [{c['probe']}] {c['title']}**")
            if c.get("evidence"):
                lines.append(f"  - **正文证据**：`{c['evidence']}`")
            if c.get("state_ref"):
                lines.append(f"  - **台账依据**：`{c['state_ref']}`")
            lines.append(f"  - **描述**：{c['description']}")
            if c.get("suggestion"):
                lines.append(f"  - ✂️ **处理建议**：{c['suggestion']}")
            lines.append("")

    lines.extend([
        "---",
        "",
        "## 🟡 软性存疑（主控关注）",
    ])
    softs = [c for c in candidates if c.get("severity") == "candidate_soft"]
    if not softs:
        lines.append("无")
    else:
        for c in softs:
            lines.append(f"- **[{c['id']}] [{c['probe']}] {c['title']}**")
            if c.get("evidence"):
                lines.append(f"  - **正文证据**：`{c['evidence']}`")
            if c.get("state_ref"):
                lines.append(f"  - **台账依据**：`{c['state_ref']}`")
            lines.append(f"  - **描述**：{c['description']}")
            if c.get("suggestion"):
                lines.append(f"  - **建议**：{c['suggestion']}")
            lines.append("")

    lines.extend([
        "---",
        "",
        "## 🧠 语义逻辑与出戏审查（轨 3 · Auditor 手写，引擎不覆盖）",
        "<!-- 逐条填「世界观一致性 / 人物行为逻辑 / 因果与代价闭环 / 现场常识与时空」四类"
        "确凿出戏点：正文原句 ➔ 为什么读者会出戏 ➔ 定向手术刀指令或 Evolution 转办单。"
        "填完后把顶部 logic 改成条目数（0 = 无确凿问题）；存疑但不确凿的写进 🟡 段并走 soft 出口。"
        "本节正文在重跑 audit --write 时被原样保留，logic 计数随本节一并沿用 -->",
        "",
        "---",
        "",
        "## ✅ 交叉核实排除（误报归档）",
        "<!-- 若经人工或 Auditor 核实上述某条属于语境误报（如回忆、同名新道具等），在此记录排除理由并将 hard 扣减或将顶部 adjudicated 设为 true -->",
        "",
    ])
    return "\n".join(lines)


_AUDIT_HARD_HEAD = r"^##\s*🔴"
_AUDIT_EXCLUDE_HEAD = r"^##\s*✅\s*交叉核实排除"
_AUDIT_SEMANTIC_HEAD = r"^##\s*🧠\s*语义逻辑与出戏审查"


def _audit_hard_block(text: str) -> str:
    """提取报告「🔴 确凿硬矛盾」段落正文（剥掉分隔线/空行后归一化，用于比对候选是否变化）。"""
    lines = [ln.strip() for ln in common.md_section(text, _AUDIT_HARD_HEAD)]
    return "\n".join(ln for ln in lines if ln and ln != "---")


def _audit_adjudication_note(text: str) -> str:
    """提取 Auditor 手写的「交叉核实排除」正文（模板自带的 HTML 注释不算内容）。"""
    body = []
    for ln in common.md_section(text, _AUDIT_EXCLUDE_HEAD):
        s = ln.strip()
        if not s or s == "---" or s.startswith("<!--"):
            continue
        body.append(ln)
    return "\n".join(body).strip()


def _audit_semantic_note(text: str) -> str:
    """提取 Auditor 手写的「语义逻辑与出戏审查」正文（模板自带的 HTML 注释不算内容）。"""
    body = []
    for ln in common.md_section(text, _AUDIT_SEMANTIC_HEAD):
        st = ln.strip()
        if not st or st == "---" or st.startswith("<!--"):
            continue
        body.append(ln)
    return "\n".join(body).strip()


def _merge_audit_report(old_text: str | None, new_text: str,
                        clear_logic: bool = False,
                        adjudicate: bool = False) -> tuple[str, list[str]]:
    """重跑 `audit --write` 时保住既有裁决痕迹。

    此前 cmd_audit 是无条件 `write_text` 覆盖，而 `_render_audit_md` 恒定写
    `adjudicated: false`：Auditor 完成轨 2 语义裁决 → Stylist 动刀 → 重新 audit，
    这一步会把人工裁决整份抹掉并把闸门打回未裁定。现按机械可判定规则合并：
    - 若显式指定 adjudicate=True → 强制置 adjudicated: true；
    - 否则若「🔴 确凿硬矛盾」段落逐字未变 → 沿用旧 front-matter 的 adjudicated；
      变了（探针结论更新）→ 回落 false，需重新裁决；
    - Auditor 写在「✅ 交叉核实排除」里的排除理由原样搬回新报告；
    - 轨 3（语义审查）：若指定 clear_logic=True → 重置 logic: 0，解除阻断；
      否则原样搬回 Auditor 手填的 logic 计数。
    """
    notes: list[str] = []
    if not old_text:
        if adjudicate:
            new_text = new_text.replace("adjudicated: false", "adjudicated: true", 1)
            notes.append("已显式标记为已人工裁决（adjudicated: true）")
        return new_text, notes
    old_fm = parse_audit_frontmatter(old_text) or {}
    if adjudicate:
        new_text = new_text.replace("adjudicated: false", "adjudicated: true", 1)
        notes.append("已显式标记为已人工裁决（adjudicated: true）")
    elif _audit_hard_block(old_text) != _audit_hard_block(new_text):
        if old_fm.get("adjudicated"):
            notes.append("硬矛盾候选已变化 → adjudicated 回落 false（请重新裁决）")
    elif old_fm.get("adjudicated"):
        new_text = new_text.replace("adjudicated: false", "adjudicated: true", 1)
        notes.append("硬矛盾候选未变化 → 沿用既有 adjudicated: true")
    keep = _audit_adjudication_note(old_text)
    if keep:
        new_text = new_text.rstrip() + "\n\n### 既有排除理由（自上一版报告保留）\n" + keep + "\n"
        notes.append("已保留上一版报告的「交叉核实排除」正文")
    # 轨 3 是纯人工产物（引擎无对应探针），重跑必须原样搬回，连同 Auditor 手填的 logic 计数——
    # 否则「手术刀修复后重跑 audit」会把语义裁决抹掉、并把闸门悄悄放回放行侧。
    # 若带 --clear-logic 参数则显式解除阻断（保持正文备忘，logic 回归 0）。
    sem = _audit_semantic_note(old_text)
    if sem:
        new_text = new_text.replace(
            "## ✅ 交叉核实排除（误报归档）",
            "### 既有语义审查（自上一版报告保留）\n" + sem + "\n\n---\n\n"
            "## ✅ 交叉核实排除（误报归档）", 1)
        try:
            logic_n = int(old_fm.get("logic", 0) or 0)
        except (TypeError, ValueError):
            logic_n = 0
        if clear_logic:
            notes.append(f"已清空既有语义审查 logic 阻断计数（原 logic={logic_n} → 现 logic=0）")
        elif logic_n > 0:
            new_text = new_text.replace("logic: 0", f"logic: {logic_n}", 1)
            notes.append(f"已保留上一版报告的「语义逻辑与出戏审查」正文（logic={logic_n}）")
        else:
            notes.append("已保留上一版报告的「语义逻辑与出戏审查」正文（logic=0）")
    elif clear_logic:
        notes.append("已清空语义审查 logic 计数（logic=0）")
    return new_text, notes


def cmd_audit(args) -> int:
    book = ws_gate(args)
    if book is None:
        return ws_gate_code()
    ch_arg = getattr(args, "chapter", None)
    if not ch_arg:
        latest = common.latest_chapter_number(book, "final") or 1
        ch_arg = f"ch_{latest:03d}"
    n = common.chapter_token_to_num(ch_arg)
    if not n:
        return usage_error(f"无法解析章节号: {ch_arg!r}", args, chapter=str(ch_arg))
    tok = f"ch_{n:03d}"

    payload = audit.run_audit(book, tok)
    clear_logic = getattr(args, "clear_logic", False)
    adjudicate = getattr(args, "adjudicate", False)
    do_write = getattr(args, "write", False) or clear_logic or adjudicate
    if do_write and not payload.get("error"):
        audit_dir = book / "log" / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        out_file = audit_dir / f"{tok}.md"
        prev_text = None
        if out_file.is_file():
            try:
                prev_text = out_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                prev_text = None
        md_content, merge_notes = _merge_audit_report(
            prev_text, _render_audit_md(payload),
            clear_logic=clear_logic, adjudicate=adjudicate)
        out_file.write_text(md_content, encoding="utf-8")
        payload["written_file"] = str(out_file.relative_to(book))
        if merge_notes:
            payload["preserved"] = merge_notes
        if not getattr(args, "json", False):
            print(f" 💾 已生成并写入仲裁报告: {out_file.relative_to(book)}")
            for note in merge_notes:
                print(f"    ♻️ {note}")

    if payload.get("error"):
        if getattr(args, "json", False):
            # 与文本模式同口径：audit 失败（final 缺失等）= 业务拒收 1，
            # 但 JSON 模式仍把 payload（含 error）整体吐出供消费方读取。
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 1
        print(f"❌ {payload['error']}")
        return 1

    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"\n🔍 [确定性机械审计探针] {payload['chapter']}（分析稿件：{payload['file']}）")
    print(f"   候选矛盾总数: {payload['total_candidates']}（🔴 硬矛盾候选: {payload['hard_count']} ｜ 🟡 软存疑候选: {payload['soft_count']}）\n")
    if not payload["candidates"]:
        print("   ✅ 未检出机械矛盾候选（状态与正文基础事实高度自洽）\n")
        return 0

    for c in payload["candidates"]:
        icon = "🔴" if c["severity"] == "candidate_hard" else "🟡"
        print(f"   {icon} [{c['id']}] [{c['probe']}] {c['title']}")
        print(f"      描述: {c['description']}")
        if c.get("evidence"):
            print(f"      证据: {c['evidence']}")
        if c.get("state_ref"):
            print(f"      台账: {c['state_ref']}")
        if c.get("suggestion"):
            print(f"      建议: {c['suggestion']}")
        print()
    return 0


# ---------------------------------------------------------------------------
# beats
# ---------------------------------------------------------------------------
def _consistency_section(book, n: int, cur: dict, ents: list[dict], lines_st: dict,
                         plan_line: str = "", locked_st: dict | None = None) -> str:
    """beats「本章一致性速查」：不可逆事实台账 + 实体名册（含既有别名）+ KNO 知情差边界（引擎自动注入）。

    beats 是唯一同时被 Drafter / Editor / Reader 准读的文件——把账本记忆投递进 beats，
    即可在不动权限网关的前提下修复 Reader 的实体盲区（防别名分裂/另立新名），并防知情差与不可逆事实穿帮。
    名册来源：不可逆事实 + 主角 + 章末在场 + 到期线涉及实体 + 卷纲「当章预定规划」点名实体（防大纲回归角色漏网）。
    """
    proj = common.load_json(book / "project.json", default={}) or {}
    protagonist = str(proj.get("protagonist", "")).strip()
    ent_map = {}
    for e in ents or []:
        if isinstance(e, dict) and e.get("name"):
            ent_map[str(e["name"])] = e

    def _resolve(name: str):
        e = ent_map.get(name)
        if e:
            return e
        for ent in ent_map.values():
            if name and name in [str(a) for a in (ent.get("aliases") or [])]:
                return ent
        return None

    roster: list[dict] = []
    seen: set[str] = set()

    def _push(ent):
        if ent and ent.get("name") not in seen and len(seen) < 15:
            seen.add(ent["name"])
            roster.append(ent)

    _push(ent_map.get(protagonist))
    for name in (cur.get("present_characters") or []):
        _push(_resolve(str(name)))
    for arr in ("foreshadows", "misunderstandings", "knowledge"):
        for g in (lines_st or {}).get(arr, []):
            if str(g.get("status", "")).strip().lower() in ("resolved", "revealed"):
                continue
            t = g.get("target_ch")
            # 原过滤只收 `isinstance(t, int) and t <= n+3`，于是 `target_ch:
            # "longline"` 的全书级线索被整条剔除——那往往正是本书最重要的道具/主线
            # （实测《沧澜拾灯》的「无主空灯」规范名根本没进名册）。不跑 pack 的 Drafter
            # 只读 beats + 上章 final，就拿不到道具规范名，只能自己造词。
            # 现改为：近章（int 且 ≤ n+3）与全书级（longline / 非整数 target）都收。
            t_num = t if isinstance(t, int) else common.chapter_token_to_num(t)
            is_longline = not isinstance(t_num, int)
            if not (is_longline or t_num <= n + 3):
                continue
            blob = " ".join(str(g.get(k, "")) for k in
                            ("name", "content", "plan", "parties", "secret", "note"))
            for ename, ent in ent_map.items():
                if ename in seen:
                    continue
                if ename in blob or any(a and a in blob for a in (ent.get("aliases") or [])):
                    _push(ent)
    if plan_line:
        for ename, ent in ent_map.items():
            if ename in seen:
                continue
            if ename in plan_line or any(a and a in plan_line for a in (ent.get("aliases") or [])):
                _push(ent)

    kno_list = [k for k in (lines_st or {}).get("knowledge", [])
                if str(k.get("status", "")).strip().lower() != "revealed"]
    kno_list.sort(key=lambda k: -(k.get("weight") if isinstance(k.get("weight"), int) else 1))
    locked_entries = (locked_st or {}).get("entries", [])
    # 资源池在 ledger.json 的 pools 键下（十一表里没有 resources 这张表——
    # 此前误读 state/resources.json，异常被吞成空字典，于是恒报「尚无已声明资源池」）。
    ledger_err = ""
    try:
        res_st = state.load_state(book, "ledger") or {}
    except Exception as exc:  # 账本读不回来 ≠ 没有资源池，必须显式说出来
        res_st, ledger_err = {}, str(exc)
    pools = (res_st.get("pools", {}) if isinstance(res_st.get("pools", {}), dict) else {})
    # 键形状小节恒注入（见下）：Reader 的网关禁读 state/，它唯一的提案契约来源就是 beats。
    if not roster and not kno_list and not locked_entries and not pools:
        return _proposal_shapes_section()
    out = ["## 本章一致性速查（引擎自动注入 · 主控可增删）", ""]
    # 资源池合法键名 + LOCK 已用 ID 水位线：Reader 提案若引用未声明的池键或复用已用 ID，
    # Stage 5 会硬拒（ledger_pool_undeclared / locked_entry_id_reuse）——先给清单再让人写。
    if pools or locked_entries or ledger_err:
        out += ["### 💰 资源池与 ID 水位线（Reader 提案必填口径）", ""]
        if ledger_err:
            out.append(f"- ⚠️ 账本 ledger.json 读取失败，无法列出合法池键：{_clip(ledger_err, 120)}"
                       "（先修 state/ledger.json，否则本章流水的 pool 键名只能靠猜）")
        if pools:
            for pk in sorted(pools):
                # 落盘态余额字段是 current（引擎按流水重算写回），不是 balance
                bal = pools[pk].get("current", pools[pk].get("initial", 0))
                unit = pools[pk].get("unit", "")
                out.append(f"- 合法池键：`{pk}`（当前余额 {bal} {unit}）— 流水 `pool` 必须逐字等于此键")
        elif not ledger_err:
            out.append("- ⚠️ 尚无已声明资源池：本章流水必须 `kind=\"set\"` 建立首个池键（新键名需主控批准）")
        _lock_ids = sorted(str(e.get("id", "")) for e in locked_entries if e.get("id"))
        try:
            _cog_raw = state.load_state(book, "cognition") or {}
        except Exception:
            _cog_raw = {}
        _cog_ids = sorted(str(e.get("id", ""))
                          for e in (_cog_raw.get("entries") or []) if e.get("id"))
        if _lock_ids:
            out.append(f"- LOCK 已用 ID：{'、'.join(_lock_ids)} — 新增条目从水位线之后起号，严禁复用")
        if _cog_ids:
            out.append(f"- COG 已用 ID：{'、'.join(_cog_ids)} — 同上")
        out.append("- 复用同一 ID 重写旧条目会被 `locked_entry_id_reuse` 拒绝（改史走 `locked retire` 留痕）")
        out.append("")
    if locked_entries:
        out += ["### 🔒 不可逆事实台账（LOCK 引擎规范 · 严禁吃书/逆转）", ""]
        for le in locked_entries[:15]:
            lid = le.get("id", "LOCK")
            kind = le.get("kind", "fact")
            fact = _clip(str(le.get("fact", "")), 80)
            since = le.get("since_ch", "")
            since_part = f"（始于 {since}）" if since else ""
            out.append(f"- [{lid}] ({kind}) {fact}{since_part}")
        out.append("")
    if roster:
        out += ["### 实体名册（含既有别名——正文沿用既有写法，严禁另立新名碎片化实体）", ""]
        for ent in roster:
            eid_part = f"[{ent['id']}] " if ent.get("id") else ""
            aliases = "、".join(str(a) for a in (ent.get("aliases") or []) if a)
            name_part = f"{ent['name']}（别名：{aliases}）" if aliases else str(ent["name"])
            tier_info = ""
            tr = ent.get("tier_rank")
            tname = ent.get("tier_name") or ent.get("realm")
            if tr is not None or tname:
                tier_info = f" [Tier {tr if tr is not None else '?'}: {tname or '未定'}]"
            anchor_info = ""
            if ent.get("sensory_anchor"):
                anchor_info = f" ｜ 物象: {ent['sensory_anchor']}"
            mood_info = ""
            _mm = (cur.get("present_moods") or {}).get(ent["name"])
            if isinstance(_mm, dict) and _mm.get("label"):
                _lvl = f"·{_mm['level']}/5" if type(_mm.get("level")) is int else ""
                mood_info = f" ｜ 心境：{_mm['label']}{_lvl}"
            summary = _clip(str(ent.get("summary", "") or ""), 60)
            out.append(f"- {eid_part}{name_part}{tier_info} ｜ {ent.get('type', 'other')}"
                       f"{anchor_info}{mood_info} ｜ {summary}")
        out.append("")
    if kno_list:
        out += ["### 知情差边界（KNO 未揭示——对手戏严防「不该知道却说漏」穿帮）", ""]
        for k in kno_list[:6]:
            secret = _clip(str(k.get("secret", "")), 60)
            note = _clip(str(k.get("note", "") or "保密中"), 60)
            out.append(f"- [{k.get('id', 'KNO')}] 秘密：{secret} ｜ 知情边界：{note}")
        out.append("")
    out.append(_proposal_shapes_section())
    return "\n".join(out)


def _proposal_shapes_section() -> str:
    """beats「📐 提案通道与键形状」：把 v2/v3 契约搬进 Reader 的准读范围。

    动因：`state/inbox/README.md` 是提案契约的完整文本，但 Reader 的角色网关禁读
    `state/`（ROLE_DENY），`proposal new --v3` 又只给 `"ops": []` 空骨架——子代理被要求
    写一种它拿不到形状表的格式，只能凭记忆猜键名。本小节以 `state.models.ProposalModel`
    与 `proposal_v3.V3_OP_SHAPES` 为单一真源生成，与 v2/v3 管线同源，不再复制字面量。

    ch_001 实战补正：v2 分区**并不同构**（current/timeline/ledger/synopsis 是对象，
    entities/lines/locked/cognition/… 是裸数组），而 v3 的 op 载荷（`current`·update →
    `{"set":{…}}`、`timeline`·append_event → `{"event":{…}}`）此前紧接在 v2 分区名之后
    且无任何标注，Reader 极易把 op 载荷当成分区形状——实战即产出
    `cognition: {"entries":[…]}` 与 `current: {"set":{…}}`。现按两套契约分块标注。
    """
    import typing

    from .. import proposal_v3 as v3_mod
    from ..models import ProposalModel

    meta_only = {"schema_version", "chapter", "operation_id", "draft"}
    v2_secs = [k for k in ProposalModel.model_fields if k not in meta_only]

    def _v2_shape(key: str) -> str:
        """从字段注解推导 v2 分区形状（注解形如 `X | None`，需先解包 Optional）。"""
        ann = ProposalModel.model_fields[key].annotation
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        inner = args[0] if args else ann
        origin = typing.get_origin(inner)
        if origin in (list, tuple, set):
            return "裸数组 `[ … ]`"
        if origin is dict or inner is dict:
            return "对象 `{ … }`"
        if isinstance(inner, type) and hasattr(inner, "model_fields"):
            return "对象 `{ … }`"
        return ""

    lines = ["### 📐 提案通道与键形状（Stage 4 Reader 照此写；**不要**打开 state/inbox/README.md"
             "——那是主控/人类的完整契约，且在你的禁读范围内）", ""]
    lines.append("- 二选一、同一文件禁止混写：**默认 v2 分区**；"
                 "**本章要改 ≥2 个「已登记」实体（update/retire）→ 改 v3 寻址式**"
                 "（v3 的价值：名/ID 写错当场点名，不再静默新建碎片实体）。")
    lines.append("- v2 顶层：`{\"schema\":\"novel-studio.state-mutation/v2\",\"chapter\":\"ch_XXX\","
                 "\"operation_id\":\"ch_XXX.reader.HHMM\", …分区}` ｜ 分区："
                 + " / ".join(f"`{k}`" for k in v2_secs))
    lines.append("- **v2 分区形状（先看这张表，不要凭记忆猜）**——分区**不同构**：")
    for k in v2_secs:
        shape = _v2_shape(k)
        if shape:
            lines.append(f"  - `{k}` → {shape}")
    lines.append("  - 形状写错时报错会直接点名并给修法（如 `cognition 必须是数组（实际 dict）"
                 "——直接写条目列表，不要包成 {\"entries\": [...]}`），照修即可。")
    lines.append("- v3 顶层：`{\"schema\":\"…/v3\",\"chapter\",\"operation_id\",\"ops\":[{table,action,…}]}`；"
                 f"仅 v2 可用、无 v3 op 的分区：{'、'.join('`%s`' % x for x in v3_mod.V3_UNAVAILABLE_V2_ONLY)}")
    lines.append("  - ⚠️ **以下各行是 v3 的 `ops` 载荷形状，不是 v2 分区形状**。"
                 "同一个名字在两套契约里形状不同：v2 的 `current` 是**扁平字段字典**"
                 "（`{\"present_characters\":[…],\"situation\":\"…\"}`），"
                 "只有 v3 的 `current`·update 才写成 `{\"set\":{…}}`。")
    for table, action, shape in v3_mod.V3_OP_SHAPES:
        lines.append(f"  - `{table}` · {action} → `{shape}`")
    # ch_002 实战补正：分区形状（对象/裸数组）之外，Reader 还需要知道**条目能写哪些键**。
    # 此前这些白名单只存在于 state.validate_proposal 的局部字面量里，无任何途径可见，
    # Reader 于是照 cognition 的形状填 cognition_delta，换来 9 条「含未知字段」整案拒收。
    from ..models.timeline import ClockStatus, ClockUrgency
    from .. import state as state_mod

    lines.append("- **v2 分区条目字段（每条能写哪些键；写错会点名到 `分区[i] 含未知字段: xxx`）**：")
    for sec_name, keys, note in state_mod.v2_entry_contracts():
        lines.append(f"  - `{sec_name}` → {' / '.join('`%s`' % k for k in keys)} ｜ {note}")
    lines.append("- **`lines` 分区的按 kind 契约（动作不对会被点名）**：")
    for chunk in state_mod.v2_line_contracts():
        for sub in chunk.split("\n"):
            lines.append("  " + sub)
    lines.append("- `timeline.clocks[]`：`status` 只认大写开头 "
                 + " / ".join(f"`{x.value}`" for x in ClockStatus)
                 + "；`urgency` 只认小写 "
                 + " / ".join(f"`{x.value}`" for x in ClockUrgency) + "。")
    # ch_002 实战补正：kind 枚举此前从未文档化，Reader 只能猜——把「当场战死」填成了
    # irreversible_action，于是「已故角色仍在发言」探针按 kind=="death" 整条跳过、静默不检。
    # 枚举取自模型层 LockedKind（单一真源），不手抄。
    from typing import get_args

    from ..models.locked import LockedKind
    lines.append("- `locked[].kind` 只认 "
                 + " / ".join(f"`{k}`" for k in get_args(LockedKind))
                 + "。⚠️ **当场死亡一律填 `death`**"
                   "（填 `irreversible_action` 会让「已故角色仍在发言」探针整条跳过）；"
                   "`since_ch` 填本章号——填更晚的章号会被判为「该状态在本章尚未生效」。")
    lines.append("- 只写增量；每条尽量带 `\"quote\":\"本章 final 原句\"`（柔性接地，不逐字抠）。"
                 "`current` 缺省/空值＝不改；`locked[].note`、`lines[].target_ch`(plant) 必填。")
    lines.append("- 幂等：`operation_id` 全书唯一，同 id 换内容会被拒收——修正重提必须换新 id。")
    lines.append("- Reader 落盘即交卷、**不要**自己跑命令：结构预检由主控接收提案后执行"
                 "（0 Token 的 `python studio.py proposal check ch_XXX`），"
                 "报错会点名到 `entities[i] 含未知字段: xxx`，按名改再重提。")
    lines.append("")
    return "\n".join(lines)


def _clip(s: str, n: int) -> str:
    """定长截断并带省略号（ P2-15）。"""
    s = (s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


def cmd_beats(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    js = bool(getattr(args, "json", False))

    def _err(msg: str, code: int = 2, err_code: str = "usage") -> int:
        if js:
            print(json.dumps({"ok": False, "code": err_code, "error": msg},
                             ensure_ascii=False))
        else:
            print(f"❌ {msg}")
        return code

    ch = getattr(args, "chapter", None)
    if not ch:
        latest = common.latest_chapter_number(book, "final") or 0
        ch = f"ch_{latest + 1:03d}"
    # 归一化不再静默——`ch_7` 会被改写成 `ch_007` 并明确告知，
    # 避免与提案端（`target_ch` 必须是规范 ch_NNN）的严格度形成无声落差。
    tok, _rewrote = common.normalize_chapter_arg(ch)
    if not tok:
        return _err(f"无法解析章节号: {ch!r}")
    if _rewrote:
        note = f"ℹ️ 章号 {str(ch).strip()!r} 已归一为规范写法 {tok}" \
               "（提案 target_ch 等账本字段只接受规范 ch_NNN）"
        if js:
            print(note, file=sys.stderr)  # JSON 模式 stdout 零杂质
        else:
            print(note)
    n = common.chapter_token_to_num(tok)

    vol_str = "vol_01"
    matched = False
    max_seen = 0
    max_vol_num = 1
    for vdir in sorted((book / "outlines").glob("vol_*")):
        vm = common.VOL_RE.fullmatch(vdir.name)
        if vm:
            try:
                max_vol_num = max(max_vol_num, int(vm.group(1)))
            except ValueError:
                pass
        otext = (vdir / "outline.md").read_text(encoding="utf-8", errors="ignore") if (vdir / "outline.md").is_file() else ""
        m = re.findall(r"ch[_\-](\d{1,4})", otext)
        if m:
            try:
                lo, hi = int(m[0]), int(m[-1])
                max_seen = max(max_seen, hi)
                if lo <= n <= hi:
                    vol_str = vdir.name
                    matched = True
                    break
            except ValueError:
                pass
    if not matched and n > max_seen and max_seen > 0:
        # 跨卷自动晋升：当章号超出所有已有卷纲范围时，自动进入下一卷
        vol_str = f"vol_{max_vol_num + 1:02d}"
        # 若新卷目录不存在，beats 写入时会自动创建；卷纲占位由上层按需创建
        common.debug(f"beats vol routing: ch_{n:03d} 超出已有卷范围(最大 {max_seen})，自动晋升至 {vol_str}")

    beats_path = book / "outlines" / vol_str / "beats" / f"{tok}.md"
    drift_warning = ""
    if getattr(args, "write", False) and beats_path.exists() and not getattr(args, "force", False):
        return _err(f"{tok} beats 细纲已存在: {beats_path}（覆盖请加 --force）",
                    code=1, err_code="exists")
    if getattr(args, "write", False) and common.find_chapter_files(book, "final", tok):
        drift_warning = (f"该章已有定稿（manuscript/*/final/{tok}.md）——本次写入/覆盖细纲后，"
                         "正文与任务书可能版本漂移；若为回溯修订，请同步核对 final 与提案修订通道"
                         "（timeline 事件修订 / synopsis 跨章修订）")
        # --json 契约：文本警示不进 stdout（写盘分支已并入 payload.warning），仅文本模式即时输出
        if not getattr(args, "json", False):
            print(f"⚠️ {drift_warning}")

    proj = common.load_json(book / "project.json", default={}) or {}
    protagonist = proj.get("protagonist", "主角名")

    # form 默认值不再硬编码——上一章用了默认章型时切换推荐值，
    # 防「连续同章型无理由」在脚手架阶段就已埋雷
    default_form = "暗流汇聚"
    if n > 1:
        for pf in common.find_chapter_files(book, "beats", n - 1):
            prev_fm = common.parse_front_matter(pf.read_text(encoding="utf-8", errors="replace"))
            prev_form = str(prev_fm.get("form", "")).strip()
            if prev_form:
                for alt in ("危机逼近", "生死博弈", "战后清点", "暗流汇聚"):
                    if alt != prev_form:
                        default_form = alt
                        break
            break

    milestone = pack_mod._volume_phase_milestone(book, n)

    try:
        cur = state.load_state(book, "current")
    except (ValueError, OSError):
        cur = {}  # 现场快照不可用：脚手架相关注入留空
    sit = cur.get("situation", "")
    _sit_day = cur.get("time_day")
    if type(_sit_day) is int and str(sit).strip():
        sit = f"第{_sit_day}日·{sit}"

    try:
        lines_st = state.load_state(book, "lines")
    except (ValueError, OSError):
        lines_st = {}  # 线索账本不可用：到期区留默认占位
    try:
        ents_st = state.load_state(book, "entities").get("entries", [])
    except (ValueError, OSError):
        ents_st = []  # 实体账本不可用：名册留空
    try:
        locked_st = state.load_state(book, "locked")
    except (ValueError, OSError):
        locked_st = {}  # 不可逆台账不可用：留空

    due_lines_str = ""
    try:
        lines_st = state.load_state(book, "lines")
        due_items = []
        for g in lines_st.get("foreshadows", []):
            if str(g.get("status", "")).lower() != "resolved" and g.get("target_ch") == n:
                due_items.append(f"- {g.get('id')}（{g.get('name','')}）：本章到期，安排回收或回响")
        for m in lines_st.get("misunderstandings", []):
            if str(m.get("status", "")).lower() != "resolved" and m.get("target_ch") == n:
                due_items.append(f"- {m.get('id')}（{m.get('content','')[:24]}）：本章到期，安排澄清或激化")
        for k in lines_st.get("knowledge", []):
            if str(k.get("status", "")).lower() != "revealed" and k.get("target_ch") == n:
                due_items.append(f"- {k.get('id')}（{k.get('secret','')[:24]}）：本章计划揭示")
        if due_items:
            due_lines_str = "\n".join(due_items)
    except (ValueError, OSError):
        pass  # 线索账本不可用：到期区留默认占位
    if not due_lines_str:
        due_lines_str = "- （根据大纲按需 plant 新线或维持现状）"

    # 冷线提醒（A5）：已冷且近期（≤5 章）要到期的线——安排回收前先半句锚定。
    cold_hint_str = ""
    try:
        from .. import memory as memory_mod
        _mem_all = memory_mod.line_memory_map(book)
        cold_due = [r for r in _mem_all
                    if r["is_cold"] and isinstance(r.get("target_ch"), int)
                    and r["target_ch"] <= n + 5]
        cold_due.sort(key=lambda r: (r["target_ch"], -(r["gap"] or 0)))
        _hints = [
            f"- {r['id']}《{r['label']}》已 {r['gap']} 章未重现"
            f"（目标 ch_{r['target_ch']:03d}）——读者或已忘记，回收前先半句锚定旧事"
            for r in cold_due[:3]]
        # 长线心跳：无到期压力的跨卷长线久未重现——与 check 侧共用判定口径。
        _heart = checks.longline_stale_findings(_mem_all)
        _heart.sort(key=lambda r: -(r["gap"] or 0))
        _hints += [
            f"- {r['id']}《{r['label']}》已 {r['gap']} 章未重现（跨卷长线，无到期）"
            "——本章若无安排，顺手半句回响防读者遗忘"
            for r in _heart[:2]]
        cold_hint_str = "\n".join(_hints)
    except (ValueError, OSError):
        pass  # 读者记忆层不可用：冷线提醒留空，不阻断细纲装配

    tmpl_path = common.project_root() / "templates" / "beats.md"
    if not tmpl_path.is_file():
        return _err(f"细纲模板缺失: {tmpl_path}", code=1, err_code="engine")

    text = tmpl_path.read_text(encoding="utf-8")
    text = text.replace("{{slot:chapter_id}}", tok)
    text = text.replace("{{slot:vol_id}}", vol_str)
    text = text.replace("{{slot:form|暗流汇聚}}", default_form)
    text = text.replace("{{slot:protagonist|主角名}}", protagonist)
    text = text.replace("{{slot:tension_curve|动态起伏}}", "危机逼近 → 试探博弈 → 动作破局")
    text = text.replace("{{slot:tension_score|6}}", "6")
    text = text.replace("{{slot:stage_mode|Simmering}}", "Simmering")
    # 「所属阶段 + 上章现场」注入——此前 replace 的模板标记不存在，属静默 no-op 死代码；
    # 现在模板补了标记，并保留锚点回退，任何路径注入失败都走 stderr 警告（绝不静默）
    coord_block = (f"- **所属阶段**：{milestone or '（未匹配到分卷阶段，请核对 outlines/*/outline.md）'}\n"
                   f"- **上章现场**：{str(sit).strip() or '（暂无现场快照，按首章/转场处理）'}")
    coord_marker = "<!-- 双方不可退让的核心诉求与冲突点 -->"
    if coord_marker in text:
        text = text.replace(coord_marker, coord_block)
    elif "- **本章核心戏剧目标**：" in text:
        # 旧模板（无标记）回退：锚定「本章核心戏剧目标」行上方注入
        text = text.replace("- **本章核心戏剧目标**：",
                            coord_block + "\n- **本章核心戏剧目标**：", 1)
    else:
        # 兜底：frontmatter 之后的正文独立块 + stderr 明示（ P7：注入失败必须可见）。
        # 不能 prepend 到最顶——frontmatter 的 --- 必须保持首行
        block = f"## 本章坐标（引擎自动注入 · 可改）\n\n{coord_block}\n\n"
        fm_close = text.find("\n---", 3) if text.startswith("---") else -1
        insert_at = text.find("\n## ", fm_close + 1 if fm_close > 0 else 0)
        if insert_at > 0:
            text = text[:insert_at] + "\n" + block + text[insert_at:]
        else:
            text = block + text
        print("⚠️ beats 脚手架「所属阶段/上章现场」注入：模板标记与锚点均缺失，"
              "已回退到 frontmatter 后独立块——请人工核对位置", file=sys.stderr)
    text = re.sub(r"- GUN-XXX[^\n]*\n- KNO-XXX[^\n]*\n- MIS-XXX[^\n]*", due_lines_str, text)
    # 冷线提醒（A5）：追加到到期区之后（读者记忆轴信号，与到期台账互补）
    if cold_hint_str:
        text = text.replace(due_lines_str, due_lines_str + "\n\n**⚠️ 冷线提醒（已冷却且临近到期 / 长线心跳）**\n" + cold_hint_str, 1)

    # 一致性速查注入：实体名册（含别名，含卷纲规划行点名实体）+ KNO 知情差边界
    plan_line = ""
    m_plan = re.search(r"当章预定规划[:：](.+)", milestone or "")
    if m_plan:
        plan_line = m_plan.group(1).strip()
    cons_section = _consistency_section(book, n, cur, ents_st, lines_st, plan_line=plan_line,
                                        locked_st=locked_st)
    if cons_section:
        text = text.replace("## 本章新登场实体速写", cons_section.rstrip() + "\n\n## 本章新登场实体速写")

    # 自动对校并注入现场在场角色的法定互称矩阵
    try:
        from . import book_setup as book_setup_mod
        pres = list(cur.get("present_characters") or [])
        if protagonist and protagonist not in pres:
            pres.insert(0, protagonist)
        addr_lines = []
        if len(pres) >= 2:
            for i in range(len(pres)):
                for j in range(len(pres)):
                    if i != j:
                        p_from = book_setup_mod._get_entity_full_profile(book, pres[i])
                        p_to = book_setup_mod._get_entity_full_profile(book, pres[j])
                        if p_from and p_to:
                            addr = book_setup_mod._resolve_mutual_address(p_from, p_to)
                            if addr and addr != "(未在卡片登记)":
                                addr_lines.append(f"- 【{pres[i]} -> {pres[j]}】唯一指定法定称谓：「{addr}」")
        if addr_lines:
            addr_block = "\n".join(addr_lines)
            target_addr_marker = "- （若无特殊人物互动，保持默认；否则在此显式填写）"
            if target_addr_marker in text:
                text = text.replace(target_addr_marker, addr_block)
    except Exception:
        pass

    algo_str = ""
    try:
        algo_items = cockpit_mod.get_algorithmic_guidance(book, n)
        if algo_items:
            algo_str = "<!-- ⚙️ [确定性算法引擎动态制导胶囊]\n" + "\n".join(f"     - {item}" for item in algo_items) + "\n-->\n\n"
        else:
            algo_str = "<!-- ⚙️ [确定性算法制导] 角色登场密度均衡，张力波浪处于健康区间。 -->\n\n"
    except (ValueError, OSError):
        algo_str = ""  # 制导胶囊不可用：留静态占位

    if algo_str:
        target_marker = "<!-- 明确本章核心事件与矛盾推进，全篇采用直白好懂的大白话推进 -->"
        text = text.replace(target_marker, f"{algo_str}{target_marker}")

    if getattr(args, "write", False):
        beats_path.parent.mkdir(parents=True, exist_ok=True)
        common.atomic_write_text(beats_path, text)
        if getattr(args, "json", False):
            payload_out = {"chapter": tok, "written": beats_path.relative_to(book).as_posix()}
            if drift_warning:
                payload_out["warning"] = drift_warning
            print(json.dumps(payload_out, ensure_ascii=False))
        else:
            print(f"✅ 已生成 {tok} 细纲任务书脚手架：{beats_path.relative_to(book).as_posix()}")
        return 0
    else:
        if getattr(args, "json", False):
            print(json.dumps({"chapter": tok, "scaffold": text}, ensure_ascii=False, indent=2))
        else:
            print(f"# === {tok} 细纲任务书脚手架（加 --write 直接落盘）===\n")
            print(text)
        return 0



# ---------------------------------------------------------------------------
# critic
# ---------------------------------------------------------------------------
def cmd_critic(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    ch_arg = getattr(args, "chapter", None)
    if not ch_arg:
        latest = common.latest_chapter_number(book, "final") or 1
        ch_arg = f"ch_{latest:03d}"
    n = common.chapter_token_to_num(ch_arg)
    if not n:
        if getattr(args, "json", False):
            print(json.dumps({"chapter": str(ch_arg), "ok": False,
                              "error": f"无法解析章节号: {ch_arg!r}",
                              "code": "usage"}, ensure_ascii=False))
        else:
            print(f"❌ 无法解析章节号: {ch_arg!r}")
        return 2
    tok = f"ch_{n:03d}"
    critic_file = book / "log" / "critic" / f"{tok}.md"

    if critic_file.is_file():
        text = critic_file.read_text(encoding="utf-8", errors="ignore")
        # 骨架明示为「未评测」，不再以正式报告的口吻回显
        is_skeleton = "SKELETON" in text[:400]
        panel_title = (f"🧐 [催更便签骨架 · 未评测（Stage 4B 待 Critic 子代理改写）] {tok}"
                       if is_skeleton else f"🧐 [老白读者催更便签] {tok}")
        if getattr(args, "json", False):
            print(json.dumps({"chapter": tok, "skeleton": is_skeleton, "report": text},
                             ensure_ascii=False))
        elif _HAS_RICH and console:
            console.print(Panel(
                Markdown(text),
                title=f"[bold gold1]{panel_title}[/bold gold1]",
                border_style="cyan",
                padding=(1, 2)
            ))
        else:
            print("======================================================================")
            print(f" {panel_title}")
            print("======================================================================")
            print(text)
        return 0

    final_files = common.find_chapter_files(book, "final", n)
    if not final_files:
        if getattr(args, "json", False):
            print(json.dumps({"chapter": tok, "ok": False,
                              "error": f"未找到 {tok} 的定稿（final），无法进行读者评测（需先由 Stage 4C 定稿师 Fixer 落盘 final）",
                              "code": "no_final"}, ensure_ascii=False))
        else:
            print(f"❌ 未找到 {tok} 的定稿（final），无法进行读者评测（需先由 Stage 4C 定稿师 Fixer 落盘 final）")
        return 1

    final_text = final_files[-1].read_text(encoding="utf-8", errors="ignore")
    words = common.cjk_count(final_text)
    hook_info = evidence.detect_chapter_hook(final_text, evidence.hook_words(book))

    # 前情记忆（追更老白脑中）：取当前现场快照（Stage 4 跑在 sync 前 = 上一章末状态）
    memory_lines = []
    try:
        cur = state.load_state(book, "current")

        def _mem(label, key, sep="；"):
            v = cur.get(key)
            if isinstance(v, str) and v.strip():
                memory_lines.append(f"- **{label}**：{v.strip()[:40]}")
            elif isinstance(v, list) and v:
                memory_lines.append(f"- **{label}**：{sep.join(str(x) for x in v)[:60]}")

        where = "｜".join(x for x in (str(cur.get("time") or "").strip(),
                                      str(cur.get("location") or "").strip()) if x)
        if where:
            memory_lines.append(f"- **时地**：{where[:60]}")
        _mem("伤势", "injury")
        _mem("处境", "situation")
        _mem("心境", "mood")
        _mem("目标", "goal")
        _mem("悬顶危机", "active_pressures")
        _mem("上章余震", "aftershock")
        _mem("在场角色", "present_characters")
    except (ValueError, FileNotFoundError):
        memory_lines = ["- （暂无前情记忆：现场快照不可用，按首章读者处理）"]
    memory_block = "\n".join(memory_lines) if memory_lines else "- （无显著前情记忆）"

    skeleton = f"""# 第{n}章 老白读者催更便签（SKELETON 未评测 · 引擎预填骨架）

<!-- ⚠️ SKELETON：本文件由引擎预填机械数据与前情记忆，所有「（待评）」字段必须由
     Stage 4B Critic 子代理盲审后改写；在 Critic 交卷前，本文件不视为正式便签，
     cockpit 也不将其计为 Stage 4B 完成。 -->

- 💬 **本章体感**：（待评）
- 🌊 **阅读疲劳度**：（待评——紧绷/松弛？下章该爆发/蓄水还是日常清点缓冲？）
- 🔍 **伏笔与信息差**：（待评——暗线透光度如何？是否藏太深快被读者遗忘？）
- 🌡️ **主角活人感**：（待评——有无七情六欲的活人感？有无滑向冷酷装逼/说教AI的苗头？）
- 💖 **角色路人缘**：（待评——女主/重要配角/反派的真实路人缘与好感度走向）
- 🚩 **连续性红旗**：（待评——若有：与前情记忆冲突的断戏感，最多 2 条且必须引用下方记忆字段值）

## 🧠 前情记忆（追更老白脑中 · 来自 state/current.json 快照）
{memory_block}

## 📊 机械参考数据（引擎只出数，零裁决）
- **评测章节**：{tok}
- **字数统计**：{words} 汉字
- **章末钩子**：{hook_info.get('type', '普通收尾')}（{hook_info.get('detail', '')[:30]}）
"""
    if getattr(args, "write", False):
        critic_file.parent.mkdir(parents=True, exist_ok=True)
        common.atomic_write_text(critic_file, skeleton)
        if getattr(args, "json", False):
            print(json.dumps({"chapter": tok, "skeleton": True,
                              "written": critic_file.relative_to(book).as_posix()},
                             ensure_ascii=False))
        else:
            print(f"✅ 催更便签骨架（SKELETON）已落盘: {critic_file.relative_to(book).as_posix()}")
            print("   ⚠️ 骨架不替代 Stage 4B 评审：请派发 Critic 子代理盲审改写后再进下章细纲（cockpit 不把骨架计为已完成）。")
        return 0
    else:
        if getattr(args, "json", False):
            print(json.dumps({"chapter": tok, "exists": False,
                              "note": f"{tok} 尚未执行老白读者评测（Stage 4B 待 Critic 子代理评审）",
                              "hint": f"python studio.py critic {tok} --write 可落盘预填骨架（SKELETON）"},
                             ensure_ascii=False))
        else:
            print(f"ℹ️ {tok} 尚未执行老白读者评测。")
            print("   正道：主控在 Stage 4 派发子代理 `Role: 'Critic'` 并行评审（零脚本、盲审便签）。")
            print(f"   引擎辅助：python studio.py critic {tok} --write 可落盘预填骨架（SKELETON，供子代理改写，不计完成）。")
        return 0



# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------
def cmd_graph(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    return graph_mod.run_graph(
        book,
        getattr(args, "graph_action", None),
        as_json=bool(getattr(args, "json", False)),
        source=getattr(args, "source", ""),
        target=getattr(args, "target", ""),
        name=getattr(args, "name", ""),
        depth=getattr(args, "depth", 1),
    )


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
def cmd_export(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    if not args.txt and not args.views:
        args.txt = args.views = True
    written = []
    try:
        if args.txt:
            written.append(pack_mod.export_txt(book))
        if args.views:
            written.append(pack_mod.export_views(book))
    except (ValueError, FileNotFoundError) as exc:
        print(f"❌ 导出失败: {exc}")
        return 1
    if args.json:
        print(json.dumps({"written": [str(p.relative_to(book)) for p in written]}, ensure_ascii=False))
    else:
        for p in written:
            size = len(p.read_text(encoding="utf-8"))
            print(f"📦 已导出: {p.relative_to(book)}（{size} 字符）")
    return 0


# ---------------------------------------------------------------------------
# ask / pov / calendar（只读取证三件套：写作前先问书，严禁凭记忆脑补）
# ---------------------------------------------------------------------------
def cmd_ask(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    query = str(getattr(args, "query", "") or "").strip()
    payload = evidence.ask(book, query)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if payload.get("error") else 0


def cmd_pov(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    payload = evidence.pov(book, str(getattr(args, "name", "") or ""))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 2 if payload.get("error") else 0


def _calendar_payload(book, span: int) -> dict:
    """未来 N 章排产日历：到期线/危机时钟/阶段里程碑投影（advisory）。"""
    target = cockpit_mod._infer_active_chapter(book)
    start = common.chapter_token_to_num(target) or 1
    out: dict = {"kind": "calendar", "start": f"ch_{start:03d}", "span": span, "chapters": []}
    try:
        lines = state.load_state(book, "lines")
    except (ValueError, FileNotFoundError):
        lines = {}
    try:
        tl = state.load_state(book, "timeline")
    except (ValueError, FileNotFoundError):
        tl = {}
    resolved_status = {"foreshadows": "resolved", "misunderstandings": "resolved",
                       "knowledge": "revealed"}

    def _desc(g):
        return str(g.get("name") or g.get("content") or g.get("secret") or "")[:36]

    overdue = []
    for arr, kind in (("foreshadows", "伏笔"), ("misunderstandings", "误会"), ("knowledge", "知识线")):
        for g in lines.get(arr, []):
            t = g.get("target_ch")
            if (isinstance(t, int) and t < start
                    and str(g.get("status", "")).strip().lower() != resolved_status[arr]):
                overdue.append({"id": g.get("id"), "kind": kind, "target_ch": t, "desc": _desc(g)})
    if overdue:
        out["overdue_lines"] = overdue
    clocks_overdue = [{"name": c.get("name"), "target_ch": c.get("target_ch"),
                       "desc": str(c.get("desc", ""))[:40]}
                      for c in tl.get("clocks") or []
                      if str(c.get("status", "")).lower() == "active"
                      and isinstance(c.get("target_ch"), int) and c["target_ch"] < start]
    if clocks_overdue:
        out["overdue_clocks"] = clocks_overdue
    # 跨卷长线节：无到期章号的线此前在日历上完全不可见（排产盲区）——单列一节，
    # 让主控在排产时看到「这些线没有 deadline，最容易被遗忘」。
    longlines = []
    for arr, kind in (("foreshadows", "伏笔"), ("misunderstandings", "误会"), ("knowledge", "知识线")):
        for g in lines.get(arr, []):
            t = g.get("target_ch")
            if (not isinstance(t, int) and common.chapter_token_to_num(t) is None
                    and str(g.get("status", "")).strip().lower() != resolved_status[arr]):
                longlines.append({"id": g.get("id"), "kind": kind, "desc": _desc(g),
                                  "target_ch": t, "plant_ch": g.get("plant_ch")})
    if longlines:
        out["longlines"] = longlines

    for n in range(start, start + span):
        tok = f"ch_{n:03d}"
        row: dict = {"chapter": tok,
                     "beats_planned": bool(common.find_chapter_files(book, "beats", tok))}
        phase = pack_mod._volume_phase_milestone(book, n)
        if phase:
            row["phase"] = phase
        due = []
        for arr, kind in (("foreshadows", "伏笔"), ("misunderstandings", "误会"), ("knowledge", "知识线")):
            for g in lines.get(arr, []):
                if (g.get("target_ch") == n
                        and str(g.get("status", "")).strip().lower() != resolved_status[arr]):
                    due.append({"id": g.get("id"), "kind": kind, "desc": _desc(g)})
        if due:
            row["due_lines"] = due
        clocks = [{"name": c.get("name"), "desc": str(c.get("desc", ""))[:40]}
                  for c in tl.get("clocks") or []
                  if str(c.get("status", "")).lower() == "active" and c.get("target_ch") == n]
        if clocks:
            row["clocks"] = clocks
        out["chapters"].append(row)
    out["notes"] = ["排产参考（advisory）：due_lines=预定本章结算的线；phase=卷阶段航标；"
                  "longlines=跨卷长线（无到期，排产时顺手安排回响防遗忘）；兑付节奏归主控裁决。"]
    return out


def cmd_calendar(args) -> int:
    book = ws_gate(args)  # --json 错误路径也出 JSON 信封
    if book is None:
        return ws_gate_code()
    try:
        span = int(getattr(args, "span", None) or 5)
    except (TypeError, ValueError):
        span = 5
    span = max(1, min(span, 12))
    print(json.dumps(_calendar_payload(book, span), ensure_ascii=False, indent=2))
    return 0