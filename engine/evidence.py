"""evidence：机械证据五 kind（mentions|gaps|dup|style|words）。

原则 ：只数事实、零裁决——本模块输出里不允许出现「可疑/建议/达标」类语义词；
判断属于审校 Agent 与主控。空结果 = 合法事实（退出码 0）。全部纯 regex/算术，禁一切 NLP 依赖。
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
                by_ch[key] = (f"ch_{n:03d}", n, f)
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
    out = {"kind": "gaps", "max_final_chapter": cur, "foreshadows": [], "misunderstandings": []}
    for g in lines.get("foreshadows", []):
        t = g.get("target_ch")
        overdue = isinstance(t, int) and g.get("status") != "Resolved" and t < cur
        out["foreshadows"].append({
            "id": g["id"], "name": g.get("name", ""), "status": g.get("status"),
            "plant_ch": g.get("plant_ch"), "target_ch": t, "overdue": overdue,
            "idle_chapters": (cur - int(g.get("plant_ch") or 0)) if g.get("status") != "Resolved" else 0})
    for m in lines.get("misunderstandings", []):
        t = m.get("target_ch")
        overdue = isinstance(t, int) and m.get("status") != "Resolved" and t < cur
        out["misunderstandings"].append({
            "id": m["id"], "parties": m.get("parties", ""), "status": m.get("status"),
            "level": m.get("level"), "target_ch": t, "overdue": overdue})
    out["summary"] = {"open_foreshadows": sum(1 for g in out["foreshadows"] if g["status"] != "Resolved"),
                      "overdue_foreshadows": sum(1 for g in out["foreshadows"] if g["overdue"]),
                      "open_misunderstandings": sum(1 for m in out["misunderstandings"] if m["status"] != "Resolved"),
                      "overdue_misunderstandings": sum(1 for m in out["misunderstandings"] if m["overdue"])}
    return out


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
