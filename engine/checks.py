"""check：结构 + schema + 算术体检（吸收旧 doctor/verify/audit；errors 只允许事实级）。

语义红线 ：
- errors：可机械判定必须修复的事实——schema 违规、引用未登记实体、章号断档、占位符未填、
  同 form 无理由、账本重算不符（state.verify_state）。
- warnings：算术数出来的偏离事实（字数出带、线逾期、tics 命中、form 占比超 40%）——只报数，
  是否修、怎么修由主控决定。
- 两个桶里都不许出现「建议/疑似/不宜」等判断词；本模块零写入。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import common, evidence, state

SLOT_RE = re.compile(r"\{\{\s*slot:")
CANDIDATE_RE = re.compile(r"candidate_[0-9A-Za-z_*]")
FORM_SHARE_LIMIT = 0.40


def _err(code: str, msg: str) -> dict:
    return {"code": code, "msg": msg}


_BEATS_FM_KEYS = {"chapter", "vol", "form", "pov", "words", "style_notes", "form_reason",
                  "guard_extra", "tension_curve"}

# 空判据词表（形容词类判据的机械近似；与 evidence.AI_CONSTRUCTIONS 同一精神——
# 只数固定清单。通用形容词识别属语义，引擎不做；书级可用 project.json.empty_criteria_words 追加）。
EMPTY_CRITERIA_WORDS = ["读者", "感到", "觉得", "紧张", "揪心", "感动", "震撼",
                        "代入感", "沉浸", "氛围感", "真实感", "节奏感", "余味", "回味"]

_WORDS_BAND_RE = re.compile(r"(\d+)\s*[-–—~～]\s*(\d+)")


def _words_band(s: str) -> tuple[int | None, int | None]:
    """'2400-3500' → (2400, 3500)；解析不出 → (None, None)。"""
    m = _WORDS_BAND_RE.search(s or "")
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _style_knobs(s: str) -> tuple[str, ...]:
    """style_notes 竖线分旋钮（全同=复印机的比较键）。"""
    return tuple(p.strip() for p in re.split(r"[|｜]", s or "") if p.strip())


def _numbered_items(lines: list[str]) -> dict[int, str]:
    """`N.`/`N、`起头的行 → {序号: 整行及后续缩进/子行内容}（跳空行，只认节内）。"""
    out: dict[int, str] = {}
    current_num = None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        m = re.match(r"^(\d+)[.、]\s*(.*)$", s)
        if m:
            current_num = int(m.group(1))
            out[current_num] = s
        elif current_num is not None:
            out[current_num] += " " + s
    return out


def review_gate(book: Path, ch: str) -> list[str]:
    """Stage 4 合同（机械层）：必须有校对注记；「验收」节须逐条答完任务书「验收」。

    只数行与符号：无注记 → 拦（Stage 4 封存前提，见 novel_workflow.md#Stage 4）；
    注记缺「## 验收」→ 拦；beats 有验收条目 → 缺答/缺✓✗/无证据 = 拒绝封存。
    guard 不写注记、不答验收。
    """
    beats = [f for f in common.find_chapter_files(book, "beats")
             if common.chapter_number_from_name(f.name) == common.chapter_token_to_num(ch)]
    k = 0
    if beats:
        acc = common.md_section(beats[0].read_text(encoding="utf-8", errors="replace"), r"^##\s*(?:.*验收|.*契约)")
        k = max(_numbered_items(acc), default=0)
    rev = book / "log" / "review" / f"{ch}.md"
    if not rev.is_file():
        extra = f"；beats「验收」共 {k} 条" if k else ""
        return [f"校对注记 {ch}.md 不存在（Stage 4 未留注记；拒封存{extra}）"]
    rtext = rev.read_text(encoding="utf-8", errors="replace")
    issues: list[str] = []
    if not re.search(r"^##\s*(?:.*验收|.*契约)", rtext, re.M):
        issues.append("校对注记缺「## 验收」或「## 交付契约」节")
    items = _numbered_items(common.md_section(rtext, r"^##\s*(?:.*验收|.*契约)"))
    missing = [n for n in range(1, k + 1) if n not in items]
    if missing:
        issues.append(f"验收 {missing} 未被校对注记回答（共 {k} 条，须逐条 N. ✓/✗+证据）")
    # 证据判定（novel_craft.md#打磨与校对）：每条结论必须带证据——正文引文，或 evidence 字段名+数值。
    # 不再用"整行 ≥24 字符"的任意长阈值（会误伤语句精炼但已给引文/数值的证据）。
    EVIDENCE_QUOTE_RE = re.compile(r"[「“\"'『]")          # 引号 = 正文引文
    EVIDENCE_FIELD_RE = re.compile(r"[A-Za-z_][\w]*[:：]\s*[\d.]+|[A-Za-z_]+\s*=\s*[\d.]+")  # 字段:值
    for n, line in sorted(items.items()):
        if not re.search(r"[✓✗×√]", line):
            issues.append(f"验收 {n} 无 ✓/✗ 判定符")
        elif not (EVIDENCE_QUOTE_RE.search(line) or EVIDENCE_FIELD_RE.search(line)):
            issues.append(f"验收 {n} 打了判定符但无证据（须含正文引文或 evidence 字段名+数值）")
    return issues


def review_skeleton(book: Path, ch: str) -> dict:
    """校对注记骨架数据（Stage 4）：验收条目/必须保留自 beats 提取，机器数据逐项预填。
    纯提取/计数——每项的「结果」与证据仍由主控填写；零裁决。"""
    n = common.chapter_token_to_num(ch)
    if not n:
        raise ValueError(f"非法章号: {ch!r}")
    tok = f"ch_{n:03d}"
    beats_files = [f for f in common.find_chapter_files(book, "beats")
                   if common.chapter_number_from_name(f.name) == n]
    if not beats_files:
        raise ValueError(f"未找到 {tok} 的 beats（Stage 1 未完成，无任务书可对照）")
    final_files = common.find_chapter_files(book, "final", n)
    if not final_files:
        raise ValueError(f"未找到 {tok} 的 final（注记对象缺失）")
    text = beats_files[-1].read_text(encoding="utf-8", errors="replace")
    ftext = final_files[-1].read_text(encoding="utf-8", errors="replace")
    fm = common.parse_front_matter(text)
    acc: list[str] = []
    for ln in common.md_section(text, r"^##\s*(?:.*验收|.*契约)"):
        m = re.match(r"^\s*(\d+)[.、]\s*(.+)$", ln.strip())
        if m:
            acc.append(m.group(2).strip())
    must = [ln.strip().lstrip("-*· ").strip() for ln in common.md_section(text, r"^##\s*(?:必须保留|.*契约)")]
    must = [s for s in must if s and not s.startswith(("<", "#"))]
    led = state.load_state(book, "ledger")
    cur = state.load_state(book, "current")
    ents = state.load_state(book, "entities").get("entries", [])
    return {
        "chapter": tok,
        "form": fm.get("form", ""),
        "words": fm.get("words", ""),
        "acceptance": acc,
        "must_keep": must,
        "present": cur.get("present_characters", []),
        "proper_names": [{"name": e["name"],
                          "aliases": [a for a in e.get("aliases", []) if a]}
                         for e in ents if e.get("status", "active") == "active"],
        "ledger_now": {pid: p for pid, p in (led.get("pools") or {}).items()},
        "quote_balance": {q: ftext.count(q) for q in "「」“”『』"},
        "residue": {"slot": len(re.findall(r"\{\{\s*slot:", ftext)),
                    "candidate": len(re.findall(r"candidate_", ftext))},
    }


def proposal_cross_facts(book: Path, ch: str, proposal: dict) -> dict:
    """提案×final×状态 三方对照：只出机械事实，零裁决措辞（是否上账归主控）。"""
    n = common.chapter_token_to_num(ch)
    facts: dict = {}
    if not isinstance(proposal, dict) or not n:
        return facts
    chs = [text for _, num, text in evidence.final_chapters(book) if num == n]
    if chs:
        text = chs[0]
        led = state.load_state(book, "ledger")
        facts["amounts_in_final"] = evidence._amount_scan(text, led.get("pools"))
        facts["ledger_tx_in_proposal"] = len((proposal.get("ledger") or {}).get("transactions") or [])
        lookup = evidence.entity_lookup(book)
        per = {}
        for name, aliases in lookup.items():
            c = sum(evidence.count_aliases(text, aliases).values())
            if c:
                per[name] = c
        facts["present_mentions"] = per
    lines = state.load_state(book, "lines")
    due = []
    for arr, resolved in (("foreshadows", "Resolved"), ("misunderstandings", "Resolved"),
                          ("knowledge", "Revealed")):
        for g in lines.get(arr, []):
            t = g.get("target_ch")
            if g.get("status") != resolved and isinstance(t, int) and t <= n:
                due.append({"id": g["id"], "target_ch": t})
    facts["due_lines"] = due
    ops = sorted({str(g.get("id")) for g in (proposal.get("lines") or [])
                  if isinstance(g, dict) and g.get("id") and g.get("action", "plant") != "plant"})
    facts["lines_ops_in_proposal"] = ops
    # 知识线揭示时机对照：提案标记 KNO 揭示 × 台账计划揭示章（纯算术比数，提前/逾期归主控）
    ledger_kno = {str(k.get("id")): k for k in lines.get("knowledge", [])}
    timing = []
    for g in (proposal.get("lines") or []):
        if not isinstance(g, dict) or g.get("kind") != "knowledge" or g.get("action") != "resolve":
            continue
        k = ledger_kno.get(str(g.get("id")))
        if not k:
            continue
        t = k.get("target_ch")
        if isinstance(t, int) and t != n:
            timing.append({"id": str(g.get("id")), "planned_ch": t, "chapter": n, "early": n < t})
    if timing:
        facts["kno_reveal_timing"] = timing
    facts["present_in_proposal"] = list(((proposal.get("current") or {}).get("present_characters") or []))
    return facts


def run_checks(book: Path) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    stats: dict = {}

    # ---- project.json ----
    proj_path = book / "project.json"
    proj: dict = {}
    if not proj_path.exists():
        errors.append(_err("project_missing", f"缺 project.json: {book}（先运行 init）"))
    else:
        try:
            proj = common.load_json(proj_path)
        except (ValueError, OSError) as exc:
            errors.append(_err("project_corrupt", f"project.json 解析失败: {exc}"))
    for field in ("title", "genre"):
        if proj and not str(proj.get(field, "")).strip():
            errors.append(_err("project_field_empty", f"project.json.{field} 为空"))
    band = proj.get("words_target")
    band_ok = isinstance(band, list) and len(band) == 2 and all(isinstance(x, int) for x in band)
    if proj and "words_target" in proj and not band_ok:
        errors.append(_err("project_field_type", "project.json.words_target 必须是 [下限, 上限] 整数对"))

    # ---- 状态层（schema + 账本重算 + 唯一性，sync 前同款体检） ----
    for msg in state.verify_state(book):
        errors.append(_err("state_inconsistent", msg))

    # ---- 实体引用闭合（current.present_characters ∈ 注册表名/别名） ----
    try:
        ents = state.load_state(book, "entities")["entries"]
        known = set()
        for e in ents:
            known.add(str(e.get("name", "")))
            known.update(str(a) for a in e.get("aliases", []) if a)
        cur = state.load_state(book, "current")
        for name in cur.get("present_characters", []):
            if str(name).strip() and str(name) not in known:
                errors.append(_err("unregistered_character",
                                   f"current.present_characters 引用未登记实体「{name}」"
                                   "（先在 entities 提案注册，名字须与卡一致）"))
        # retired 实体上台：retired=退场/死亡，仍在 present = 事实矛盾（闪回章由主控判读）
        retired = set()
        for e in ents:
            if e.get("status") == "retired":
                retired.add(str(e.get("name", "")))
                retired.update(str(a) for a in e.get("aliases", []) if a)
        for name in cur.get("present_characters", []):
            if str(name) in retired:
                warnings.append(_err("retired_entity_on_stage",
                                     f"current.present_characters 含已退休实体「{name}」"
                                     "（retired=退场/死亡——闪回/补叙章可忽略，否则移出 present 或改回 active）"))
    except (ValueError, FileNotFoundError) as exc:
        errors.append(_err("state_unreadable", str(exc)))

     # ---- 稿件结构：final 章号断档 / 同版本号重复（一章多版本是合法溯源，只取版本最大者）----
    # 分组键 = (卷, 章号, 版本号)：跨卷同章号互不覆盖（vol_02/ch_001 合法），
    # 仅同卷、同章号、同版本号出现多份定稿 = 真正重复。
    final_files = common.find_chapter_files(book, "final")
    ver_by_ch: dict[tuple[str, int], dict[int, list[Path]]] = {}
    for f in final_files:
        n = common.chapter_number_from_name(f.name)
        if n is not None:
            try:
                vol = f.relative_to(book / "manuscript").parts[0]
            except ValueError:
                vol = ""
            v = common.chapter_version_from_name(f.name)
            ver_by_ch.setdefault((vol, n), {}).setdefault(v, []).append(f)
    per_ch: dict[tuple[str, int], Path] = {}
    for (vol, n), vers in sorted(ver_by_ch.items()):
        # 同一版本号出现多个文件 = 真正重复；不同版本号 = 审计留痕（v2/v10），取版本号最大者。
        dup = [f for fs in vers.values() if len(fs) > 1 for f in fs]
        if dup:
            errors.append(_err("duplicate_final",
                               f"{vol} 第{n}章同版本号有多份定稿: {', '.join(f.name for f in dup)}"))
        top = max(vers)
        per_ch[(vol, n)] = vers[top][0]
    # 断档按卷检查：只对已有定稿的卷判断连续区间，避免把卷间间隙误判。
    vol_nums: dict[str, list[int]] = {}
    for (vol, n) in per_ch:
        vol_nums.setdefault(vol, []).append(n)
    for vol, nums in sorted(vol_nums.items()):
        missing = sorted(set(range(min(nums), max(nums) + 1)) - set(nums))
        if missing:
            errors.append(_err("final_gap_chapters",
                               f"{vol} final 章号断档: {missing}（第 {min(nums)} 与 {max(nums)} 章之间无定稿）"))
    stats["final_chapters"] = len(per_ch)

    # ---- 占位符：槽位未实例化禁止入流水线 ----
    slot_hits = []
    for md in sorted(book.rglob("*.md")):
        try:
            if SLOT_RE.search(md.read_text(encoding="utf-8", errors="ignore")):
                slot_hits.append(str(md.relative_to(book)))
        except OSError:
            continue
    for rel in slot_hits:
        errors.append(_err("unfilled_slot", f"{rel} 存在未填充槽位 {{{{slot:...}}}}（Stage 0 未完成）"))

    # ---- 禁令5：稿件禁工程痕迹（candidate_* 泄漏进 manuscript）----
    ms = book / "manuscript"
    if ms.is_dir():
        for md in sorted(ms.rglob("*.md")):
            try:
                if CANDIDATE_RE.search(md.read_text(encoding="utf-8", errors="ignore")):
                    errors.append(_err("candidate_leak",
                        f"{md.relative_to(book)} 含 candidate_* 工程痕迹（AGENTS 禁令5：禁入稿件）"))
            except OSError:
                continue

    # ---- beats 协议（机械部分）：同 form 连章必须给理由；form 缺失；超键拦截；
    #      上章对照与自交检报数（style_notes 全同 / words 带贴近 / 空判据词 / 线动作对照）----
    beats = sorted(common.find_chapter_files(book, "beats"),
                   key=lambda p: (p.parts[-3] if len(p.parts) > 2 else "",
                                  common.chapter_number_from_name(p.name) or 0))
    ledger_line_ids: set[str] = set()
    open_due: list[tuple[int, str]] = []  # (target_ch, id)：未结且有整数到期章的线
    try:
        _lines_state = state.load_state(book, "lines")
        for _arr, _resolved in (("foreshadows", "Resolved"), ("misunderstandings", "Resolved"),
                                ("knowledge", "Revealed")):
            for _g in _lines_state.get(_arr, []):
                _gid = str(_g.get("id", ""))
                if _gid:
                    ledger_line_ids.add(_gid)
                if _g.get("status") != _resolved and isinstance(_g.get("target_ch"), int):
                    open_due.append((_g["target_ch"], _gid))
    except (ValueError, FileNotFoundError):
        pass  # lines 不可读已在 state_inconsistent 报 error；线对照降级为不跑
    empty_words = list(EMPTY_CRITERIA_WORDS)
    empty_words += [w for w in (proj.get("empty_criteria_words") or [])
                    if isinstance(w, str) and w.strip() and w not in empty_words]
    prev_by_vol: dict[str, dict] = {}
    for f in beats:
        text = f.read_text(encoding="utf-8", errors="replace")
        fm = common.parse_front_matter(text)
        vol = f.relative_to(book / "outlines").parts[0]
        extra = set(fm) - _BEATS_FM_KEYS
        if extra:
            errors.append(_err("beats_fm_extra_keys",
                               f"{f.name}: front-matter 含未定义键 {sorted(extra)}"
                               f"（合法键 {sorted(_BEATS_FM_KEYS)}；工程痕迹禁入稿——AGENTS 禁令5）"))
        num = common.chapter_number_from_name(f.name) or 0
        form = fm.get("form", "")
        if not form:
            errors.append(_err("beats_missing_form", f"{f.name}: front-matter 缺 form 字段（Stage 1 未选章型）"))
        cur_notes = _style_knobs(fm.get("style_notes"))
        cur_lo, _ = _words_band(fm.get("words"))
        last = prev_by_vol.get(vol)
        if last and last["num"] == num - 1:
            if form and last.get("form") == form and not fm.get("form_reason"):
                errors.append(_err("beats_form_repeat_without_reason",
                                   f"{f.name}: 与上一章同 form「{form}」但 front-matter 未写 form_reason"))
            if cur_notes and cur_notes == _style_knobs(last.get("notes")):
                warnings.append(_err("style_notes_copy",
                                     f"{f.name}: style_notes 三旋钮与上一章全同「{fm.get('style_notes','')}」"
                                     "（novel_craft.md#反公式化与拟人化：三个全同=复印机）"))
            prev_lo = _words_band(last.get("words"))[0]
            if prev_lo is not None and cur_lo is not None and 0 < abs(cur_lo - prev_lo) < 400:
                warnings.append(_err("words_band_crowded",
                                     f"{f.name}: words 带下限 {cur_lo} 与上一章 {prev_lo} 仅差 "
                                     f"{abs(cur_lo - prev_lo)}（微调幅度过小，建议维持同级或拉开差距）"))
        prev_by_vol[vol] = {"num": num, "form": form,
                            "notes": fm.get("style_notes", ""), "words": fm.get("words", "")}
        crit_hits: list[str] = []
        for sec_pat in (r"^##\s*(?:.*目标|核心目标)", r"^##\s*(?:.*验收|.*契约)"):
            for ln in common.md_section(text, sec_pat):
                s = ln.strip()
                if not s or s.startswith(("#", "<")):
                    continue
                for w in empty_words:
                    if w in s and w not in crit_hits:
                        crit_hits.append(w)
        if crit_hits:
            warnings.append(_err("acceptance_empty_criterion",
                                 f"{f.name}: 目标/验收含空判据词 {'、'.join(crit_hits[:5])}"
                                 "（判据用动词+可指认名词，novel_craft.md#句式与语域词汇）"))
        action_sec = "\n".join(common.md_section(text, r"^##\s*(?:.*线动作|伏笔与线动作)"))
        orphans = sorted(set(re.findall(r"(?:GUN|MIS|KNO)-\d{3,}", action_sec)) - ledger_line_ids)
        if orphans:
            warnings.append(_err("line_action_orphan",
                                 f"{f.name}: 线动作栏引用台账不存在的线 {', '.join(orphans[:5])}"
                                 "（先 plant 或核对 ID）"))
        missing = sorted({gid for t, gid in open_due if t <= num and gid not in action_sec})
        if missing:
            warnings.append(_err("line_action_missing",
                                 f"{f.name}: 到期/逾期线 {', '.join(missing[:5])} 未出现在「线动作」栏"
                                 "（不还须写顺延理由，novel_workflow.md#Stage 1）"))

    # ---- 流程事实（warn 级）：final 无 raw / 无 beats ----
    # 与 final 的 per_ch 同口径，按 (卷, 章号) 键控：跨卷同章号互不覆盖，
    # 避免 vol_02/ch_001 的缺口被 vol_01/ch_001 的原料"顶掉"而漏报。
    def _vol_nums(area: str) -> set[tuple[str, int]]:
        out = set()
        for f in common.find_chapter_files(book, area):
            n = common.chapter_number_from_name(f.name)
            if n is None:
                continue
            base = book / ("outlines" if area == "beats" else "manuscript")
            try:
                vol = f.relative_to(base).parts[0]
            except ValueError:
                vol = ""
            out.add((vol, n))
        return out

    raw_nums = _vol_nums("raw")
    beats_nums = _vol_nums("beats")
    for (vol, n) in sorted(per_ch):
        tok = f"ch_{n:03d}"
        if (vol, n) not in raw_nums:
            warnings.append(_err("final_without_raw", f"{tok}: 有定稿但无 raw 草稿（流程事实，供核对）"))
        if (vol, n) not in beats_nums:
            warnings.append(_err("final_without_beats", f"{tok}: 有定稿但无 beats 细纲（流程事实，供核对）"))

    # ---- 字数带偏离（只报数：beats words / project.words_target 都是手感带，不阻断封存） ----
    if band_ok:
        lo, hi = band
        for tok, _, text in evidence.final_chapters(book):
            c = common.cjk_count(text)
            if c < lo or c > hi:
                warnings.append(_err("word_band_deviation", f"{tok}: 字数 {c} 在目标带 [{lo}, {hi}] 之外"))


    # ---- 线逾期（算术事实） ----
    try:
        g = evidence.gaps(book)
        for item in g["foreshadows"] + g["misunderstandings"] + g.get("knowledge", []):
            if item["overdue"]:
                warnings.append(_err(
                    "line_overdue",
                    f"{item['id']}: target_ch={item['target_ch']} < 已定稿 "
                    f"{g['max_final_chapter']} 章"))
    except (ValueError, FileNotFoundError) as exc:
        errors.append(_err("state_unreadable", f"lines 不可读: {exc}"))

    # ---- tics 命中（project.style_guards × 定稿正文，纯计数） ----
    guards = [x for x in (proj.get("style_guards") or []) if isinstance(x, str) and x]
    if guards:
        for tok, _, text in evidence.final_chapters(book):
            for gtxt in guards:
                c = text.count(gtxt)
                if c:
                    warnings.append(_err("style_guard_hit",
                                         f"{tok}: 「{gtxt}」出现 {c} 次"))

    # ---- form 占比（>40% 卷内，仅当卷内已达到 5 章以上样本时统计） ----
    for vol, rec in evidence.form_distribution(book).items():
        if rec.get("count", 0) < 5:
            continue
        for form, share in rec.get("shares", {}).items():
            if share > FORM_SHARE_LIMIT:
                warnings.append(_err("form_share_over_limit",
                                     f"{vol}: form「{form}」占比 {share:.0%} > {FORM_SHARE_LIMIT:.0%}"))
    stats["errors"] = len(errors)
    stats["warnings"] = len(warnings)
    return {"schema": "novel-studio.check/v1", "ok": not errors,
            "errors": errors, "warnings": warnings, "stats": stats}
