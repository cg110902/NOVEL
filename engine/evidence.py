"""evidence：机械证据（mentions|gaps|dup|style|words|file|candidates|prev；all 聚合）。

原则 ：只数事实、零裁决——本模块输出里不允许出现「可疑/建议/达标」类语义词；
判断属于主控与子代理。空结果 = 合法事实（退出码 0）。支持 jieba 词性标注提取高精度专名候选与关键词，坚决不做主观文学裁决。
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from . import common, state

try:
    import jieba
    import jieba.posseg as pseg
    import jieba.analyse
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

SENT_SPLIT_RE = re.compile(r"[。！？!?…；\n]+")
QUOTE_LINE_RE = re.compile(r"^\s*[「“\"『]")
SHINGLE_N = 12
REP_MIN = 8

AI_CONSTRUCTIONS: list[tuple[str, str]] = [
    ("不是…而是…", r"不是[^。！？]{1,15}[，,]?\s*而是"),
    ("仿佛…一般", r"仿佛[^。！？]{0,15}(?:一般|般)"),
    ("宛如…一般", r"宛如[^。！？]{0,15}(?:一般|般)"),
    ("空气凝固/凝重", r"空气[^。！？]{0,8}(?:凝固|凝重|仿佛凝固)"),
    ("嘴角勾起/上扬", r"嘴角[^。！？]{0,6}(?:勾起|上扬|勾起一抹)"),
    ("眼底闪过", r"眼底[^。！？]{0,4}闪过"),
    ("心中一凛/一紧/暗道", r"心中[^。！？]{0,6}(?:一凛|一紧|暗道|一惊)"),
    ("眼神微凝/微眯/一缩", r"眼神[^。！？]{0,4}(?:微凝|一凝|微眯|猛地一缩)"),
    ("深吸一口气", r"深吸了一?口气|长舒了一?口气"),
    ("不由自主/不由得", r"不由自主地?|不由得"),
]


# --------------------------------------------------------------------------- 公共小件
def final_chapters(book: Path) -> list[tuple[str, int, str]]:
    """按 (卷, 章号) 升序的 [(ch_token, num, text)]，一章多文件时取版本号最大者（v10 > v2）。
    注意：key = (卷, 章号)，避免跨卷同章号互相覆盖（vol_02/ch_001 不会被 vol_01/ch_001 顶掉）。
    字数口径：仅去除首行章题标题行，保留正文中其他 # 开头的行（如“#号房”对话）。
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
                by_ch[key] = (f"{vol}/ch_{n:03d}", n, f)
    out = []
    for key in sorted(by_ch):
        tok, _, p = by_ch[key]
        raw = p.read_text(encoding="utf-8", errors="replace")
        # 仅去除首个非空标题行（以 # 开头），而非全文所有 # 行，避免误删正文对话
        lines = raw.splitlines()
        idx = 0
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        if idx < len(lines) and re.match(r"^\s*#", lines[idx]):
            # 标题行后保留其余
            body = "\n".join(lines[idx + 1:])
        else:
            body = raw
        out.append((tok, key[1], body))
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
    valid = [a for a in (aliases or []) if a and str(a).strip()]
    if not valid:
        return {}
    pat = re.compile("|".join(re.escape(a) for a in sorted(valid, key=len, reverse=True)))
    per = dict.fromkeys(valid, 0)
    for m in pat.finditer(text or ""):
        per[m.group(0)] += 1
    return per


def entity_lookup(book: Path, safe_aliases: bool = False) -> dict[str, list[str]]:
    ents = state.load_state(book, "entities")
    proj = common.load_json(book / "project.json", default={}) or {}
    all_stopwords = {str(w).strip() for w in (proj.get("generic_stopwords") or [])
                     if isinstance(w, str) and w.strip()}
    lookup = {}
    for e in ents.get("entries", []):
        if e.get("status", "active") != "active":
            continue
        primary = str(e.get("name", "")).strip()
        if not primary:
            continue
        names = [primary]
        for a in e.get("aliases", []):
            if not a:
                continue
            a_str = str(a).strip()
            if not a_str or a_str == primary:
                continue
            if safe_aliases and len(a_str) <= 2 and a_str in all_stopwords:
                continue
            if a_str not in names:
                names.append(a_str)
        lookup[primary] = names
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
        for name, aliases in lookup.items():
            if target in aliases:
                target = name
                break
    if target:
        if target not in lookup:
            return {"kind": "mentions", "error": f"实体「{target}」未登记（先在 entities.json/提案注册）",
                    "unknown": True}
        names = lookup[target]
    else:
        names = None
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
            "level": m.get("level"), "target_ch": t, "overdue": overdue,
            "idle_chapters": (cur - int(m.get("plant_ch") or 0)) if m.get("status") != "Resolved" and m.get("plant_ch") else 0})
    for k in lines.get("knowledge", []):
        t = k.get("target_ch")
        overdue = isinstance(t, int) and k.get("status") != "Revealed" and t < cur
        out["knowledge"].append({
            "id": k["id"], "secret": k.get("secret", ""), "status": k.get("status"),
            "plant_ch": k.get("plant_ch"), "target_ch": t, "weight": k.get("weight", 1),
            "overdue": overdue,
            "idle_chapters": (cur - int(k.get("plant_ch") or 0)) if k.get("status") != "Revealed" else 0})
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


_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "両": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}
_NUM_RE = r"[0-9][0-9,，]*|[零一二两両三四五六七八九十百千]{1,6}"


def _cn_num_to_int(s: str) -> int | None:
    if not s:
        return None
    if ("两" in s or "両" in s) and re.search(r"[一二三四五六七八九][两両]", s):
        return None
    total, num = 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            if num != 0 and ch in ("两", "両"):
                return None
            num = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            total += (num or 1) * _CN_UNITS[ch]
            num = 0
        else:
            return None
    return total + num


_GENERIC_UNITS = {"块", "枚", "张", "个", "粒", "颗", "只", "道", "本", "卷", "盒", "条", "段"}


def is_candidate_noise(g: str, ledger_pools: dict | None = None) -> bool:
    """候选新实体/泛词的机械毛刺过滤（改进：账本池名仅精确匹配才过滤，避免‘灵石’误杀‘灵石矿’）。"""
    if not g:
        return True
    head = g[0]
    if head in _CN_DIGITS or head in _CN_UNITS or head in _GENERIC_UNITS:
        return True
    if head in "把将被在":
        return True
    if head in "我你他她它咱您":
        return True
    for p in (ledger_pools or {}).values():
        for term in (p.get("name"), p.get("unit")):
            t = str(term or "").strip()
            if not t:
                continue
            # 仅精确相等才算噪音，子串不再误杀（修复 M5）
            if g == t:
                return True
            # 若池名是通用货币且长度<=2，且候选以该货币结尾但本身更长（如“灵石矿” vs “灵石”），不算噪音
            # 保留旧逻辑的宽松过滤仅对完全包含且长度相近的情况
            if len(t) >= 2 and len(g) == len(t) and t in g:
                return True
    return False


def _amount_scan(text: str, pools: dict) -> list[dict]:
    out = []
    for pid, p in (pools or {}).items():
        unit = str(p.get("unit") or "").strip()
        name = str(p.get("name") or "").strip()
        if not unit and not name:
            continue
        recs = []
        if unit in _GENERIC_UNITS:
            if name:
                patterns = [
                    rf"({_NUM_RE})\s*{re.escape(unit)}\s*(?:{re.escape(name)}|{re.escape(name[-2:])})",
                    rf"(?:{re.escape(name)}|{re.escape(name[-2:])})\s*({_NUM_RE})\s*{re.escape(unit)}",
                ]
                if len(name) >= 2:
                    patterns.append(rf"({_NUM_RE})\s*{re.escape(name)}")
            else:
                patterns = []
        else:
            patterns = [rf"({_NUM_RE})\s*{re.escape(unit)}"] if unit else []
            if name and name != unit:
                patterns.append(rf"({_NUM_RE})\s*{re.escape(name)}")

        for pat in patterns:
            for hit in re.finditer(pat, text):
                m = hit.group(1)
                nxt = text[hit.end():hit.end() + len(m) + len(unit) + 1] if unit else ""
                if unit and nxt.startswith(m) and nxt.startswith(unit, len(m)):
                    continue
                after_char = text[hit.end():hit.end() + 2]
                if unit == "两" and any(after_char.startswith(tc) for tc in ("日", "天", "月", "年", "个")):
                    continue
                if unit == "文" and any(after_char.startswith(tc) for tc in ("章", "篇", "件", "理", "武", "风", "字")):
                    continue
                pre_char = text[max(0, hit.start() - 3):hit.start()]
                if any(pre_char.endswith(x) for x in ("成百上", "成千上", "数以", "约有几", "好几")):
                    continue
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
    terms: list[str] = []
    if kind == "foreshadow":
        name = str(g.get("name", "")).strip()
        if name:
            terms.append(name)
        blob = name + " " + str(g.get("plan", ""))
    elif kind == "knowledge":
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
    prio_field = "level" if kind == "misunderstanding" else "weight"
    prio = g.get(prio_field)
    prio = int(prio) if isinstance(prio, int) and not isinstance(prio, bool) and prio >= 1 else 1
    t = g.get("target_ch")
    return (0 if isinstance(t, int) else 1, -prio, t if isinstance(t, int) else 0, str(g.get("id", "")))


def candidates(book: Path, ch: str) -> dict:
    n = common.chapter_token_to_num(ch)
    tok = f"ch_{n:03d}" if n else ch
    if not n:
        return {"kind": "candidates", "chapter": ch, "error": f"非法章号: {ch!r}"}
    # 处理多卷同章号：优先选卷号最大的（最新卷），并提示歧义
    all_finals = final_chapters(book)
    matched = [(t, num, text, Path(t)) for t, num, text in all_finals if num == n]
    if not matched:
        return {"kind": "candidates", "chapter": tok,
                "error": f"无 {tok} 的 final（工作单以 final 为源；数 raw 用 evidence file）"}
    if len(matched) > 1:
        # 按卷号排序，取最大卷
        def _vol_num(tok_str: str) -> int:
            m = common.VOL_RE.search(tok_str)
            return int(m.group(1)) if m else 0
        matched.sort(key=lambda x: _vol_num(x[0]))
        # 保留提示
        chosen_t, _, text = matched[-1][0], matched[-1][1], matched[-1][2]
        ambiguous = [m[0] for m in matched]
    else:
        chosen_t, _, text = matched[0][0], matched[0][1], matched[0][2]
        ambiguous = []
    out: dict = {"kind": "candidates", "chapter": tok, "source": "final"}
    if ambiguous:
        out["ambiguous_volumes"] = ambiguous
        out["chosen"] = chosen_t

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
                sk = line_sort_key(g, kind)
                if t <= n:
                    due.append((t, sk[1], sk[3], item))
                elif t <= n + 2:
                    upcoming.append((t, sk[1], sk[3], item))
            hits = {tm: text.count(tm) for tm in _line_terms_for(g, kind, reg_terms) if tm in text}
            if hits:
                line_hits.append({"id": g["id"], "kind": kind,
                                  "label": str(g.get("name", g.get("parties", g.get("secret", "")))),
                                  "target_ch": t, "hits": hits})
    due = [p[3] for p in sorted(due, key=lambda p: (p[1], p[0], p[2]))]
    upcoming = [p[3] for p in sorted(upcoming, key=lambda p: (p[1], p[0], p[2]))]
    out["line_hits"] = line_hits
    out["due_lines"] = due
    out["upcoming_lines"] = upcoming

    led = state.load_state(book, "ledger")
    out["amounts"] = _amount_scan(text, led.get("pools"))
    out["ledger_now"] = {pid: p.get("current") for pid, p in (led.get("pools") or {}).items()}

    markers = []
    for f in common.find_chapter_files(book, "beats", n):
        for i, ln in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if re.search(r"新实体\s*[→>]\s*注册", ln):
                markers.append({"line": i, "text": ln.strip()[:80]})
    out["new_entity_markers"] = markers

    per = {}
    for name, aliases in lookup.items():
        c = sum(count_aliases(text, aliases).values())
        if c:
            per[name] = c
    out["present_candidates"] = per

    proper_nouns = []
    if _HAS_JIEBA:
        known_all = set(lookup.keys())
        for aliases in lookup.values():
            known_all.update(aliases)
        for w, flag in pseg.cut(text):
            if flag in ("nr", "ns", "nt", "nz") and 2 <= len(w) <= 6:
                if w not in known_all and not is_candidate_noise(w, led.get("pools")):
                    proper_nouns.append(w)
        counts = {}
        for w in proper_nouns:
            counts[w] = counts.get(w, 0) + 1
        proper_nouns = [w for w, _ in sorted(counts.items(), key=lambda x: -x[1])[:10]]
    out["proper_noun_candidates"] = proper_nouns

    cur = state.load_state(book, "current")
    out["state_digest"] = {k: v for k, v in cur.items() if v not in ("", [], None)}

    out["quote_balance"] = {q: text.count(q) for q in "「」“”『』"}
    out["residue"] = {"slot": len(re.findall(r"\{\{\s*slot:", text)),
                      "candidate": len(re.findall(r"candidate_", text))}
    return out


def prev_contrast(book: Path, ch: str) -> dict:
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

    hooks = []
    for past_n in range(max(1, n - 3), n):
        pf = common.find_chapter_files(book, "final", past_n)
        if pf:
            h = detect_chapter_hook(pf[-1].read_text(encoding="utf-8", errors="replace"),
                                    hook_words(book))
            hooks.append((f"ch_{past_n:03d}", h["type"]))
    out["recent_hooks"] = hooks
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


def hook_words(book: Path) -> dict | None:
    proj = common.load_json(book / "project.json", default={}) or {}
    raw = proj.get("hook_words")
    if not isinstance(raw, dict):
        return None
    return {tier: [str(w).strip() for w in (raw.get(tier) or []) if str(w).strip()]
            for tier in ("strong", "suspense", "anticlimax")}


def detect_chapter_hook(text: str, words: dict | None = None) -> dict:
    paras = _paragraphs(text)
    tail = "\n".join(paras[-3:]) if paras else text[-300:]
    tail_clean = tail.strip().rstrip("」』”’\"')）】…。")
    ends_hook = bool(tail_clean) and tail_clean[-1] in "？！?!"
    words = words or {}
    tiers = {t: [w for w in (words.get(t) or []) if w]
             for t in ("strong", "suspense", "anticlimax")}

    def _hit(ws: list[str]) -> bool:
        return any(w in tail for w in ws)

    if ends_hook or _hit(tiers["strong"]):
        return {"type": "强钩", "detail": tail.strip()[:60]}
    elif _hit(tiers["suspense"]):
        return {"type": "悬置", "detail": tail.strip()[:60]}
    elif _hit(tiers["anticlimax"]):
        return {"type": "反高潮", "detail": tail.strip()[:60]}
    else:
        return {"type": "弱收", "detail": tail.strip()[:60]}


def dup(book: Path, ch: str | None = None) -> dict:
    full = final_chapters(book)
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
    sents = _sentences(text)
    lens = [len(re.sub(r"\s+", "", s)) for s in sents] or [0]
    mean = sum(lens) / len(lens)
    var = sum((x - mean) ** 2 for x in lens) / len(lens)
    total_chars = sum(lens) or 1
    paras = _paragraphs(text)
    heads = [re.sub(r"^[^\u4e00-\u9fffA-Za-z0-9]+", "", p)[:2] for p in paras]
    lines = [ln for ln in text.splitlines() if ln.strip()]
    dialogue_lines = sum(1 for ln in lines if QUOTE_LINE_RE.match(ln))
    cons = {name: len(re.findall(pat, text)) for name, pat in AI_CONSTRUCTIONS}
    guards = {g: text.count(g) for g in guard_words if isinstance(g, str) and g}
    top_tags = jieba.analyse.extract_tags(text, topK=8) if _HAS_JIEBA else []
    return {"cjk": common.cjk_count(text), "sentences": len(lens),
            "len_mean": round(mean, 1), "len_stdev": round(math.sqrt(var), 1),
            "max_share": round(max(lens) / total_chars, 3),
            "dialogue_line_ratio": round(dialogue_lines / max(1, len(lines)), 3),
            "para_head_repeat": len(heads) - len(set(heads)), "para_count": len(paras),
            "ai_constructions": cons, "style_guards_hits": guards, "top_keywords": top_tags}


def file_stats(book: Path, rel: str, ch: str | None = None) -> dict:
    base = book.resolve()
    # 使用 safe_child_path 统一校验越界与 symlink
    try:
        path = common.safe_child_path(book, rel)
    except ValueError as exc:
        return {"error": f"路径越界或不存在: {exc}"}
    if not path.is_file():
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
