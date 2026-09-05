"""check：结构 + schema + 算术体检（吸收旧 doctor/verify/audit；errors 只允许事实级）。

语义红线 ：
- errors：可机械判定必须修复的事实——schema 违规、引用未登记实体、章号断档、占位符未填、
  同 form 无理由、账本重算不符（state.verify_state）。
- warnings：算术数出来的偏离事实（字数出带、线逾期、tics 命中、form 占比超 40%）——只报数，
  是否修、怎么修由主控决定。
- 两个桶里都不许出现「建议/疑似/不宜」等判断词；本模块零写入。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import common, errcodes, evidence, state

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False

SLOT_RE = re.compile(r"\{\{\s*slot:")
CANDIDATE_RE = re.compile(r"candidate_[0-9A-Za-z_*]")
FORM_SHARE_LIMIT = 0.40
QUOTE_PASS_RATIO = 85.0   # 模糊相似度 ≥85 视为命中（静默通过）
QUOTE_NEAR_RATIO = 60.0   # [60, 85) 提示「近似命中」；< 60 提示「存疑」；全程不阻断

_QUOTE_SLOTS: list[tuple[str, object]] = [
    ("entities", lambda p: p.get("entities") or []),
    ("lines", lambda p: p.get("lines") or []),
    ("ledger.transactions", lambda p: ((p.get("ledger") or {}).get("transactions")) or []),
    ("timeline.events", lambda p: ((p.get("timeline") or {}).get("events")) or []),
    ("timeline.clocks", lambda p: ((p.get("timeline") or {}).get("clocks")) or []),
]


def _iter_quote_items(proposal: dict):
    if not isinstance(proposal, dict):
        return
    for name, getter in _QUOTE_SLOTS:
        try:
            items = getter(proposal)
        except (AttributeError, KeyError, TypeError):
            continue
        for i, item in enumerate(items):
            if isinstance(item, dict):
                yield f"{name}[{i}]", item
    syn = proposal.get("synopsis")
    if isinstance(syn, dict):
        yield "synopsis", syn


def _norm_quote_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _norm_quote_punct(s: str) -> str:
    if not s:
        return ""
    t = re.sub(r"\s+", "", s)
    t = re.sub(r"[「」『』“”‘’\"']", "\"", t)
    t = re.sub(r"[—–―─\-]{2,}", "——", t)
    t = re.sub(r"[…]{1,}|\.{3,}|。{3,}", "……", t)
    return t.strip("，。！？；：、,.;:!?\"")


def validate_quotes(book: Path, ch: str, proposal: dict) -> list[str]:
    """引文柔性接地（advisory · 永不阻断）。

    分级语义（2026-09 引文柔性化：摘录凭印象即可，严禁 LLM 逐字抠字眼浪费算力）：
    - 逐字 / 空白归一 / 标点归一 / 模糊 ≥ QUOTE_PASS_RATIO → 命中，静默通过；
    - 模糊 [QUOTE_NEAR_RATIO, PASS) → 「近似命中」提示（凭印象摘录的预期偏差，供主控参考）；
    - 其余（含短引文无法可靠模糊判定）→ 「存疑」提示（可能编造或版本漂移，主控复核）；
    - 战死/退役等高危变更未携带引文 → 醒目提示（建议附原句，便于日后回溯）。
    返回值为提示清单，调用方一律不得据此阻断 sync。
    """
    finals = common.find_chapter_files(book, "final", ch)
    if not finals:
        return []
    text = finals[-1].read_text(encoding="utf-8", errors="replace")
    norm_text = _norm_quote_ws(text)
    norm_punct_text = _norm_quote_punct(text)
    notes: list[str] = []
    for where, item in _iter_quote_items(proposal):
        if not isinstance(item, dict):
            continue
        q = item.get("quote")
        if q is None:
            continue
        if not isinstance(q, str) or not q.strip():
            notes.append(f"🟡 {where}.quote 非空字符串（请填正文原句或删除该字段）: {q!r}")
            continue
        if q in text:
            common.debug(f"quote {where}: exact hit")
            continue
        norm_q = _norm_quote_ws(q)
        if norm_q and norm_q in norm_text:
            common.debug(f"quote {where}: whitespace-normalized hit")
            continue
        norm_p_q = _norm_quote_punct(q)
        if norm_p_q and len(norm_p_q) >= 4 and norm_p_q in norm_punct_text:
            common.debug(f"quote {where}: punct-normalized hit")
            continue
        score = -1.0
        if _HAS_RAPIDFUZZ and norm_p_q and len(norm_p_q) >= 8:
            score = fuzz.partial_ratio(norm_p_q, norm_punct_text)
        if score >= QUOTE_PASS_RATIO:
            common.debug(f"quote {where}: fuzzy hit (score={score:.1f} ≥ {QUOTE_PASS_RATIO})")
            continue
        frag = q if len(q) <= 32 else q[:32] + "…"
        if score >= QUOTE_NEAR_RATIO:
            common.debug(f"quote {where}: near miss (score={score:.1f}, [{QUOTE_NEAR_RATIO}, {QUOTE_PASS_RATIO}))")
            notes.append(f"🟡 {where}.quote 近似命中（相似度 {score:.0f}%，与原文存在字词偏差）"
                         f"——凭印象摘录的预期现象，仅供主控参考: 「{frag}」")
        else:
            common.debug(f"quote {where}: MISS (score={score:.1f} < {QUOTE_NEAR_RATIO})")
            notes.append(f"🟡 {where}.quote 未命中当章 final（存疑引文，不阻断）"
                         f"——主控复核是否编造或版本漂移: 「{frag}」")
    for e in (proposal.get("entities") or []):
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "")).strip() or "未命名实体"
        has_quote = bool(str(e.get("quote") or "").strip())
        if not has_quote and e.get("life_status") == "deceased":
            notes.append(f"🚨 实体「{name}」被登记为【战死/离世】但未携带引文"
                         "——强烈建议凭印象附正文原句，便于日后回溯审计")
        if not has_quote and e.get("status") == "retired":
            notes.append(f"🚨 实体「{name}」被标记为【退役/退场】但未携带引文"
                         "——强烈建议凭印象附正文原句")
    return notes


class _FoundCycle(Exception):
    """迭代式 DFS 检出循环依赖时抛出（携带成环节点 ID）。"""

    def __init__(self, node: str):
        super().__init__(node)
        self.node = node


def _char_shingles(text: str, n: int) -> set[str]:
    # 注意：字符类不含字母 n（旧写法 \\n 在 raw string 中是「反斜杠+字母n」两个成员，
    # 会把西文单词里的 n 当标点剔除，QA P3-19）；换行已由 \s 覆盖。
    z = re.sub(r"[\s，。！？、；：「」『』“”‘’\"'（）()《》〈〉—…·\-~,.;:?!]", "", text or "")
    return {z[i:i + n] for i in range(0, max(0, len(z) - n + 1))}


_CAND_STOP = set("他们的自己一个没有什么这个那个已经现在时候知道看着起来出来东西地方一声到底怎么这样那样不是之后就是不过还是这个那般一般".split()) | {
    "他们", "自己", "一个", "没有", "什么", "这个", "那个", "已经", "现在", "时候", "知道",
    "看着", "起来", "出来", "东西", "地方", "一声", "怎么", "这样", "那样", "不是", "之后",
    "就是", "不过", "还是", "一般", "那些", "有些", "一声", "顿时", "随即", "然后", "所以",
    "但是", "如果", "因为", "可是", "心中", "目光", "声音", "身体", "脸上", "手中", "顿时"}


def verify_candidates(book: Path, ch: str, proposal: dict) -> dict:
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
            # 双侧同规则归一化（QA P2-4）：此前只剥 final 侧的「第N章」前缀，
            # 提案侧逐字拷贝的章题反而每次触发假阳性告警
            sub_norm = re.sub(r"^(?:第\s*[0-9零一二三四五六七八九十百千]+\s*章|ch[_-]?\d+)\s*",
                              "", str(submitted)).strip()
            if sub_norm != final_title:
                add("warn", "title_mismatch",
                    f"章题与 final 不一致: 提交「{submitted}」≠ final「{final_title}」（契约：逐字拷贝）")

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
    tx_vals = {abs(int(t.get("delta", 0))) for t in txs + new_txs if isinstance(t.get("delta"), int)}
    for a in amounts:
        miss = [v for v in a["values"] if abs(v) not in tx_vals]
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

    try:
        lookup = evidence.entity_lookup(book)
    except (ValueError, FileNotFoundError) as exc:
        add("warn", "entities_unreadable", f"实体表不可读，在场对照跳过: {exc}")
        lookup = {}
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
        try:
            _persons = {e.get("name") for e in state.load_state(book, "entities").get("entries", [])
                        if e.get("type", "person") == "person"}
        except (ValueError, FileNotFoundError):
            _persons = set()
        for name, c in sorted(per.items(), key=lambda x: -x[1]):
            if c >= 2 and name not in cur_prop and (not _persons or name in _persons):
                # QA P10：提及 2~3 次多为「中段退场」场景常态 → info；≥4 次才大概率真在场 → warn
                add("info" if c < 4 else "warn", "mention_not_present",
                    f"「{name}」本章提及 {c} 次但未列入在场名单（漏报或早退，归主控判）")
                break

    proj = common.load_json(book / "project.json", default={}) or {}
    try:
        cur_state = state.load_state(book, "current")
    except (ValueError, FileNotFoundError):
        cur_state = {}
    prop_cur = (proposal.get("current") or {}) if isinstance(proposal.get("current"), dict) else {}
    for field, terms in (proj.get("state_watch") or {}).items():
        if not isinstance(terms, list):
            continue
        active_val = str(prop_cur[field]) if field in prop_cur else str(cur_state.get(field, ""))
        for term in terms:
            if isinstance(term, str) and term in text and term not in active_val:
                add("warn", "state_watch_hit",
                    f"正文出现「{term}」但提案/现场 current.{field} 未提及——疑似状态刷新遗漏（修辞/闪回情形忽略）")

    # 开篇咬合检查（advisory）：final 首部应承接上章余震（pack「首段必咬住」硬提醒的机械复核）；
    # sync 在合并前调用本电池，此刻 current.aftershock 恰为上一章封存的余震，时序正确。
    if n > 1 and str(cur_state.get("aftershock") or "").strip():
        prev_after = str(cur_state["aftershock"]).strip()
        head = text[:600]
        windows = [prev_after[i:i + 4] for i in range(0, max(1, len(prev_after) - 3))
                   if len(prev_after[i:i + 4].strip()) == 4]
        if windows and not any(w in head for w in windows):
            add("info", "aftermath_opening_miss",
                f"final 开篇未触及上章余震「{prev_after[:40]}」的任何 4 字片段——"
                "核对首段是否需要咬住余波（氛围型余震或有意转场可忽略）")

    known = [str(x).lower() for names in lookup.values() for x in names]
    cand_stop = _CAND_STOP | {str(w).strip() for w in (proj.get("candidate_stopwords") or [])
                              if isinstance(w, str) and w.strip()}
    segs = [s for s in re.split(r"[^\u4e00-\u9fff]+", text) if len(s) >= 2]
    grams: dict[str, int] = {}
    # QA P3：候选最小长度 3（2 字碎片「了半/樵把/的声」纯语法噪声，不再上报）
    for seg in segs:
        for L in (3, 4):
            for i in range(len(seg) - L + 1):
                g = seg[i:i + L]
                grams[g] = grams.get(g, 0) + 1
    cands = []
    try:
        _pools = state.load_state(book, "ledger").get("pools", {})
    except (ValueError, FileNotFoundError):
        _pools = {}
    # QA P3：账本池名/单位并入已知词——「灵通」类池名片段不再当候选（如 灵通石→灵通）
    for p in _pools.values():
        for t in (p.get("name"), p.get("unit")):
            if t:
                known.append(str(t).lower())
    for g, c in grams.items():
        if c < 3 or g in cand_stop or any(s in g for s in cand_stop):
            continue
        if evidence.is_candidate_noise(g, _pools):
            continue
        if any((g in k) or (k in g and len(k) >= 2) for k in known):
            continue
        cands.append((g, c))
    cands = [(g, c) for g, c in cands if not any(g != g2 and g in g2 and c2 >= c for g2, c2 in cands)]
    for g, c in sorted(cands, key=lambda x: -x[1])[:12]:
        add("info", "candidate_new_entity", f"「{g}」出现 {c} 次且未注册——若是新实体请补 entities upsert（实验性候选，误报勿理）")

    try:
        lines = state.load_state(book, "lines")
        ops_ids = {str(g.get("id")) for g in (proposal.get("lines") or [])
                   if isinstance(g, dict) and g.get("id") and g.get("action", "plant") != "plant"}
        reg_terms = [a for names in lookup.values() for a in names]
        resolved = {"foreshadow": "Resolved", "misunderstanding": "Resolved", "knowledge": "Revealed"}
        for kind, arr in (("foreshadow", "foreshadows"), ("misunderstanding", "misunderstandings"),
                          ("knowledge", "knowledge")):
            for g in lines.get(arr, []):
                if str(g.get("status", "")).strip().lower() == resolved[kind].lower() or g.get("id") in ops_ids:
                    continue
                t = g.get("target_ch")
                if isinstance(t, int) and t <= n:
                    terms = evidence._line_terms_for(g, kind, reg_terms)
                    if any(term in text for term in terms):
                        add("warn", "due_line_unhandled",
                            f"{g['id']}（target ch_{t:03d}）正文有触及、提案未操作——确认本章是否该还线")

        proj = common.load_json(book / "project.json", default={}) or {}
        lcap = proj.get("lines_cap") or {}
        act_cap = lcap.get("active_foreshadows", 8)
        long_cap = lcap.get("longline_foreshadows", 5)
        open_act = [g for g in lines.get("foreshadows", []) if str(g.get("status", "")).strip().lower() != "resolved" and isinstance(g.get("target_ch"), int)]
        open_long = [g for g in lines.get("foreshadows", []) if str(g.get("status", "")).strip().lower() != "resolved" and g.get("target_ch") == "longline"]
        for g in (proposal.get("lines") or []):
            if isinstance(g, dict) and g.get("kind") == "foreshadow" and g.get("action", "plant") == "plant":
                tgt = g.get("target_ch")
                if tgt == "longline" and len(open_long) >= long_cap:
                    add("warn", "line_quota_exceeded",
                        f"全书长线已达上限（{len(open_long)}/{long_cap}），提案再次 plant 长线《{g.get('name','')}》——建议先回收或精简旧线")
                elif tgt != "longline" and len(open_act) >= act_cap:
                    add("warn", "line_quota_exceeded",
                        f"卷内活动伏笔池已满（{len(open_act)}/{act_cap}），提案再次 plant 活动线《{g.get('name','')}》——建议在后续章节优先回收旧线")

        for ent in (proposal.get("entities") or []):
            if not isinstance(ent, dict):
                continue
            ename = ent.get("name", "未命名实体")
            if ent.get("life_status") == "deceased":
                add("warn", "critical_mutation", f"🚨【高危状态变更】实体「{ename}」生命状态变更为【战死/离世 (deceased)】，请重点核实正文确凿事实！")
            if ent.get("action") == "retire" or ent.get("status") == "retired":
                add("warn", "critical_mutation", f"🚨【高危状态变更】实体「{ename}」被标记为退役 (retired)，请核实！")

        cur_p = proposal.get("current") or {}
        if isinstance(cur_p, dict):
            inj = str(cur_p.get("injury", ""))
            crit_words = proj.get("critical_injury_words")
            if crit_words is None:
                add("info", "wordlist_unconfigured",
                    "critical_injury_words 未配置：伤势高危警示档已跳过——"
                    "请主控在 project.json 按本书题材供参（如 [\"重伤\",\"濒死\",...]）后生效（空表 = 明确关闭）")
            elif inj:
                for kw in [w for w in crit_words if isinstance(w, str) and w]:
                    if kw in inj:
                        add("warn", "critical_mutation", f"🚨【高危状态变更】主角伤势出现严重伤残描述「{inj}」，请核实是否为正文真实设定！")
                        break
            if cur_p.get("power_level"):
                add("info", "power_level_shift", f"⭐【境界变动】主角境界更新为「{cur_p['power_level']}」")
    except (ValueError, FileNotFoundError) as exc:
        add("warn", "lines_unreadable", f"lines 不可读，线对照跳过: {exc}")
    return out


# 错误码与修复文案的唯一真源在 errcodes.REGISTRY（含 severity 与人话解释，供 Agent 消费）；
# 此处仅派生兜底 remedy 字典，禁止在本文件再手写新条目（守卫测试 test_errcodes 拦截漂移）。
DEFAULT_REMEDIES: dict[str, str] = {c.code: c.remedy for c in errcodes.REGISTRY.values()
                                    if c.remedy}


def _err(code: str, msg: str, remedy: str = "", can_auto_heal: bool = True) -> dict:
    item = {"code": code, "msg": msg}
    resolved_remedy = remedy or DEFAULT_REMEDIES.get(code, "")
    if resolved_remedy:
        item["remedy"] = resolved_remedy
    item["can_auto_heal"] = can_auto_heal
    return item


_BEATS_FM_KEYS = {"chapter", "vol", "form", "pov", "words", "style_notes", "form_reason",
                  "editor_extra", "tension_curve", "tension_score",
                  "stage_mode", "suppression_factors", "release_trigger"}

PARAM_SPEC: dict[str, dict] = {
    "generic_stopwords": {"shape": "str_list", "gap": True,
        "desc": "通用实体停用词（evidence 别名 P1 触发降噪 / pack）",
        "example": ["掌柜", "警官", "乘务员"]},
    "critical_injury_words": {"shape": "str_list", "gap": True,
        "desc": "伤势高危警示词（verify critical_mutation 档）",
        "example": ["重伤", "濒死", "截瘫"]},
    "abstract_phrases": {"shape": "str_list", "gap": True,
        "desc": "细纲假大空词（check beats_scene_abstract 档）",
        "example": ["巧妙化解", "发生争执"]},
    "high_heat_forms": {"shape": "str_list", "gap": True,
        "desc": "高压章型名清单（check 连续高压疲劳检测，精确匹配 front-matter form 值）",
        "example": ["生死博弈", "高潮突破"]},
    "empty_criteria_words": {"shape": "str_list", "gap": True,
        "desc": "验收条目空判词（check acceptance_empty_criterion 档）",
        "example": ["读者", "沉浸感"]},
    "hook_words": {"shape": "hook_tiers", "gap": True,
        "desc": "章尾钩子分档词表（prev/dashboard；strong/suspense/anticlimax 三键，值各为词表）",
        "example": {"strong": ["案发", "强敌登门"], "suspense": ["尾随", "深夜来电"], "anticlimax": ["虚惊一场"]}},
    "candidate_stopwords": {"shape": "str_list", "gap": False,
        "desc": "候选新实体追加降噪词（verify 候选清单过滤，追加到语言功能词底表；可选增配，不配不提示）",
        "example": ["心头", "眼底"]},
    "state_watch": {"shape": "str_map", "gap": False,
        "desc": "current 字段关键词守望（verify state_watch 档）：{字段: [词表]}。"
                "注意：守望按纯字符串命中、无上下文消歧——同词多义（如境界名与道具名同字）请拆分词表或限定词形，防误报。",
        "example": {"power_level": ["突破", "晋升"]}},
    "words_target": {"shape": "int_pair", "gap": False,
        "desc": "定稿字数目标带 [下限, 上限]（check word_band_deviation / word_band_breach 判定依据）",
        "example": [2000, 3000]},
    "lines_cap": {"shape": "cap_map", "gap": False,
        "desc": "活跃线索配额 {active_foreshadows, longline_foreshadows, active_knowledge, active_misunderstandings}",
        "example": {"active_foreshadows": 8, "longline_foreshadows": 5,
                    "active_knowledge": 5, "active_misunderstandings": 4}},
}
WORDLIST_SPEC = {k: v["desc"] for k, v in PARAM_SPEC.items() if v.get("gap")}


def param_suggestions(book: Path, top: int = 12) -> dict:
    proj = common.load_json(book / "project.json", default={}) or {}
    texts = [t for _, _, t in evidence.final_chapters(book)]
    full = "\n".join(texts)
    sugg: dict[str, list] = {}

    configured_stop = {str(w).strip() for w in (proj.get("generic_stopwords") or [])}
    alias_hits: list[tuple[str, int, str]] = []
    for e in state.load_state(book, "entities").get("entries", []):
        if e.get("status", "active") != "active":
            continue
        for a in e.get("aliases", []):
            a = str(a).strip()
            if not a or len(a) > 2 or a == str(e.get("name", "")).strip() or a in configured_stop:
                continue
            c = full.count(a)
            if c >= 3:
                alias_hits.append((a, c, str(e.get("name", ""))))
    sugg["generic_stopwords"] = [
        {"word": w, "count": c, "of_entity": en}
        for w, c, en in sorted(alias_hits, key=lambda x: -x[1])[:top]]

    known: list[str] = [str(proj.get("protagonist", "")).strip()]
    for e in state.load_state(book, "entities").get("entries", []):
        known.append(str(e.get("name", "")))
        known.extend(str(a) for a in e.get("aliases", []) if a)
    known = [k for k in known if k]
    base = _CAND_STOP | configured_stop | {str(w).strip() for w in (proj.get("candidate_stopwords") or [])}
    try:
        _sugg_pools = state.load_state(book, "ledger").get("pools", {})
    except (ValueError, FileNotFoundError):
        _sugg_pools = {}
    # QA P3：账本池名/单位并入已知词（与 verify_candidates 同口径，防「灵通」类片段误报）
    for p in _sugg_pools.values():
        for t in (p.get("name"), p.get("unit")):
            if t:
                known.append(str(t))
    grams: dict[str, int] = {}
    # QA P3：候选最小长度 3（2 字碎片「了一 ×35」类语法噪声不再进入候选）
    for seg in re.split(r"[^\u4e00-\u9fff]+", full):
        if len(seg) >= 2:
            for L in (3, 4):
                for i in range(len(seg) - L + 1):
                    g = seg[i:i + L]
                    grams[g] = grams.get(g, 0) + 1
    cands = []
    for g, c in grams.items():
        if c < 6 or g in base or any(s in g for s in base):
            continue
        if evidence.is_candidate_noise(g, _sugg_pools):
            continue
        if any((g in k) or (k in g) for k in known):
            continue
        cands.append((g, c))
    cands = [(g, c) for g, c in cands if not any(g != g2 and g in g2 and c2 >= c for g2, c2 in cands)]
    sugg["candidate_stopwords"] = [
        {"word": g, "count": c} for g, c in sorted(cands, key=lambda x: -x[1])[:top]]

    return {"kind": "config_suggest", "final_chapters_scanned": len(texts),
            "suggestions": sugg,
            "adopt": "采纳手势：python studio.py config set <键> --merge '<JSON数组>'（并入现有值；"
                     "判断采纳与否属语义裁决，归主控）"}


def validate_param_value(key: str, value) -> str | None:
    spec = PARAM_SPEC.get(key)
    if spec is None:
        return f"未知参数键「{key}」（合法键清单见 `python studio.py config guide`）"
    shape = spec["shape"]
    eg = json.dumps(spec["example"], ensure_ascii=False)
    if shape == "str_list":
        if not isinstance(value, list) or any(not isinstance(w, str) for w in value):
            return f"「{key}」必须是字符串数组（形状示例：{eg}）"
    elif shape == "hook_tiers":
        if not isinstance(value, dict):
            return f"「{key}」必须是对象（形状示例：{eg}）"
        extra = set(value) - {"strong", "suspense", "anticlimax"}
        if extra:
            return f"「{key}」含未知分档 {sorted(extra)}（合法分档：strong/suspense/anticlimax）"
        for tier, ws in value.items():
            if not isinstance(ws, list) or any(not isinstance(w, str) for w in ws):
                return f"「{key}.{tier}」必须是字符串数组"
    elif shape == "str_map":
        if (not isinstance(value, dict)
                or any(not isinstance(k, str) or not isinstance(v, list)
                       or any(not isinstance(w, str) for w in v) for k, v in value.items())):
            return f"「{key}」必须是 字段名→字符串数组 的对象（形状示例：{eg}）"
    elif shape == "int_pair":
        # 亦容忍字符串形态："[2000, 3000]"（JSON）或 "2000,3000" / "2000 3000"（逗号/空格，中文逗号亦容忍）
        if isinstance(value, str):
            s = value.strip()
            try:
                value = json.loads(s) if s.startswith("[") else [int(p) for p in re.split(r"[,，\s]+", s) if p]
            except (ValueError, TypeError):
                value = None
        if (not isinstance(value, list) or len(value) != 2
                or any(not isinstance(x, int) or isinstance(x, bool) or x < 1 for x in value)):
            return f"「{key}」必须是 [下限, 上限] 正整数对（形状示例：{eg} 或字符串 \"2000,3000\"）"
        if value[0] > value[1]:
            return f"「{key}」下限不能大于上限：{value}"
    elif shape == "cap_map":
        allowed_keys = {"active_foreshadows", "longline_foreshadows", "active_knowledge",
                        "active_misunderstandings"}
        if (not isinstance(value, dict) or not value
                or any(not isinstance(k, str) or k not in allowed_keys
                       or not isinstance(v, int) or isinstance(v, bool) or v < 1
                       for k, v in value.items())):
            return f"「{key}」必须是 配额键→正整数 的对象（合法键 {sorted(allowed_keys)}，形状示例：{eg}）"
    return None

_WORDS_BAND_RE = re.compile(r"(\d+)\s*[-–—~～]\s*(\d+)")


def _words_band(s: str) -> tuple[int | None, int | None]:
    m = _WORDS_BAND_RE.search(s or "")
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _style_knobs(s: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in re.split(r"[|｜]", s or "") if p.strip())


def _numbered_items(lines: list[str]) -> dict[int, str]:
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
    beats = [f for f in common.find_chapter_files(book, "beats")
             if common.chapter_number_from_name(f.name) == common.chapter_token_to_num(ch)]
    k = 0
    if beats:
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
    EVIDENCE_QUOTE_RE = re.compile(r"[「“\"'『]")
    EVIDENCE_FIELD_RE = re.compile(r"[A-Za-z_][\w]*[:：]\s*[\d.]+|[A-Za-z_]+\s*=\s*[\d.]+")
    for n, line in sorted(items.items()):
        if not re.search(r"[✓✗×√]", line):
            issues.append(f"验收 {n} 无 ✓/✗ 判定符")
        elif not (EVIDENCE_QUOTE_RE.search(line) or EVIDENCE_FIELD_RE.search(line)):
            issues.append(f"验收 {n} 打了判定符但无证据（须含正文引文或 evidence 字段名+数值）")
    return issues


def review_skeleton(book: Path, ch: str) -> dict:
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
            facts["error"] = f"状态不可读，三方对照降级: {exc}"
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
            if str(g.get("status", "")).strip().lower() != resolved.lower() and isinstance(t, int) and t <= n:
                due.append({"id": g["id"], "target_ch": t})
    facts["due_lines"] = due
    ops = sorted({str(g.get("id")) for g in (proposal.get("lines") or [])
                  if isinstance(g, dict) and g.get("id") and g.get("action", "plant") != "plant"})
    facts["lines_ops_in_proposal"] = ops
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
    infos: list[dict] = []
    stats: dict = {}

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

    if proj:
        for wl_key, wl_desc in WORDLIST_SPEC.items():
            if wl_key not in proj:
                infos.append(_err("wordlist_unconfigured",
                                  f"project.json 未配置「{wl_key}」（{wl_desc}）——对应启发式档已跳过；"
                                  "请主控按本书题材供参后生效（空表 = 明确关闭）"
                                  "（形状与示例见 `python studio.py config guide`）"))
        for pkey in PARAM_SPEC:
            if pkey in proj:
                shape_err = validate_param_value(pkey, proj[pkey])
                if shape_err:
                    errors.append(_err("param_shape_invalid", f"project.json.{shape_err}"))

    for msg in state.verify_state(book):
        errors.append(_err("state_inconsistent", msg))

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
        # 别名冲突与悬空关系边（advisory，QA P2-9）
        owner_by_alias: dict[str, list[str]] = {}
        ent_names = {str(e.get("name", "")) for e in ents}
        for e in ents:
            for a in {str(e.get("name", ""))} | {str(x) for x in e.get("aliases", []) if x}:
                owner_by_alias.setdefault(a, []).append(str(e.get("name", "")))
        for alias, owners in sorted(owner_by_alias.items()):
            if len(owners) > 1:
                warnings.append(_err("alias_conflict",
                                     f"别名「{alias}」被多个实体共享（{ '、'.join(owners[:4]) }）"
                                     "——mentions/pov/在场推断将产生歧义，请在 entities 中消歧"))
        for e in ents:
            for rel in e.get("relations", []) or []:
                tgt = str(rel.get("target", "")).strip()
                if tgt and tgt not in ent_names and tgt not in owner_by_alias:
                    warnings.append(_err("relation_target_unknown",
                                         f"实体「{e.get('name','')}」的关系指向未登记实体「{tgt}」"
                                         "（关系图悬空边：补登目标实体或修正拼写）"))
    except (ValueError, FileNotFoundError) as exc:
        errors.append(_err("state_unreadable", str(exc)))

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
        dup = [f for fs in vers.values() if len(fs) > 1 for f in fs]
        if dup:
            errors.append(_err("duplicate_final",
                               f"{vol} 第{n}章同版本号有多份定稿: {', '.join(f.name for f in dup)}"))
        top = max(vers)
        per_ch[(vol, n)] = vers[top][0]
    vol_nums: dict[str, list[int]] = {}
    for (vol, n) in per_ch:
        vol_nums.setdefault(vol, []).append(n)
    for vol, nums in sorted(vol_nums.items()):
        plan_start = None
        vol_outline = book / "outlines" / vol / "outline.md"
        if vol_outline.is_file():
            try:
                otext = vol_outline.read_text(encoding="utf-8", errors="ignore")
                # 只认阶段头里的范围对（ch_A—ch_B）作为规划起点证据（QA P1-4）：
                # 大纲自由文本里的 ch_NNN 提及（如「回收 ch_030 的暗线」）不再参与推断，
                # 且范围必须与本卷实际章号区间相交，防跨卷引用误判。
                ranges = re.findall(r"ch_(\d{1,4})\s*[—－\-~至到]\s*ch_(\d{1,4})", otext)
                starts = [int(a) for a, b in ranges
                          if int(a) >= 1 and int(b) >= int(a)
                          and int(a) <= max(nums) and int(b) >= min(nums)]
                if starts:
                    plan_start = min(starts)
            except OSError:
                pass
        # M3 修复：vol_01 不再无条件从 1 开始
        if plan_start is not None and plan_start < min(nums):
            start = plan_start
        elif vol == "vol_01":
            if plan_start is None and min(nums) > 1:
                # 无大纲规划且首章不是 1，不强制补 1，避免 false positive
                start = min(nums)
            else:
                start = 1
        else:
            start = min(nums)
        missing = sorted(set(range(start, max(nums) + 1)) - set(nums))
        if missing:
            errors.append(_err("final_gap_chapters",
                               f"{vol} final 章号断档: {missing}（第 {start} 与 {max(nums)} 章之间无定稿）"))
    stats["final_chapters"] = len(per_ch)

    slot_hits = []
    for md in sorted(book.rglob("*.md")):
        if md.is_symlink():
            continue
        try:
            # 防越界：resolve 后仍需在 book 内
            if md.resolve() != book and book.resolve() not in md.resolve().parents:
                continue
            if SLOT_RE.search(md.read_text(encoding="utf-8", errors="ignore")):
                slot_hits.append(md.relative_to(book).as_posix())
        except OSError:
            continue
    for rel in slot_hits:
        errors.append(_err("unfilled_slot", f"{rel} 存在未填充槽位 {{{{slot:...}}}}（Stage 0 未完成）"))

    ms = book / "manuscript"
    if ms.is_dir():
        for md in sorted(ms.rglob("*.md")):
            if md.is_symlink():
                continue
            try:
                if md.resolve() != book and book.resolve() not in md.resolve().parents:
                    continue
                if CANDIDATE_RE.search(md.read_text(encoding="utf-8", errors="ignore")):
                    errors.append(_err("candidate_leak",
                        f"{md.relative_to(book).as_posix()} 含 candidate_* 工程痕迹（AGENTS 防污染原则：稿件严禁工程标记）"))
            except OSError:
                continue

    beats = sorted(common.find_chapter_files(book, "beats"),
                   key=lambda p: (p.parts[-3] if len(p.parts) > 2 else "",
                                  common.chapter_number_from_name(p.name) or 0))
    ledger_line_ids: set[str] = set()
    open_due: list[tuple[int, str]] = []
    try:
        _lines_state = state.load_state(book, "lines")
        for _arr, _resolved in (("foreshadows", "Resolved"), ("misunderstandings", "Resolved"),
                                ("knowledge", "Revealed")):
            for _g in _lines_state.get(_arr, []):
                _gid = str(_g.get("id", ""))
                if _gid:
                    ledger_line_ids.add(_gid)
                if str(_g.get("status", "")).strip().lower() != _resolved.lower() and isinstance(_g.get("target_ch"), int):
                    open_due.append((_g["target_ch"], _gid))
    except (ValueError, FileNotFoundError):
        pass

    latest_final = max((n for _, n in per_ch.keys()), default=0)
    for tch, gid in open_due:
        if latest_final >= tch + 2:
            warnings.append(_err("plotline_starvation",
                                 f"伏笔/暗线 {gid} 预定 ch_{tch:03d} 解决，当前已连载至 ch_{latest_final:03d}（严重饥饿，请尽快安排回响或闭环）"))

    # 因果依赖图校验 (Prerequisite DAG Check)
    all_lines_map: dict[str, dict] = {}
    try:
        _lines_state = state.load_state(book, "lines")
        for _arr, _resolved_status in (("foreshadows", "Resolved"), ("misunderstandings", "Resolved"), ("knowledge", "Revealed")):
            for _item in _lines_state.get(_arr, []):
                if _item.get("id"):
                    all_lines_map[str(_item["id"])] = {
                        "kind": _arr,
                        "status": str(_item.get("status", "")),
                        "resolved_status": _resolved_status,
                        "requires": list(_item.get("requires") or [])
                    }
        for lid, info in all_lines_map.items():
            is_resolved = info["status"].lower() == info["resolved_status"].lower()
            for req_id in info["requires"]:
                if req_id not in all_lines_map:
                    warnings.append(_err("prerequisite_missing", f"线索 {lid} 依赖的前置线索 {req_id} 未在 lines 账本中注册"))
                elif is_resolved:
                    req_info = all_lines_map[req_id]
                    req_resolved = req_info["status"].lower() == req_info["resolved_status"].lower()
                    if not req_resolved:
                        errors.append(_err("prerequisite_unmet",
                                           f"因果逻辑冲突：线索 {lid} 已标记完成({info['status']})，但其前置依赖 {req_id} 仍未完成({req_info['status']})！",
                                           remedy=f"在 lines 账本中先推进并达成前置线索 {req_id}，或暂缓收束 {lid} 并将其状态退回 Active/Planted。"))

        # 检测循环依赖 (Cyclic Dependency Detection)——迭代式 DFS（QA P2-13：
        # 递归实现遇深层 requires 链会 RecursionError，曾被 except Exception 吞掉使守卫静默失效）
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {lid: WHITE for lid in all_lines_map}
        for root_id in all_lines_map:
            if color[root_id] != WHITE:
                continue
            stack = [(root_id, iter(all_lines_map[root_id].get("requires", [])))]
            color[root_id] = GRAY
            while stack:
                node, it = stack[-1]
                advanced = False
                for neighbor in it:
                    if neighbor not in all_lines_map:
                        continue
                    if color.get(neighbor, BLACK) == GRAY:
                        raise _FoundCycle(neighbor)
                    if color.get(neighbor, BLACK) == WHITE:
                        color[neighbor] = GRAY
                        stack.append((neighbor, iter(all_lines_map[neighbor].get("requires", []))))
                        advanced = True
                        break
                if not advanced:
                    color[node] = BLACK
                    stack.pop()
    except _FoundCycle as cyc:
        errors.append(_err("prerequisite_cycle",
                           f"因果逻辑冲突：线索 {cyc.node} 存在循环前置依赖！",
                           remedy=f"检查并解除线索 {cyc.node} 的前置依赖闭环，破除循环 requires 拓扑。"))
    except (OSError, ValueError) as exc:
        warnings.append(_err("lines_state_unreadable",
                             f"lines 账本不可读，因果依赖守卫降级跳过: {exc}"))

    empty_words = [w for w in (proj.get("empty_criteria_words") or [])
                   if isinstance(w, str) and w.strip()]
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
        planned_plants = set(re.findall(r"plant\s+((?:GUN|MIS|KNO)-\d{3,})", action_sec))
        orphans = sorted(set(re.findall(r"(?:GUN|MIS|KNO)-\d{3,}", action_sec)) - ledger_line_ids
                         - planned_plants)
        if orphans:
            warnings.append(_err("line_action_orphan",
                                 f"{f.name}: 线动作栏引用台账不存在的线 {', '.join(orphans[:5])}"
                                 "（先 plant 或核对 ID；计划本章 plant 的新线请写「plant GUN-XXX」格式以豁免）"))
        missing_ids = sorted({gid for t, gid in open_due if t <= num and gid not in action_sec})
        if missing_ids:
            warnings.append(_err("line_action_missing",
                                 f"{f.name}: 到期/逾期线 {', '.join(missing_ids[:5])} 未出现在「线动作」栏"
                                 "（不还须在 beats 写明顺延理由，归主控 Stage 1 裁决）"))

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

    if band_ok:
        lo, hi = band
        for tok, _, text in evidence.final_chapters(book):
            c = common.cjk_count(text)
            # QA P4：字数带双层判定——出带 15% 容差内 = info（软约束），
            # 显著出带（<下限 85% 或 >上限 115%）= warning（beats 硬合同口径）
            if c < lo * 0.85 or c > hi * 1.15:
                warnings.append(_err("word_band_breach",
                                     f"{tok}: 字数 {c} 显著偏离目标带 [{lo}, {hi}]（超出 15% 容差）"))
            elif c < lo or c > hi:
                infos.append(_err("word_band_deviation", f"{tok}: 字数 {c} 在目标带 [{lo}, {hi}] 之外"))

    for f in common.find_chapter_files(book, "final"):
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n_bad = t.count("\ufffd")
        if n_bad:
            warnings.append(_err("encoding_replacement_chars",
                                 f"{f.name}: 含 {n_bad} 个替换符（疑似非 UTF-8 编码保存，字数/统计口径已失真）"))

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

    try:
        lines_st = state.load_state(book, "lines")
        lcap = proj.get("lines_cap") or {}
        act_cap = lcap.get("active_foreshadows", 8)
        long_cap = lcap.get("longline_foreshadows", 5)
        open_act = [g for g in lines_st.get("foreshadows", []) if str(g.get("status", "")).strip().lower() != "resolved" and isinstance(g.get("target_ch"), int)]
        open_long = [g for g in lines_st.get("foreshadows", []) if str(g.get("status", "")).strip().lower() != "resolved" and g.get("target_ch") == "longline"]
        if len(open_act) > act_cap:
            warnings.append(_err("line_quota_exceeded",
                                 f"未结活动伏笔 {len(open_act)} 条 > 上限 {act_cap} 条（建议在后续章节优先回收 resolve，防僵尸伏笔堆积）"))
        if len(open_long) > long_cap:
            warnings.append(_err("longline_quota_exceeded",
                                 f"未结全书长线 {len(open_long)} 条 > 上限 {long_cap} 条（长线过多分散主线焦点）"))
        mis_cap = lcap.get("active_misunderstandings", 4)
        kno_cap = lcap.get("active_knowledge", 5)
        open_mis = [m for m in lines_st.get("misunderstandings", [])
                    if str(m.get("status", "")).strip().lower() != "resolved"]
        open_kno = [k for k in lines_st.get("knowledge", [])
                    if str(k.get("status", "")).strip().lower() != "revealed"]
        if len(open_mis) > mis_cap:
            warnings.append(_err("line_quota_exceeded",
                                 f"未澄清误会 {len(open_mis)} 条 > 上限 {mis_cap} 条（认知差堆积稀释主线，建议尽快安排澄清或合并同类）"))
        if len(open_kno) > kno_cap:
            warnings.append(_err("line_quota_exceeded",
                                 f"未揭示知识线 {len(open_kno)} 条 > 上限 {kno_cap} 条（秘密堆积稀释主线，建议尽快安排揭示节点）"))
    except (ValueError, FileNotFoundError):
        pass

    for vol, rec in evidence.form_distribution(book).items():
        if rec.get("count", 0) < 5:
            continue
        for form, share in rec.get("shares", {}).items():
            if share > FORM_SHARE_LIMIT:
                warnings.append(_err("form_share_over_limit",
                                     f"{vol}: form「{form}」占比 {share:.0%} > {FORM_SHARE_LIMIT:.0%}"))

    high_heat_forms = {w for w in (proj.get("high_heat_forms") or []) if isinstance(w, str) and w.strip()}
    for vol_dir in sorted((book / "outlines").glob("vol_*")) if high_heat_forms else []:
        beats_files = sorted(vol_dir.glob("beats/ch_*.md"))
        consecutive_high = []
        for bf in beats_files:
            try:
                fm = common.parse_front_matter(bf.read_text(encoding="utf-8", errors="replace"))
                form_val = str(fm.get("form", "")).strip()
                ch_tok = bf.stem
                is_high = form_val in high_heat_forms
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

    abstract_phrases = [w for w in (proj.get("abstract_phrases") or []) if isinstance(w, str) and w.strip()]
    for vol_dir in sorted((book / "outlines").glob("vol_*")) if abstract_phrases else []:
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

    protagonist = str(proj.get("protagonist", "")).strip()
    if protagonist:
        protagonist_names = {protagonist}
        try:
            ents = state.load_state(book, "entities").get("entries", [])
            for e in ents:
                if e.get("name") == protagonist:
                    protagonist_names.update(str(a) for a in e.get("aliases", []) if a)
        except (ValueError, OSError):
            pass  # 实体账本损坏：主角名册退化为仅主角本名，不做静默扩表

        finals = list(evidence.final_chapters(book))
        if len(finals) >= 2:
            low_streak = []
            for tok, path, text in finals[-3:]:
                paras = [p.strip() for p in text.split("\n") if len(p.strip()) > 10]
                if not paras:
                    continue
                hit = sum(1 for p in paras if any(name in p for name in protagonist_names))
                ratio = hit / len(paras)
                if ratio < 0.15:
                    low_streak.append((tok, ratio))
                else:
                    low_streak = []
            if len(low_streak) >= 2:
                chs_desc = "、".join(f"{t}（{r:.0%}）" for t, r in low_streak)
                warnings.append(_err("protagonist_pov_drift",
                                     f"主角视角失焦警报：最近连续 {len(low_streak)} 章 {chs_desc} 主角「{protagonist}」登场段落率低于 15%，疑似配角戏份喧宾夺主！建议在下一章强化主角的主动破局与核心对白！"))

    for vol_dir in sorted((book / "outlines").glob("vol_*")):
        beats_files = sorted(vol_dir.glob("beats/ch_*.md"))
        flatline_streak = []
        burnout_streak = []
        for bf in beats_files:
            try:
                fm = common.parse_front_matter(bf.read_text(encoding="utf-8", errors="replace"))
                raw_score = fm.get("tension_score")
                t_score = None
                if raw_score is not None:
                    try:
                        t_score = float(str(raw_score).strip())
                    except ValueError:
                        pass
                if t_score is not None:
                    ch_tok = bf.stem
                    if t_score <= 3:
                        flatline_streak.append(ch_tok)
                        burnout_streak = []
                        if len(flatline_streak) == 3:
                            warnings.append(_err("tension_flatline",
                                                 f"{vol_dir.name}: {flatline_streak[0]}—{flatline_streak[-1]} 连续 {len(flatline_streak)} 章张力评分 ≤ 3（情绪低迷平淡），读者极易产生枯燥感并弃更！建议在下一章制造外部危机打破僵局！"))
                    elif t_score >= 8:
                        burnout_streak.append(ch_tok)
                        flatline_streak = []
                        if len(burnout_streak) == 4:
                            warnings.append(_err("tension_burnout",
                                                 f"{vol_dir.name}: {burnout_streak[0]}—{burnout_streak[-1]} 连续 {len(burnout_streak)} 章张力评分 ≥ 8（超高压紧绷），建议在下一章安排「战后清点/爽感兑现」章型消化战利品，防止读者情绪疲劳！"))
                    else:
                        flatline_streak = []
                        burnout_streak = []
            except OSError:
                continue

    # final 定稿漂移检查（QA P2）：sync 封存时盖章的 final 哈希 vs 当前内容——
    # 封后再改 final 不再静默漂移，check 必报（有意修订走提案修订通道重封）
    try:
        fhp = book / "state" / "inbox" / "processed" / "final_hashes.json"
        if fhp.is_file():
            sealed = common.load_json(fhp, default={}) or {}
            for tok_rec in sorted(sealed):
                rec = sealed[tok_rec]
                if not isinstance(rec, dict):
                    continue
                want_sha = str(rec.get("sha256", ""))
                finals = common.find_chapter_files(book, "final", tok_rec)
                if not finals:
                    warnings.append(_err("final_drift",
                                         f"{tok_rec}: 封存定稿文件已不存在（sync 后 final 被删除？建议 snapshot rollback 恢复）"))
                    continue
                cur_sha = hashlib.sha256(finals[-1].read_bytes()).hexdigest()
                if want_sha and cur_sha != want_sha:
                    warnings.append(_err("final_drift",
                                         f"{tok_rec}: final 内容在封存后已改动（封存 {want_sha[:12]}… / 当前 {cur_sha[:12]}…）"))
    except (ValueError, OSError):
        pass

    # bible 版本盖章对照（info）：世界圣经在封存后又被改动 → 新旧章适用的世界规则可能不同
    try:
        jpath = book / "state" / "bible_log.jsonl"
        bible_path = book / "bible" / "project_bible.md"
        if jpath.is_file() and bible_path.is_file():
            last_ch, last_sha = "", ""
            for jline in jpath.read_text(encoding="utf-8", errors="replace").splitlines():
                jline = jline.strip()
                if not jline:
                    continue
                try:
                    rec = json.loads(jline)
                except json.JSONDecodeError:
                    continue
                if isinstance(rec, dict) and rec.get("bible_sha"):
                    last_ch, last_sha = str(rec.get("chapter", "")), str(rec["bible_sha"])
            cur_sha = hashlib.sha256(bible_path.read_bytes()).hexdigest()[:16]
            if last_ch and last_sha and cur_sha != last_sha:
                infos.append(_err("bible_drift",
                                  f"bible/project_bible.md 自 {last_ch} 封存后有改动——其后旧章系旧版规则所写，"
                                  "回溯修订或新设定生效时请对照 state/bible_log.jsonl 与「本书偏离清单」"))
    except OSError:
        pass

    # 新书 Stage 0 待办降级：纯未开工书（beats/raw/final 全空）且全部错误均为
    # unfilled_slot 时，未填模板属于「待办清单」而非数据损坏——降级为 infos 并放行；
    # 一旦存在任何创作活动，unfilled_slot 恢复硬闸门语义（防止带病开工）。
    onboarding = bool(errors) and all(e.get("code") == "unfilled_slot" for e in errors) \
        and all(not common.find_chapter_files(book, area)
                for area in ("beats", "raw", "final"))
    if onboarding:
        for e in errors:
            e["code"] = "stage0_onboarding"
            e["msg"] += "（新书 Stage 0 待办，暂不阻断；开写后恢复硬闸门）"
        infos.extend(errors)
        errors = []

    stats["errors"] = len(errors)
    stats["warnings"] = len(warnings)
    stats["infos"] = len(infos)
    return {"schema": "novel-studio.check/v1", "ok": not errors, "onboarding": onboarding,
            "errors": errors, "warnings": warnings, "infos": infos, "stats": stats}


def get_self_healing_remedies(book: Path, ch: str | None = None) -> list[dict]:
    """运行全书体检，并按章节或全书提取可供 AI 自愈的可执行处方。"""
    report = run_checks(book)
    out: list[dict] = []
    for e in report.get("errors", []):
        code = e.get("code", "unknown")
        rem = e.get("remedy") or DEFAULT_REMEDIES.get(code, "请根据错误信息核实并修改相应设定文件。")
        item = {
            "level": "error",
            "code": code,
            "msg": e.get("msg", ""),
            "remedy": rem,
            "can_auto_heal": e.get("can_auto_heal", True),
        }
        if "recompute" in rem or "ledger" in code:
            item["action_command"] = "python studio.py ledger recompute"
        # QA P1：旧 remedy 曾指向不存在的 `entity add` 命令，自愈指令解析分支一并移除；
        # 实体登记的唯一通道是 Reader 提案（remedy 文案已在 errcodes 更正）。
        out.append(item)

    for w in report.get("warnings", []):
        code = w.get("code", "unknown")
        rem = w.get("remedy") or DEFAULT_REMEDIES.get(code, "")
        item = {
            "level": "warning",
            "code": code,
            "msg": w.get("msg", ""),
            "remedy": rem,
            "can_auto_heal": w.get("can_auto_heal", True),
        }
        out.append(item)

    if ch:
        ch_num = common.chapter_token_to_num(ch)
        ch_tok = f"ch_{ch_num:03d}" if ch_num else str(ch)
        out.sort(key=lambda x: (0 if ch_tok in x["msg"] else 1, 0 if x["level"] == "error" else 1))

    return out

