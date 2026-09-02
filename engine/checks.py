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

# 引文接地（0 token 机械校验）支持 quote 的分区遍历描述表：(列表取值器, 条目名)
_QUOTE_SLOTS: list[tuple[str, object]] = [
    ("entities", lambda p: p.get("entities") or []),
    ("lines", lambda p: p.get("lines") or []),
    ("ledger.transactions", lambda p: ((p.get("ledger") or {}).get("transactions")) or []),
    ("timeline.events", lambda p: ((p.get("timeline") or {}).get("events")) or []),
    ("timeline.clocks", lambda p: ((p.get("timeline") or {}).get("clocks")) or []),
]


def _iter_quote_items(proposal: dict):
    """产出 (路径名, 条目) ——提案中所有可携带 quote 的条目（synopsis 单列）。"""
    if not isinstance(proposal, dict):
        return
    for name, getter in _QUOTE_SLOTS:
        try:
            items = getter(proposal)
        except Exception:  # noqa: BLE001 —— 结构异常交给 schema 校验报错
            continue
        for i, item in enumerate(items):
            if isinstance(item, dict):
                yield f"{name}[{i}]", item
    syn = proposal.get("synopsis")
    if isinstance(syn, dict):
        yield "synopsis", syn


def validate_quotes(book: Path, ch: str, proposal: dict) -> list[str]:
    """引文机械校验（0 token）：提案条目可选 quote 必须逐字出现在当章 final 中。

    final 缺失 → 返回空（sync 的输入合同另有闸门）；quote 非串/空白/不在 final → 逐条报错，
    编造或改写引文在物理上无法过闸。这是"引文先行"纪律的引擎侧牙齿。
    """
    finals = common.find_chapter_files(book, "final", ch)
    if not finals:
        return []
    text = finals[-1].read_text(encoding="utf-8", errors="replace")
    errors: list[str] = []
    for where, item in _iter_quote_items(proposal):
        q = item.get("quote")
        if q is None:
            continue
        if not isinstance(q, str) or not q.strip():
            errors.append(f"{where}.quote 必须为非空字符串（逐字摘自 final 的支撑句）")
            continue
        if q not in text:
            frag = q if len(q) <= 32 else q[:32] + "…"
            errors.append(f"{where}.quote 未逐字见于当章 final（引文必须原样摘录，含标点）: 「{frag}」")
    return errors


def _char_shingles(text: str, n: int) -> set[str]:
    z = re.sub(r"[\s，。！？、；：「」『』“”‘’\"'（）()《》〈〉—…·\-~,.;:?!\n]", "", text or "")
    return {z[i:i + n] for i in range(0, max(0, len(z) - n + 1))}


_CAND_STOP = set("他们的自己一个没有什么这个那个已经现在时候知道看着起来出来东西地方一声到底怎么这样那样不是之后就是不过还是这个那般一般".split()) | {
    "他们", "自己", "一个", "没有", "什么", "这个", "那个", "已经", "现在", "时候", "知道",
    "看着", "起来", "出来", "东西", "地方", "一声", "怎么", "这样", "那样", "不是", "之后",
    "就是", "不过", "还是", "一般", "那些", "有些", "一声", "顿时", "随即", "然后", "所以",
    "但是", "如果", "因为", "可是", "心中", "目光", "声音", "身体", "脸上", "手中", "顿时"}


def verify_candidates(book: Path, ch: str, proposal: dict) -> dict:
    """算法版 Stage 4.5（0 token）：提案 × final × 状态 的全机械对照电池。

    只数差异、只出候选清单（sev=warn/info），零裁决——判断归主控。任何一项都不阻断 sync。
    覆盖 8 项：引文覆盖、章题对照、beats 重叠（源纯度）、金额对照（双向）、在场差异、
    state_watch 关键词守望、候选新实体（实验性）、到期线覆盖。
    """
    n = common.chapter_token_to_num(ch)
    out: dict = {"kind": "verify", "chapter": ch, "items": []}
    if not n:
        out["error"] = f"非法章号: {ch!r}"
        return out
    finals = common.find_chapter_files(book, "final", n)
    if not finals:
        out["error"] = f"无 {ch} 的 final（verify 以定稿为源）"
        return out
    text = finals[-1].read_text(encoding="utf-8", errors="replace")
    items = out["items"]

    def add(sev: str, code: str, msg: str) -> None:
        items.append({"sev": sev, "code": code, "msg": msg})

    # 1. 引文覆盖
    total = missing = 0
    for where, item in _iter_quote_items(proposal):
        if not isinstance(item, dict):
            continue
        total += 1
        if not item.get("quote"):
            missing += 1
            if missing <= 8:
                add("warn", "quote_missing", f"{where} 未携带引文（引文先行：每条变更附 final 原句）")
    if missing > 8:
        add("warn", "quote_missing", f"…另有 {missing - 8} 条未携带引文")
    if total == 0:
        add("warn", "quote_none", "提案未携带任何引文——整套引文接地机制未启用")
    out["stats"] = {"quote_slots": total, "quote_missing": missing}

    # 2. 章题对照（final 首行标题行 vs 本次提交/已登记标题）
    m = re.search(r"^#\s*(.+?)\s*$", text, re.M)
    if not m:
        add("info", "title_absent", "final 无章题标题行，章题机械对照跳过（Editor 契约要求首行章题）")
    else:
        raw = m.group(1)
        final_title = re.sub(r"^(?:第\s*[0-9零一二三四五六七八九十百千]+\s*章|ch[_-]?\d+)\s*", "", raw).strip()
        submitted = (proposal.get("synopsis") or {}).get("title") if isinstance(proposal.get("synopsis"), dict) else None
        if not submitted:
            try:
                submitted = state.load_state(book, "synopsis").get("chapters", {}).get(ch, {}).get("title", "")
            except (ValueError, FileNotFoundError):
                submitted = ""
        if submitted and submitted != final_title:
            add("warn", "title_mismatch", f"章题与 final 不一致: 提交「{submitted}」≠ final「{final_title}」（契约：逐字拷贝）")

    # 3. beats 重叠（源纯度：事实性文字须来自 final，不得照抄任务书）
    beats_files = common.find_chapter_files(book, "beats", n)
    if beats_files:
        beats_sh = _char_shingles(beats_files[-1].read_text(encoding="utf-8", errors="replace"), 8)
        free_fields = []
        syn = proposal.get("synopsis") if isinstance(proposal.get("synopsis"), dict) else {}
        if syn.get("text"):
            free_fields.append(("synopsis.text", syn["text"]))
        if syn.get("title"):
            free_fields.append(("synopsis.title", syn["title"]))
        tl = proposal.get("timeline") if isinstance(proposal.get("timeline"), dict) else {}
        for i, ev in enumerate(tl.get("events") or []):
            if isinstance(ev, dict):
                free_fields.append((f"timeline.events[{i}].event", ev.get("event", "")))
                if ev.get("replace"):
                    free_fields.append((f"timeline.events[{i}].replace", ev["replace"]))
        for i, g in enumerate(proposal.get("lines") or []):
            if isinstance(g, dict):
                for f in ("name", "plan", "content", "truth"):
                    if g.get(f):
                        free_fields.append((f"lines[{i}].{f}", str(g[f])))
        for where, val in free_fields:
            shared = _char_shingles(val, 8) & beats_sh
            if len(shared) >= 2:
                ex = sorted(shared)[0]
                add("warn", "beats_overlap",
                    f"{where} 与任务书 beats 存在 {len(shared)} 处 8 字连续重叠（如「{ex}」）——"
                    "疑似照抄任务书，事实性文字须逐字以 final 为源")

    # 4. 金额对照（双向：正文金额候选 vs 本章流水；引文可豁免口径差）
    try:
        led = state.load_state(book, "ledger")
    except (ValueError, FileNotFoundError) as exc:
        add("warn", "ledger_unreadable", f"ledger 不可读，金额对照跳过: {exc}")
        led = {}
    amounts = evidence._amount_scan(text, led.get("pools"))
    cand_vals = {v for a in amounts for v in a.get("values", [])}
    txs = [t for t in (led.get("transactions") or []) if t.get("chapter") == ch]
    new_txs = [t for t in ((proposal.get("ledger") or {}).get("transactions") or [])
               if isinstance(t, dict) and (t.get("chapter") or ch) == ch]
    tx_vals = {int(t.get("delta", 0)) for t in txs + new_txs if isinstance(t.get("delta"), int)}
    for a in amounts:
        miss = [v for v in a["values"] if v not in tx_vals]
        if miss:
            add("warn", "amount_unmatched",
                f"正文金额候选 {a['samples']}（值 {miss}）未对应本章任何流水——确认是修辞还是漏账")
    for i, t in enumerate(new_txs):
        if isinstance(t.get("delta"), int) and t["delta"] not in cand_vals:
            q = t.get("quote")
            if q:
                add("info", "amount_by_quote",
                    f"ledger.transactions[{i}] 金额 {t['delta']} 未被机械扫描命中，但已附引文佐证（口径差属预期）")
            else:
                add("warn", "amount_unsupported",
                    f"ledger.transactions[{i}] 金额 {t['delta']} 既无正文金额候选、也无引文——补 quote 或核对数值")
    out["stats"]["amount_candidates"] = len(cand_vals)

    # 5. 在场差异（提及计数 vs 声明名单，双向）
    try:
        lookup = evidence.entity_lookup(book)
    except (ValueError, FileNotFoundError) as exc:
        add("warn", "entities_unreadable", f"实体表不可读，在场对照跳过: {exc}")
        lookup = {}
    # 预同步对照口径：提案本次正在注册的实体并入检索表，避免"新实体在场"误报
    for e in (proposal.get("entities") or []):
        if isinstance(e, dict) and e.get("action", "upsert") != "retire" and str(e.get("name", "")).strip():
            name = str(e["name"])
            if name not in lookup:
                lookup[name] = [name] + [str(a) for a in (e.get("aliases") or []) if a]
    per = {name: sum(evidence.count_aliases(text, aliases).values()) for name, aliases in lookup.items()}
    cur_prop = (proposal.get("current") or {}).get("present_characters") if isinstance(proposal.get("current"), dict) else None
    if cur_prop is None:
        try:
            cur_prop = state.load_state(book, "current").get("present_characters", [])
        except (ValueError, FileNotFoundError):
            cur_prop = []
    if not cur_prop:
        add("info", "present_undeclared", "present_characters 未声明（空数组按未提供处理）")
    else:
        for name in cur_prop:
            if per.get(str(name), 0) == 0:
                add("warn", "present_unmentioned", f"在场声明「{name}」在本章 final 零提及——核对是否章末真在场")
        for name, c in sorted(per.items(), key=lambda x: -x[1]):
            if c >= 2 and name not in cur_prop:
                add("warn", "mention_not_present", f"「{name}」本章提及 {c} 次但未列入在场名单（漏报或早退，归主控判）")
                break

    # 6. state_watch 关键词守望（书级配置 project.json.state_watch: {current字段: [词表]}）
    proj = common.load_json(book / "project.json", default={}) or {}
    try:
        cur_state = state.load_state(book, "current")
    except (ValueError, FileNotFoundError):
        cur_state = {}
    for field, terms in (proj.get("state_watch") or {}).items():
        if not isinstance(terms, list):
            continue
        for term in terms:
            if isinstance(term, str) and term in text and term not in str(cur_state.get(field, "")):
                add("warn", "state_watch_hit",
                    f"正文出现「{term}」但 current.{field} 未提及——疑似状态刷新遗漏（修辞/闪回情形忽略）")

    # 7. 候选新实体（实验性：正文高频 2~4 字串，非注册、非停用词）
    known = [str(x).lower() for names in lookup.values() for x in names]
    segs = [s for s in re.split(r"[^\u4e00-\u9fff]+", text) if len(s) >= 2]
    grams: dict[str, int] = {}
    for seg in segs:
        for L in (2, 3, 4):
            for i in range(len(seg) - L + 1):
                g = seg[i:i + L]
                grams[g] = grams.get(g, 0) + 1
    cands = []
    for g, c in grams.items():
        if c < 3 or g in _CAND_STOP or any(s in g for s in _CAND_STOP):
            continue
        if any((g in k) or (k in g and len(k) >= 2) for k in known):
            continue
        cands.append((g, c))
    cands = [(g, c) for g, c in cands if not any(g != g2 and g in g2 and c2 >= c for g2, c2 in cands)]
    for g, c in sorted(cands, key=lambda x: -x[1])[:12]:
        add("info", "candidate_new_entity", f"「{g}」出现 {c} 次且未注册——若是新实体请补 entities upsert（实验性候选，误报勿理）")

    # 8. 到期线覆盖（final 触及但提案未操作）
    try:
        lines = state.load_state(book, "lines")
        ops_ids = {str(g.get("id")) for g in (proposal.get("lines") or [])
                   if isinstance(g, dict) and g.get("id") and g.get("action", "plant") != "plant"}
        reg_terms = [a for names in lookup.values() for a in names]
        resolved = {"foreshadow": "Resolved", "misunderstanding": "Resolved", "knowledge": "Revealed"}
        for kind, arr in (("foreshadow", "foreshadows"), ("misunderstanding", "misunderstandings"),
                          ("knowledge", "knowledge")):
            for g in lines.get(arr, []):
                if g.get("status") == resolved[kind] or g.get("id") in ops_ids:
                    continue
                t = g.get("target_ch")
                if isinstance(t, int) and t <= n:
                    terms = evidence._line_terms_for(g, kind, reg_terms)
                    if any(term in text for term in terms):
                        add("warn", "due_line_unhandled",
                            f"{g['id']}（target ch_{t:03d}）正文有触及、提案未操作——确认本章是否该还线")
        
        # 9. 伏笔配额检查（提案新增 plant 时检测是否超限）
        proj = common.load_json(book / "project.json", default={}) or {}
        lcap = proj.get("lines_cap") or {}
        act_cap = lcap.get("active_foreshadows", 8)
        long_cap = lcap.get("longline_foreshadows", 5)
        open_act = [g for g in lines.get("foreshadows", []) if g.get("status") != "Resolved" and isinstance(g.get("target_ch"), int)]
        open_long = [g for g in lines.get("foreshadows", []) if g.get("status") != "Resolved" and g.get("target_ch") == "longline"]
        for g in (proposal.get("lines") or []):
            if isinstance(g, dict) and g.get("kind") == "foreshadow" and g.get("action", "plant") == "plant":
                tgt = g.get("target_ch")
                if tgt == "longline" and len(open_long) >= long_cap:
                    add("warn", "line_quota_exceeded",
                        f"全书长线已达上限（{len(open_long)}/{long_cap}），提案再次 plant 长线《{g.get('name','')}》——建议先回收或精简旧线")
                elif tgt != "longline" and len(open_act) >= act_cap:
                    add("warn", "line_quota_exceeded",
                        f"卷内活动伏笔池已满（{len(open_act)}/{act_cap}），提案再次 plant 活动线《{g.get('name','')}》——建议在后续章节优先回收旧线")

        # 10. 高危状态变更检测（生命阵亡/严重伤残/境界异动/退役）
        for ent in (proposal.get("entities") or []):
            if not isinstance(ent, dict): continue
            ename = ent.get("name", "未命名实体")
            if ent.get("life_status") == "deceased":
                add("warn", "critical_mutation", f"🚨【高危状态变更】实体「{ename}」生命状态变更为【战死/离世 (deceased)】，请重点核实正文确凿事实！")
            if ent.get("action") == "retire" or ent.get("status") == "retired":
                add("warn", "critical_mutation", f"🚨【高危状态变更】实体「{ename}」被标记为退役 (retired)，请核实！")

        cur_p = proposal.get("current") or {}
        if isinstance(cur_p, dict):
            inj = str(cur_p.get("injury", ""))
            for kw in ("断臂", "残疾", "瘫痪", "丹田被废", "经脉尽断", "濒死", "重伤垂死"):
                if kw in inj:
                    add("warn", "critical_mutation", f"🚨【高危状态变更】主角伤势出现严重伤残描述「{inj}」，请核实是否为正文真实设定！")
                    break
            if cur_p.get("power_level"):
                add("info", "power_level_shift", f"⭐【境界变动】主角境界更新为「{cur_p['power_level']}」")
    except (ValueError, FileNotFoundError) as exc:
        add("warn", "lines_unreadable", f"lines 不可读，线对照跳过: {exc}")
    return out


def _err(code: str, msg: str) -> dict:
    return {"code": code, "msg": msg}


_BEATS_FM_KEYS = {"chapter", "vol", "form", "pov", "words", "style_notes", "form_reason",
                  "guard_extra", "editor_extra", "tension_curve"}

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
    """校对注记体检（可选机制，软提示）：注记存在时检查「验收」节是否逐条答完 beats「验收」。

    只数行与符号；结果由调用方决定呈现方式——sync 流程将其作为 ℹ️ 提示打印，
    不影响退出码、不阻断封存（见 cli.cmd_sync）。注记不存在 = 机制未启用，
    返回创建提醒（同样不构成错误）。
    """
    beats = [f for f in common.find_chapter_files(book, "beats")
             if common.chapter_number_from_name(f.name) == common.chapter_token_to_num(ch)]
    k = 0
    if beats:
        # 取版本号最大者（[-1]），与 review_skeleton/proposal auto/pack 同口径（P2-6）
        acc = common.md_section(beats[-1].read_text(encoding="utf-8", errors="replace"), r"^##\s*(?:.*验收|.*契约)")
        k = max(_numbered_items(acc), default=0)
    rev = book / "log" / "review" / f"{ch}.md"
    if not rev.is_file():
        extra = f"；beats「验收」共 {k} 条" if k else ""
        return [f"校对注记 {ch}.md 不存在（可选机制未启用，不阻断 sync；"
                f"如需验收留痕可运行 studio review new {ch} --write{extra}）"]
    rtext = rev.read_text(encoding="utf-8", errors="replace")
    issues: list[str] = []
    if not re.search(r"^##\s*(?:.*验收|.*契约)", rtext, re.M):
        issues.append("校对注记缺「## 验收」或「## 交付契约」节")
    items = _numbered_items(common.md_section(rtext, r"^##\s*(?:.*验收|.*契约)"))
    missing = [n for n in range(1, k + 1) if n not in items]
    if missing:
        issues.append(f"验收 {missing} 未被校对注记回答（共 {k} 条，须逐条 N. ✓/✗+证据）")
    # 证据判定（Stage 4/5 验收证据规范）：每条结论必须带证据——正文引文，或 evidence 字段名+数值。
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
    """校对注记骨架数据（Stage 5）：验收条目/必须保留自 beats 提取，机器数据逐项预填。
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
        try:
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
        except (ValueError, FileNotFoundError) as exc:
            facts["error"] = f"状态不可读，三方对照降级: {exc}"  # P2-1：损坏降级为字段，不裸崩
    try:
        lines = state.load_state(book, "lines")
    except (ValueError, FileNotFoundError) as exc:
        facts.setdefault("error", f"lines 不可读: {exc}")
        lines = {}
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
        start = 1 if vol == "vol_01" else min(nums)
        missing = sorted(set(range(start, max(nums) + 1)) - set(nums))
        if missing:
            errors.append(_err("final_gap_chapters",
                               f"{vol} final 章号断档: {missing}（第 {start} 与 {max(nums)} 章之间无定稿）"))
    stats["final_chapters"] = len(per_ch)

    # ---- 占位符：槽位未实例化禁止入流水线 ----
    slot_hits = []
    for md in sorted(book.rglob("*.md")):
        try:
            if SLOT_RE.search(md.read_text(encoding="utf-8", errors="ignore")):
                slot_hits.append(md.relative_to(book).as_posix())
        except OSError:
            continue
    for rel in slot_hits:
        errors.append(_err("unfilled_slot", f"{rel} 存在未填充槽位 {{{{slot:...}}}}（Stage 0 未完成）"))

    # ---- 稿件禁工程痕迹（candidate_* 泄漏进 manuscript）----
    ms = book / "manuscript"
    if ms.is_dir():
        for md in sorted(ms.rglob("*.md")):
            try:
                if CANDIDATE_RE.search(md.read_text(encoding="utf-8", errors="ignore")):
                    errors.append(_err("candidate_leak",
                        f"{md.relative_to(book).as_posix()} 含 candidate_* 工程痕迹（AGENTS 防污染原则：稿件严禁工程标记）"))
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
                               f"（合法键 {sorted(_BEATS_FM_KEYS)}；AGENTS 防污染原则：工程痕迹禁入稿）"))
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
                                     f"{f.name}: style_notes 旋钮与上一章全同「{fm.get('style_notes','')}」"
                                     "（建议根据当章冲突焦点与情境动态配置 style_notes）"))
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
                                 "（判据建议使用具体可验证的动词与实体名词）"))
        action_sec = "\n".join(common.md_section(text, r"^##\s*.*线(索)?动作"))
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

    # ---- 编码卫生（P3-4）：正文出现替换符 \ufffd = 疑似非 UTF-8 保存，字数统计已失真 ----
    for f in common.find_chapter_files(book, "final"):
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n_bad = t.count("\ufffd")
        if n_bad:
            warnings.append(_err("encoding_replacement_chars",
                                 f"{f.name}: 含 {n_bad} 个替换符（疑似非 UTF-8 编码保存，字数/统计口径已失真）"))


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

    # ---- 伏笔配额体检（双轨配额制，只报数/超限警告） ----
    try:
        lines_st = state.load_state(book, "lines")
        lcap = proj.get("lines_cap") or {}
        act_cap = lcap.get("active_foreshadows", 8)
        long_cap = lcap.get("longline_foreshadows", 5)
        open_act = [g for g in lines_st.get("foreshadows", []) if g.get("status") != "Resolved" and isinstance(g.get("target_ch"), int)]
        open_long = [g for g in lines_st.get("foreshadows", []) if g.get("status") != "Resolved" and g.get("target_ch") == "longline"]
        if len(open_act) > act_cap:
            warnings.append(_err("line_quota_exceeded",
                                 f"未结活动伏笔 {len(open_act)} 条 > 上限 {act_cap} 条（建议在后续章节优先回收 resolve，防僵尸伏笔堆积）"))
        if len(open_long) > long_cap:
            warnings.append(_err("longline_quota_exceeded",
                                 f"未结全书长线 {len(open_long)} 条 > 上限 {long_cap} 条（长线过多分散主线焦点）"))
    except (ValueError, FileNotFoundError):
        pass

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

    # ---- 叙事节奏体检（连续高压疲劳检测） ----
    high_tension_forms = {"生死博弈", "高潮突破", "极限博弈", "高潮决战", "决战爆发", "危机激化"}
    for vol_dir in sorted((book / "outlines").glob("vol_*")):
        beats_files = sorted(vol_dir.glob("beats/ch_*.md"))
        consecutive_high = []
        for bf in beats_files:
            try:
                fm = common.parse_front_matter(bf.read_text(encoding="utf-8", errors="replace"))
                form_val = str(fm.get("form", "")).strip()
                ch_tok = bf.stem
                is_high = form_val in high_tension_forms or any(k in form_val for k in ("博弈", "高潮", "决战", "生死"))
                if is_high:
                    consecutive_high.append((ch_tok, form_val))
                    if len(consecutive_high) >= 3:
                        chs = f"{consecutive_high[0][0]}—{consecutive_high[-1][0]}"
                        warnings.append(_err("high_tension_fatigue",
                                             f"{vol_dir.name}: {chs} 连续 {len(consecutive_high)} 章为高压战斗/决战（form={form_val}），建议在下一章切换为「战后清点/爽感兑现」章型，消化战利品与人情互动，防读者情绪疲劳！"))
                else:
                    consecutive_high = []
            except OSError:
                continue

    # ---- 细纲场景具象度体检（防假大空口水章） ----
    abstract_phrases = ["巧妙化解", "发生冲突", "展现谋略", "机智应对", "某些麻烦", "发生争执", "不长眼"]
    for vol_dir in sorted((book / "outlines").glob("vol_*")):
        for bf in sorted(vol_dir.glob("beats/ch_*.md")):
            try:
                btext = bf.read_text(encoding="utf-8", errors="replace")
                for phr in abstract_phrases:
                    if phr in btext:
                        warnings.append(_err("beats_scene_abstract",
                                             f"{vol_dir.name}/{bf.name}: 细纲中出现假大空抽象词「{phr}」——建议细化为具体的物理标的、利益死结或破局动作！"))
                        break
            except OSError:
                continue

    stats["errors"] = len(errors)
    stats["warnings"] = len(warnings)
    return {"schema": "novel-studio.check/v1", "ok": not errors,
            "errors": errors, "warnings": warnings, "stats": stats}
