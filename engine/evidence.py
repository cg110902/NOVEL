"""evidence：机械证据（mentions|gaps|dup|style|words|file|candidates|prev；all 聚合）。

原则 ：只数事实、零裁决——本模块输出里不允许出现「可疑/建议/达标」类语义词；
判断属于主控。空结果 = 合法事实（退出码 0）。全部纯 regex/算术，禁一切 NLP 依赖。
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from . import common, state

SENT_SPLIT_RE = re.compile(r"[。！？!?…；\n]+")
QUOTE_LINE_RE = re.compile(r"^\s*[「“\"『]")
SHINGLE_N = 12
REP_MIN = 8  # 整句自重复的最小句长（低于此的短句重复属正常修辞）

# 6 个中文 AI 高频句式（§5.7 拟人保险丝的固定清单；书级 tics 由 project.style_guards 追加）
AI_CONSTRUCTIONS: list[tuple[str, str]] = [
    ("不是…而是…", r"不是[^。！？]{1,15}[，,]?\s*而是"),
    ("仿佛…一般", r"仿佛[^。！？]{0,15}(?:一般|般)"),
    ("空气凝固/凝重", r"空气[^。！？]{0,8}(?:凝固|凝重|仿佛凝固)"),
    ("嘴角勾起/上扬", r"嘴角[^。！？]{0,6}(?:勾起|上扬|勾起一抹)"),
    ("眼底闪过", r"眼底[^。！？]{0,4}闪过"),
    ("心中一凛/一紧/暗道", r"心中[^。！？]{0,6}(?:一凛|一紧|暗道|一惊)"),
]


# --------------------------------------------------------------------------- 公共小件
def final_chapters(book: Path) -> list[tuple[str, int, str]]:
    """按 (卷, 章号) 升序的 [(ch_token, num, text)]，一章多文件时取版本号最大者（v10 > v2）。
    注意：key = (卷, 章号)，避免跨卷同章号互相覆盖（vol_02/ch_001 不会被 vol_01/ch_001 顶掉）。
    """
    by_ch: dict[tuple[str, int], tuple[str, int, Path]] = {}
    for f in common.find_chapter_files(book, "final"):
        n = common.chapter_number_from_name(f.name)
        if n is not None:
            try:
                vol = f.relative_to(book / "manuscript").parts[0]
            except ValueError:
                vol = ""
            key = (vol, n)
            cur = by_ch.get(key)
            if cur is None or common.chapter_version_from_name(f.name) > common.chapter_version_from_name(cur[2].name):
                # P3-13: token 带卷前缀，跨卷同章号不再产生重名 ch_XXX
                by_ch[key] = (f"{vol}/ch_{n:03d}", n, f)
    out = []
    for key in sorted(by_ch):
        tok, _, p = by_ch[key]
        raw = p.read_text(encoding="utf-8", errors="replace")
        out.append((tok, key[1], re.sub(r"^\s*#.*$", "", raw, flags=re.M)))  # 字数口径=正文，不含标题行
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT_RE.split(text or "") if len(s.strip()) >= 2]


def _shingles(sents: list[str], n: int = SHINGLE_N) -> set[str]:
    out = set()
    for s in sents:
        z = re.sub(r"[\s，。！？、；：「」『』“”‘’\"'（）()《》〈〉—…·\-~,.;:?!]", "", s)
        out.update(z[i:i + n] for i in range(0, max(0, len(z) - n + 1)))
    return out


def count_aliases(text: str, aliases: list[str]) -> dict[str, int]:
    """最长优先的非重叠计数：「当铺赵四」命中后其内嵌「赵四」不重复计。

    过滤空串别名（避免空正则匹配全文）；无有效别名时返回空 dict，绝不崩溃。
    """
    valid = [a for a in (aliases or []) if a and str(a).strip()]
    if not valid:
        return {}
    pat = re.compile("|".join(re.escape(a) for a in sorted(valid, key=len, reverse=True)))
    per = dict.fromkeys(valid, 0)
    for m in pat.finditer(text or ""):
        per[m.group(0)] += 1
    return per


def entity_lookup(book: Path) -> dict[str, list[str]]:
    """注册名 → 检索词列表（含自身；只查 active）。"""
    ents = state.load_state(book, "entities")
    lookup = {}
    for e in ents.get("entries", []):
        if e.get("status", "active") != "active":
            continue
        names = [e["name"]] + [a for a in e.get("aliases", []) if a and a != e["name"]]
        lookup[e["name"]] = names
    return lookup


# --------------------------------------------------------------------------- kinds
def words(book: Path) -> dict:
    chapters = []
    for tok, _, text in final_chapters(book):
        chapters.append({"chapter": tok, "cjk": common.cjk_count(text),
                         "sentences": len(_sentences(text))})
    cjks = [c["cjk"] for c in chapters]
    spread = (max(cjks) - min(cjks)) if cjks else 0
    mean = (sum(cjks) / len(cjks)) if cjks else 0.0
    stdev = round(math.sqrt(sum((x - mean) ** 2 for x in cjks) / len(cjks)), 1) if len(cjks) > 1 else 0.0
    return {"kind": "words", "chapter_count": len(chapters),
            "total_cjk": sum(cjks), "cjk_spread": spread, "cjk_stdev": stdev, "chapters": chapters}


def mentions(book: Path, target: str | None = None) -> dict:
    lookup = entity_lookup(book)
    if target and target not in lookup:
        for name, aliases in lookup.items():  # 允许用别名查询
            if target in aliases:
                target = name
                break
    if target:
        if target not in lookup:
            return {"kind": "mentions", "error": f"实体「{target}」未登记（先在 entities.json/提案注册）",
                    "unknown": True}
        names = lookup[target]
    else:
        names = None  # 总表模式
    chapters = final_chapters(book)
    items = []
    for tok, _, text in chapters:
        if names is not None:
            per = count_aliases(text, names)
            total = sum(per.values())
            if total:
                items.append({"chapter": tok, "total": total, "by_alias": per})
        else:
            rec = {"chapter": tok, "by_entity": {}}
            for name, aliases in lookup.items():
                c = sum(count_aliases(text, aliases).values())
                if c:
                    rec["by_entity"][name] = c
            items.append(rec)
    if names is not None:
        totals = sum(c["total"] for c in items)
        return {"kind": "mentions", "target": target, "aliases": names, "total": totals,
                "first_chapter": items[0]["chapter"] if items else None,
                "last_chapter": items[-1]["chapter"] if items else None,
                "chapters": items}
    return {"kind": "mentions", "mode": "registry_overview", "entities": len(lookup), "chapters": items}


def gaps(book: Path) -> dict:
    lines = state.load_state(book, "lines")
    cur = common.latest_chapter_number(book, "final")
    out = {"kind": "gaps", "max_final_chapter": cur, "foreshadows": [], "misunderstandings": [], "knowledge": []}
    for g in lines.get("foreshadows", []):
        t = g.get("target_ch")
        overdue = isinstance(t, int) and g.get("status") != "Resolved" and t < cur
        out["foreshadows"].append({
            "id": g["id"], "name": g.get("name", ""), "status": g.get("status"),
            "plant_ch": g.get("plant_ch"), "target_ch": t, "weight": g.get("weight", 1),
            "overdue": overdue,
            "idle_chapters": (cur - int(g.get("plant_ch") or 0)) if g.get("status") != "Resolved" else 0})
    for m in lines.get("misunderstandings", []):
        t = m.get("target_ch")
        overdue = isinstance(t, int) and m.get("status") != "Resolved" and t < cur
        out["misunderstandings"].append({
            "id": m["id"], "parties": m.get("parties", ""), "status": m.get("status"),
            "level": m.get("level"), "target_ch": t, "overdue": overdue})
    for k in lines.get("knowledge", []):
        t = k.get("target_ch")
        overdue = isinstance(t, int) and k.get("status") != "Revealed" and t < cur
        out["knowledge"].append({
            "id": k["id"], "secret": k.get("secret", ""), "status": k.get("status"),
            "plant_ch": k.get("plant_ch"), "target_ch": t, "weight": k.get("weight", 1),
            "overdue": overdue})
    # 逾期/到期清单排序（机械）：权重高者优先——多条线齐逾期时"先还哪条"有据
    out["foreshadows"].sort(key=lambda x: line_sort_key(x, "foreshadow"))
    out["misunderstandings"].sort(key=lambda x: line_sort_key(x, "misunderstanding"))
    out["knowledge"].sort(key=lambda x: line_sort_key(x, "knowledge"))
    out["summary"] = {"open_foreshadows": sum(1 for g in out["foreshadows"] if g["status"] != "Resolved"),
                      "overdue_foreshadows": sum(1 for g in out["foreshadows"] if g["overdue"]),
                      "open_misunderstandings": sum(1 for m in out["misunderstandings"] if m["status"] != "Resolved"),
                      "overdue_misunderstandings": sum(1 for m in out["misunderstandings"] if m["overdue"]),
                      "open_knowledge": sum(1 for k in out["knowledge"] if k["status"] != "Revealed"),
                      "overdue_knowledge": sum(1 for k in out["knowledge"] if k["overdue"])}
    return out


# --------------------------------------------------------------------------- 工作单小件（Stage 5 候选对照 / Stage 1 上章对照）
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "両": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}
_NUM_RE = r"[0-9][0-9,，]*|[零一二两両三四五六七八九十百千]{1,6}"


def _cn_num_to_int(s: str) -> int | None:
    """中文数词→整数（千位内常见形：三十/一百二/千五百；解不出返回 None，零语义）。"""
    if not s:
        return None
    total, num = 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            num = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            total += (num or 1) * _CN_UNITS[ch]
            num = 0
        else:
            return None
    return total + num


_GENERIC_UNITS = {"块", "枚", "张", "个", "粒", "颗", "只", "道", "本", "卷", "盒", "条", "段"}


def _amount_scan(text: str, pools: dict) -> list[dict]:
    """金额候选：阿拉伯/常见中文数词（千位内）× ledger 已声明池单位/名称。精准匹配货币上下文。"""
    out = []
    for pid, p in (pools or {}).items():
        unit = str(p.get("unit") or "").strip()
        name = str(p.get("name") or "").strip()
        if not unit and not name:
            continue
        recs = []
        # 若量词为常见泛指量词（如"块/枚"），必须紧邻货币名称（如"两块灵石"），杜绝"两块点心/青石板"误判
        if unit in _GENERIC_UNITS:
            if name:
                patterns = [
                    rf"({_NUM_RE})\s*{re.escape(unit)}\s*(?:{re.escape(name)}|{re.escape(name[-2:])})",
                    rf"(?:{re.escape(name)}|{re.escape(name[-2:])})\s*({_NUM_RE})\s*{re.escape(unit)}",
                ]
            else:
                patterns = []
        else:
            patterns = [rf"({_NUM_RE})\s*{re.escape(unit)}"] if unit else []
            if name and name != unit:
                patterns.append(rf"({_NUM_RE})\s*{re.escape(name)}")

        for pat in patterns:
            ms = re.findall(pat, text)
            for m in ms:
                v = int(m.replace(",", "").replace("，", "")) if m[0].isdigit() else _cn_num_to_int(m)
                if v is not None:
                    recs.append((v, m))
        if recs:
            samples = []
            for _, m in recs:
                sample = f"{m}{unit or name}"
                if sample not in samples:
                    samples.append(sample)
            out.append({"pool": pid, "unit": unit or name, "count": len(recs),
                        "values": sorted({v for v, _ in recs})[:8], "samples": samples[:3]})
    return out


def _line_terms_for(g: dict, kind: str, reg_terms: list[str]) -> list[str]:
    """从线台账条目提取计数词：整句 name/parties + 其中包含的注册名/别名 +
    （误会）parties 的分词。全部来自台账结构化字段，零正文 NLP。"""
    terms: list[str] = []
    if kind == "foreshadow":
        name = str(g.get("name", "")).strip()
        if name:
            terms.append(name)
        # plan 也是主控写的结构化线元数据：其中提到的注册名同样是本线的关键实体
        blob = name + " " + str(g.get("plan", ""))
    elif kind == "knowledge":
        # secret 是一整句事实，整句计数无意义——只数其中的注册名（与 foreshadow.plan 同口径）
        blob = str(g.get("secret", "")) + " " + str(g.get("note", ""))
    else:
        parties = str(g.get("parties", "")).strip()
        if parties:
            terms.append(parties)
        blob = parties + " " + str(g.get("content", ""))
    for a in reg_terms:
        if len(a) >= 2 and a in blob and a not in terms:
            terms.append(a)
    if kind == "misunderstanding":
        for tok in re.split(r"[、，,·×/\s]+", str(g.get("parties", ""))):
            if len(tok) >= 2 and tok not in terms:
                terms.append(tok)
    return terms


def line_sort_key(g: dict, kind: str) -> tuple:
    """台账线排序键（纯机械）：整数到期章在前（longline 殿后）→ 权重/级别高→低 → 章号 → ID。
    weight/level 是主控写的语义分级，引擎只用于排清单出数，不做判断。"""
    prio_field = "level" if kind == "misunderstanding" else "weight"
    prio = g.get(prio_field)
    prio = int(prio) if isinstance(prio, int) and not isinstance(prio, bool) and prio >= 1 else 1
    t = g.get("target_ch")
    return (0 if isinstance(t, int) else 1, -prio, t if isinstance(t, int) else 0, str(g.get("id", "")))


def candidates(book: Path, ch: str) -> dict:
    """Stage 5 工作单数据：以本章 final 为源做机器对照，只出数、零裁决。

    是否上账、是否动线的判断全归主控（AGENTS 宪法：语义边界）。
    """
    n = common.chapter_token_to_num(ch)
    tok = f"ch_{n:03d}" if n else ch
    if not n:
        return {"kind": "candidates", "chapter": ch, "error": f"非法章号: {ch!r}"}
    chs = [(t, num, text) for t, num, text in final_chapters(book) if num == n]
    if not chs:
        return {"kind": "candidates", "chapter": tok,
                "error": f"无 {tok} 的 final（工作单以 final 为源；数 raw 用 evidence file）"}
    _, _, text = chs[0]
    out: dict = {"kind": "candidates", "chapter": tok, "source": "final"}

    lines = state.load_state(book, "lines")
    lookup = entity_lookup(book)
    reg_terms = [a for names in lookup.values() for a in names]
    line_hits: list[dict] = []
    due: list[dict] = []
    upcoming: list[dict] = []
    for kind, arr_key in (("foreshadow", "foreshadows"), ("misunderstanding", "misunderstandings"),
                          ("knowledge", "knowledge")):
        for g in lines.get(arr_key, []):
            if g.get("status") == ("Resolved" if kind != "knowledge" else "Revealed"):
                continue
            t = g.get("target_ch")
            if isinstance(t, int):
                item = {"id": g["id"], "kind": kind, "target_ch": t}
                sk = line_sort_key(g, kind)  # 排序键在剥离权重前取，输出条目不携带权重
                if t <= n:
                    due.append((t, sk[1], sk[3], item))
                elif t <= n + 2:
                    upcoming.append((t, sk[1], sk[3], item))
            hits = {tm: text.count(tm) for tm in _line_terms_for(g, kind, reg_terms) if tm in text}
            if hits:
                line_hits.append({"id": g["id"], "kind": kind,
                                  "label": str(g.get("name", g.get("parties", g.get("secret", "")))),
                                  "target_ch": t, "hits": hits})
    # 统一口径：权重高→低，同级按到期章、再按 ID（与 gaps/pack/status 同一条排序）
    due = [p[3] for p in sorted(due, key=lambda p: (p[1], p[0], p[2]))]
    upcoming = [p[3] for p in sorted(upcoming, key=lambda p: (p[1], p[0], p[2]))]
    out["line_hits"] = line_hits
    out["due_lines"] = due
    out["upcoming_lines"] = upcoming

    # 金额候选：数字（阿拉伯/中文数词）× ledger 已声明池单位（币种不硬编码）
    led = state.load_state(book, "ledger")
    out["amounts"] = _amount_scan(text, led.get("pools"))
    out["ledger_now"] = {pid: p.get("current") for pid, p in (led.get("pools") or {}).items()}

    # beats 的 [新实体→注册] 标记（Stage 1 已做的语义活，Stage 5 只做登记对照）
    markers = []
    for f in common.find_chapter_files(book, "beats", n):
        for i, ln in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if re.search(r"新实体\s*[→>]\s*注册", ln):
                markers.append({"line": i, "text": ln.strip()[:80]})
    out["new_entity_markers"] = markers

    # 本章注册实体提及计数（填 present_characters 的对照数据）
    per = {}
    for name, aliases in lookup.items():
        c = sum(count_aliases(text, aliases).values())
        if c:
            per[name] = c
    out["present_candidates"] = per

    # current.json 非空字段（状态摘要；字段随 schema 扩展自动带上）
    cur = state.load_state(book, "current")
    out["state_digest"] = {k: v for k, v in cur.items() if v not in ("", [], None)}

    out["quote_balance"] = {q: text.count(q) for q in "「」“”『』"}
    out["residue"] = {"slot": len(re.findall(r"\{\{\s*slot:", text)),
                      "candidate": len(re.findall(r"candidate_", text))}
    return out


def prev_contrast(book: Path, ch: str) -> dict:
    """Stage 1 上章约束对照卡：上一章 form/旋钮/words/必须保留 + 本章（beats 若已写）+
    开放线概况。纯提取/算术，选不选、改不改归主控。"""
    n = common.chapter_token_to_num(ch)
    tok = f"ch_{n:03d}" if n else ch
    if not n:
        return {"kind": "prev", "chapter": ch, "error": f"非法章号: {ch!r}"}

    def _fields(path: Path) -> dict:
        text = path.read_text(encoding="utf-8", errors="replace")
        fm = common.parse_front_matter(text)
        must = [ln.strip().lstrip("-*· ").strip() for ln in common.md_section(text, r"^##\s*(?:必须保留|.*契约)")]
        return {"form": fm.get("form", ""), "form_reason": fm.get("form_reason", ""),
                "style_notes": fm.get("style_notes", ""), "pov": fm.get("pov", ""),
                "words": fm.get("words", ""), "guard_extra": fm.get("guard_extra", ""),
                "tension_curve": fm.get("tension_curve", ""),
                "must_keep": [s for s in must if s and not s.startswith(("<", "#"))]}

    out: dict = {"kind": "prev", "chapter": tok}
    prev_files = common.find_chapter_files(book, "beats", n - 1) if n > 1 else []
    out["prev"] = _fields(prev_files[-1]) if prev_files else None
    out["prev_tail"] = ""
    if n > 1:
        pf = common.find_chapter_files(book, "final", n - 1)
        if pf:
            out["prev_tail"] = pf[-1].read_text(encoding="utf-8", errors="replace")[-300:]
    cur_files = common.find_chapter_files(book, "beats", n)
    out["cur"] = _fields(cur_files[-1]) if cur_files else None

    lines = state.load_state(book, "lines")
    open_f = [g for g in lines.get("foreshadows", []) if g.get("status") != "Resolved"]
    open_m = [g for g in lines.get("misunderstandings", []) if g.get("status") != "Resolved"]
    open_k = [g for g in lines.get("knowledge", []) if g.get("status") != "Revealed"]
    out["open_lines"] = {"foreshadows": len(open_f), "misunderstandings": len(open_m), "knowledge": len(open_k)}
    due: list[dict] = []
    upcoming: list[dict] = []
    for g in open_f + open_m + open_k:
        t = g.get("target_ch")
        if isinstance(t, int):
            item = {"id": g["id"], "target_ch": t}
            if t <= n:
                due.append(item)
            elif t <= n + 2:
                upcoming.append(item)
    out["due_lines"] = due
    out["upcoming_lines"] = upcoming

    # 钩子连章与情绪心电图分析
    hooks = []
    for past_n in range(max(1, n - 3), n):
        pf = common.find_chapter_files(book, "final", past_n)
        if pf:
            h = detect_chapter_hook(pf[-1].read_text(encoding="utf-8", errors="replace"))
            hooks.append((f"ch_{past_n:03d}", h["type"]))
    out["recent_hooks"] = hooks
    # P3-8: 只出机械数据（末尾连续同型钩子长度），裁决性"建议"文案已移除——evidence 零语义承诺
    hook_run = None
    if hooks:
        last_type = hooks[-1][1]
        run_len = 0
        for _, h in reversed(hooks):
            if h == last_type:
                run_len += 1
            else:
                break
        if run_len >= 2:
            hook_run = {"type": last_type, "length": run_len}
    out["hook_run"] = hook_run
    return out


def detect_chapter_hook(text: str) -> dict:
    """分析章末结尾段落，判断章尾钩子类型（强钩 / 悬置 / 弱收 / 反高潮）。

    强钩判定（P3-9 收窄）：末段以 ？/！ 收束（剥离引号括号后），或命中强冲突关键词——
    不再把末 3 段任意位置的问号判为强钩（对话设问误报）。"""
    paras = _paragraphs(text)
    tail = "\n".join(paras[-3:]) if paras else text[-300:]
    tail_clean = tail.strip().rstrip("」』”’\"')）】…。")
    ends_hook = bool(tail_clean) and tail_clean[-1] in "？！?!"

    if ends_hook or re.search(r"杀局|大战|强敌|破空|压境|逼近|震天|大阵|战帖|叫阵|轰然|夺眶|撕裂|来不来", tail):
        return {"type": "强钩", "detail": tail.strip()[:60]}
    elif re.search(r"倒数|按在剑柄|蓄势|蓄力|深吸一口气|眼神一凝|一步踏出|悄然运转|锁死|阵法亮起", tail):
        return {"type": "悬置", "detail": tail.strip()[:60]}
    elif re.search(r"尴尬|噎住|打嗝|干咳|哭笑不得|无语|噗嗤|呆立|面面相觑|嘴角微抽", tail):
        return {"type": "反高潮", "detail": tail.strip()[:60]}
    else:
        return {"type": "弱收", "detail": tail.strip()[:60]}


def dup(book: Path, ch: str | None = None) -> dict:
    full = final_chapters(book)  # 只读一遍磁盘：单章模式与全书邻接对比共用同一份
    full_sh = [(t, _shingles(_sentences(x))) for t, _, x in full]
    n = common.chapter_token_to_num(ch) if ch is not None else None
    chapters = full if ch is None else [c for c in full if c[1] == n]
    within, pairs = [], []
    if ch is None:
        for (t1, s1), (t2, s2) in zip(full_sh, full_sh[1:], strict=False):
            shared = s1 & s2
            if shared:
                pairs.append({"pair": f"{t1}|{t2}", "shared_shingles": len(shared),
                              "examples": sorted(shared)[:3]})
    for tok, _, text in chapters:
        sents = _sentences(text)
        seen: dict[str, int] = {}
        for s in sents:
            z = re.sub(r"\s+", "", s)
            if len(z) >= REP_MIN:
                seen[z] = seen.get(z, 0) + 1
        rep = {k: v for k, v in seen.items() if v > 1}
        if ch is not None:
            own = _shingles(sents)
            prevs = [s for t, s in full_sh if common.chapter_number_from_name(t) == n - 1]
            if prevs:
                shared = own & prevs[0]
                if shared:
                    pairs.append({"pair": f"prev|{ch}", "shared_shingles": len(shared),
                                  "examples": sorted(shared)[:3]})
        if rep:
            within.append({"chapter": tok, "repeated_sentences": len(rep),
                           "examples": [f"×{v} {k[:24]}" for k, v in list(rep.items())[:3]]})
    return {"kind": "dup", "shingle_n": SHINGLE_N, "scope": "within_chapter+adjacent",
            "within": within, "adjacent_pairs": pairs}


def _stats_one(text: str, guard_words: list) -> dict:
    """单篇文本的全套计数——定稿扫描与草稿实测（file_stats）共用同一把尺。"""
    sents = _sentences(text)
    lens = [len(re.sub(r"\s+", "", s)) for s in sents] or [0]
    mean = sum(lens) / len(lens)
    var = sum((x - mean) ** 2 for x in lens) / len(lens)
    total_chars = sum(lens) or 1
    paras = _paragraphs(text)
    heads = [re.sub(r"^[^\u4e00-\u9fffA-Za-z0-9]+", "", p)[:2] for p in paras]  # 剥引号/标点起头再取两字
    lines = [ln for ln in text.splitlines() if ln.strip()]
    dialogue_lines = sum(1 for ln in lines if QUOTE_LINE_RE.match(ln))
    cons = {name: len(re.findall(pat, text)) for name, pat in AI_CONSTRUCTIONS}
    guards = {g: text.count(g) for g in guard_words if isinstance(g, str) and g}
    return {"cjk": common.cjk_count(text), "sentences": len(lens),
            "len_mean": round(mean, 1), "len_stdev": round(math.sqrt(var), 1),
            "max_share": round(max(lens) / total_chars, 3),
            "dialogue_line_ratio": round(dialogue_lines / max(1, len(lines)), 3),
            "para_head_repeat": len(heads) - len(set(heads)), "para_count": len(paras),
            "ai_constructions": cons, "style_guards_hits": guards}


def file_stats(book: Path, rel: str, ch: str | None = None) -> dict:
    """工作区内任意稿件的单篇实测（起草/改稿场景：数 raw，不装进定稿口径）。
    可选章节号 → 并入该章 beats 的 guard_extra（起草现场用本章禁忌同一把尺）。"""
    base = book.resolve()
    path = (book / rel).resolve()
    if base not in path.parents or not path.is_file():
        return {"error": f"工作区内找不到文件: {rel}"}
    proj = common.load_json(book / "project.json", default={}) or {}
    guards = list(proj.get("style_guards", []) or [])
    out: dict = {"kind": "file", "path": rel}
    if ch is not None:
        num = common.chapter_token_to_num(ch)
        extra = [w for w in _beats_guard_extra(book, num) if w and w not in guards]
        guards += extra
        if extra:
            out["guard_extra_scoped"] = extra
    text = path.read_text(encoding="utf-8", errors="replace")
    return {**out, **_stats_one(text, guards)}


def _beats_guard_extra(book: Path, num: int) -> list[str]:
    """本章 beats front-matter 的 guard_extra（竖线分隔）——章级禁忌的引擎可数化。"""
    for f in common.find_chapter_files(book, "beats"):
        if common.chapter_number_from_name(f.name) == num:
            fm = common.parse_front_matter(f.read_text(encoding="utf-8", errors="replace"))
            raw = fm.get("guard_extra", "")
            return [w.strip() for w in re.split(r"[|｜，,]", raw) if w.strip()]
    return []


def style(book: Path, ch: str | None = None) -> dict:
    chapters = []
    for tok, num, text in final_chapters(book):
        if ch is not None and num != common.chapter_token_to_num(ch):
            continue
        proj = common.load_json(book / "project.json", default={}) or {}
        guard_words = list(proj.get("style_guards", []) or [])
        extra = [w for w in _beats_guard_extra(book, num) if w not in guard_words]
        stats = _stats_one(text, guard_words + extra)
        if extra:
            stats["guard_extra_scoped"] = extra
        chapters.append({"chapter": tok, **stats})
    forms = form_distribution(book)
    return {"kind": "style", "chapters": chapters, "form_distribution": forms}


def _paragraphs(text: str) -> list[str]:
    body = re.sub(r"^#+.*$", "", text, flags=re.M)
    return [p.strip() for p in re.split(r"\n\s*\n", body) if len(p.strip()) >= 4]


def form_distribution(book: Path) -> dict:
    """按卷统计 beats front-matter 的 form（≤40% 上限的计数依据，判断留给主控）。"""
    out: dict[str, dict] = {}
    for f in sorted(common.find_chapter_files(book, "beats")):
        fm = common.parse_front_matter(f.read_text(encoding="utf-8", errors="replace"))
        parts = f.relative_to(book / "outlines").parts
        vol = parts[0] if parts else "vol_01"
        rec = out.setdefault(vol, {"forms": {}, "count": 0, "missing_form": []})
        tok = f.stem
        form = fm.get("form", "")
        if form:
            rec["forms"][form] = rec["forms"].get(form, 0) + 1
        else:
            rec["missing_form"].append(tok)
        rec["count"] += 1
    for rec in out.values():
        n = rec["count"] or 1
        rec["shares"] = {k: round(v / n, 3) for k, v in rec["forms"].items()}
    return out
