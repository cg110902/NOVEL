"""evidence：机械证据（mentions|gaps|dup|style|words|file|candidates|prev；all 聚合）。

原则 ：只数事实、零裁决——本模块输出里不允许出现「可疑/建议/达标」类语义词；
判断属于主控与子代理。空结果 = 合法事实（退出码 0）。支持 jieba 词性标注提取高精度专名候选与关键词，坚决不做主观文学裁决。
"""
from __future__ import annotations

import difflib
import json
import math
import re
from pathlib import Path

from . import common, state

try:
    import jieba
    import jieba.posseg as pseg
    import jieba.analyse
    try:
        # 压掉冷启动的「Building prefix dict...」初始化日志（走 stderr，
        # 会混进 Agent 的合并输出造成噪声；--json 的 stdout 本不受影响）
        jieba.setLogLevel(60)  # logging.CRITICAL
    except Exception:
        pass
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

SENT_SPLIT_RE = re.compile(r"[。！？!?…；\n]+")
QUOTE_LINE_RE = re.compile(r"^\s*[「“\"『]")
SHINGLE_N = 12
REP_MIN = 8
# QA P2-3：专名扫描的入选下限，evidence.names 与 checks.param_suggestions 共用同一常量，
# 避免两个工具阈值互不相交（实测 names 门槛 3 / suggest 门槛 6，输出零重叠，无可采纳项）。
NAME_SCAN_MIN_COUNT = 3

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

# QA P3/P18：候选噪声增强——
# 语法碎片字符（专名/实体名中几乎不可能出现，出现即碎片）
_GRAMMAR_NOISE_CHARS = set("的了着过")
# 通用地貌/方位词作词头的「普通名词」（山脚/水口/石边…），不当专名候选
_GENERIC_HEAD_CHARS = set("山水江河湖海溪谷岭崖峰岩石沙林田路街巷桥塔楼院村镇国门墙")
# 短词（≤3 字）以通用方位/位置后缀结尾 → 普通名词（山脚/河口/路边；黑风镇/落星谷不受影响）
_GENERIC_TAIL_CHARS = set("脚口边旁里外沿顶底下上")


def is_generic_locutive_noise(g: str) -> bool:
    """普通地名/方位词噪声判定（山脚、水口、石边一类），供候选与专名扫描共用。"""
    if not g:
        return False
    if any(c in _GRAMMAR_NOISE_CHARS for c in g):
        return True
    if g[0] in _GENERIC_HEAD_CHARS:
        return True
    if len(g) <= 3 and g[-1] in _GENERIC_TAIL_CHARS:
        return True
    return False


_NUM_CHARS = "零一二两三四五六七八九十百千半"
_MEASURE_CHARS = "个只盏枚条张块份人日天年月次趟遍回桩件颗粒道本卷盒段片层批群堆串束成倍分厘"
_LEAD_VERBS = "笞打骂问答笑哭走跑坐站看听说讲想念算数拿提搬推拉拆装找等送收买卖借还赔抵拘罚跪拜刨挖捡拾"
_TIME_HEADS = ("去年", "今年", "明年", "前年", "上季", "下季", "昨", "今早", "今儿", "明儿")
# 时间词（子串命中，兼容 n-gram 切片如「年冬天」）
_TIME_WORDS = ("冬天", "夏天", "春天", "秋天", "开春", "入冬", "年关", "月底", "年初", "年尾")


def is_candidate_noise(g: str, ledger_pools: dict | None = None,
                       known_names: list[str] | None = None) -> bool:
    """候选新实体/泛词的机械毛刺过滤（改进：账本池名仅精确匹配才过滤，避免‘灵石’误杀‘灵石矿’）。

    QA P3-10：原先 `candidate_new_entity` 信噪比接近 0（实测 ch_002 七条、ch_003 十条
    全是噪声：沉舟说 / 沉舟把 / 笞二十 / 半个饼 / 那十个 / 第十一条 / 去年冬天 / 这片滩 …）。
    每章十几条纯噪声会稀释真正的告警。现补六类**纯机械**可判定的噪声形态：
    ① 已知实体名的片段 + 尾随动词/介词（沉舟说、沉舟把）；
    ② 数字 + 量词（笞二十、半个饼、那十个、拘三日）；
    ③ 律条/序号引用（第十一条、第七条、司律第）；
    ④ 时间短语（去年冬天）；
    ⑤ 指示词 + 量词开头（这片滩）；
    ⑥ 叠字开头（年年刨）。
    """
    if not g:
        return True
    head = g[0]
    if head in _CN_DIGITS or head in _CN_UNITS or head in _GENERIC_UNITS:
        return True
    if head in "把将被在":
        return True
    if head in "我你他她它咱您":
        return True
    if is_generic_locutive_noise(g):
        return True
    # ① 已知实体名片段 + 尾随单字（多为动词/介词）：沉舟说 / 沉舟把
    if known_names and len(g) >= 3:
        stem = g[:-1]
        if any(len(nm) >= 2 and stem in nm for nm in known_names):
            return True
    # ② 数字 + 量词：笞二十 / 半个饼 / 那十个 / 拘三日
    if any(c in _NUM_CHARS for c in g) and any(c in _MEASURE_CHARS for c in g):
        return True
    # ③ 律条/序号：第十一条 / 第七条 / 司律第 / 到第十
    if "第" in g:
        return True
    # ④ 时间短语：去年冬天（含被 n-gram 切出的片段「年冬天」）
    if any(t in g for t in _TIME_HEADS) or any(t in g for t in _TIME_WORDS):
        return True
    # ⑤ 指示词 + 量词开头：这片滩 / 那些盏
    if head in "这那每" and len(g) >= 2 and g[1] in _MEASURE_CHARS:
        return True
    # ⑥ 叠字开头：年年刨 / 天天走（叠字本身即语法形态，不是专名）
    if len(g) >= 3 and g[0] == g[1]:
        return True
    # 前置动词 + 数字：笞二十 / 拘三日（已被 ② 覆盖时不重复判定）
    if head in _LEAD_VERBS and any(c in _NUM_CHARS for c in g[1:]):
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
            # QA P1-2：原实现是 sorted(distinct)[:8]——静默丢掉最大的金额，而大额恰恰是
            # 金额对照最该看的。改为「最小 4 + 最大 4」保序展示，并显式给出截断标记与
            # 全量集合（checks 的 amount_unmatched / amount_by_quote 一律用全量比对）。
            distinct = sorted({v for v, _ in recs})
            capped = len(distinct) > 8
            shown = distinct if not capped else sorted(set(distinct[:4]) | set(distinct[-4:]))
            out.append({"pool": pid, "unit": unit or name, "count": len(recs),
                        "values": shown, "all_values": distinct, "values_capped": capped,
                        "samples": samples[:3]})
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


def quote_balance(text: str) -> dict:
    """引号收支：全角 + ASCII 计数、配对判定。

    QA P2-7：原实现只数 `「」“”『』`，对 ASCII 引号全盲——实测三章定稿共用 96 个
    ASCII `"`，quote_balance 全 0，既没提示中文稿应改用全角引号，也没检查 ASCII 引号
    是否配对。现补 ASCII 计数 + 奇偶配对判定 + 全角引号自身配对判定。
    原先 `evidence.candidates` 与 `checks.review_skeleton` 各有一份重复实现，现共用本函数。
    """
    ascii_dq = text.count('"')
    ascii_sq = text.count("'")
    pairs = {q: text.count(q) for q in "「」“”『』"}
    unbalanced: list[str] = []
    for a, b in (("「", "」"), ("“", "”"), ("『", "』")):
        if pairs[a] != pairs[b]:
            unbalanced.append(f"{a}{b} {pairs[a]}/{pairs[b]}")
    if ascii_dq % 2:
        unbalanced.append(f'ASCII " 共 {ascii_dq} 个（奇数，必有一处未闭合）')
    if ascii_sq % 2:
        unbalanced.append(f"ASCII ' 共 {ascii_sq} 个（奇数）")
    return {
        **pairs,
        '"': ascii_dq,
        "'": ascii_sq,
        "ascii_quote_total": ascii_dq + ascii_sq,
        "unbalanced": unbalanced,
        "ascii_residue": bool(ascii_dq or ascii_sq),
        "note": ("中文稿应使用全角引号；ascii_residue=true 表示正文仍残留 ASCII 引号，"
                 "unbalanced 非空表示有引号未成对。"),
    }


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

    out["quote_balance"] = quote_balance(text)
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

        def _clean(ln: str) -> str:
            # QA P2-10：原实现只 lstrip("-*· ")，只吃掉行首记号，粗体的**闭合** `**`
            # 会残留（`- **核心看点**：…` → `核心看点**：…`），把 markdown 记号当正文
            # 喂给下游。现剥注释、剥列表记号、剥成对强调记号。
            s = re.sub(r"<!--.*?-->", "", ln, flags=re.S)
            s = re.sub(r"^[\s>*+\-·]+", "", s)
            s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
            s = re.sub(r"__(.+?)__", r"\1", s)
            s = s.replace("**", "").replace("__", "")
            s = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", r"\1", s)
            return s.strip()

        must = [_clean(ln) for ln in common.md_section(text, r"^##\s*(?:必须保留|.*契约)")]
        return {"form": fm.get("form", ""), "form_reason": fm.get("form_reason", ""),
                "style_notes": fm.get("style_notes", ""), "pov": fm.get("pov", ""),
                "words": fm.get("words", ""),
                "tension_curve": fm.get("tension_curve", ""),
                "must_keep": [s for s in must if s and not s.startswith(("#", "<"))]}

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


def _stats_one(text: str) -> dict:
    sents = _sentences(text)
    lens = [len(re.sub(r"\s+", "", s)) for s in sents] or [0]
    mean = sum(lens) / len(lens)
    var = sum((x - mean) ** 2 for x in lens) / len(lens)
    total_chars = sum(lens) or 1
    paras = _paragraphs(text)
    heads = [re.sub(r"^[^\u4e00-\u9fffA-Za-z0-9]+", "", p)[:2] for p in paras]
    lines = [ln for ln in text.splitlines() if ln.strip()]
    dialogue_lines = sum(1 for ln in lines if QUOTE_LINE_RE.match(ln))
    top_tags = jieba.analyse.extract_tags(text, topK=8) if _HAS_JIEBA else []
    return {"cjk": common.cjk_count(text), "sentences": len(lens),
            "len_mean": round(mean, 1), "len_stdev": round(math.sqrt(var), 1),
            "max_share": round(max(lens) / total_chars, 3),
            "dialogue_line_ratio": round(dialogue_lines / max(1, len(lines)), 3),
            "para_head_repeat": len(heads) - len(set(heads)), "para_count": len(paras),
            "top_keywords": top_tags}


def file_stats(book: Path, rel: str, ch: str | None = None) -> dict:
    base = book.resolve()
    # 使用 safe_child_path 统一校验越界与 symlink
    try:
        path = common.safe_child_path(book, rel)
    except ValueError as exc:
        return {"error": f"路径越界或不存在: {exc}"}
    if not path.is_file():
        return {"error": f"工作区内找不到文件: {rel}"}
    out: dict = {"kind": "file", "path": rel}
    text = path.read_text(encoding="utf-8", errors="replace")
    return {**out, **_stats_one(text)}


def style(book: Path, ch: str | None = None) -> dict:
    chapters = []
    for tok, num, text in final_chapters(book):
        if ch is not None and num != common.chapter_token_to_num(ch):
            continue
        stats = _stats_one(text)
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


# --------------------------------------------------------------------------- 只读取证三件套（ask / pov / names）
def ask(book: Path, query: str) -> dict:
    """ask：全书事实检索机（只读取证，零裁决）。

    查询词先做别名展开（实体名/别名双向包含、账本池名、线索 ID 直查），再对
    「六表结构化命中」与「final 正文原句」双域检索；所有命中均带章节/条目出处。
    未命中 = 合法事实（该词暂无账面与正文记录），绝不臆造。
    """
    q = str(query or "").strip()
    out: dict = {"kind": "ask", "query": q}
    if not q:
        out["error"] = "查询词为空（示例：studio ask 灵石 / ask 苏九娘 / ask GUN-001）"
        return out
    terms: list[str] = [q]

    # 1) 别名展开（实体）
    try:
        ents = state.load_state(book, "entities").get("entries", [])
    except (ValueError, FileNotFoundError):
        ents = []
    lookup = entity_lookup(book)
    ent_hits = []
    for e in ents:
        if e.get("status", "active") != "active":
            continue
        names = lookup.get(str(e.get("name", "")), [])
        if any(nm and len(nm) >= 2 and (nm in q or q in nm) for nm in names):
            ent_hits.append({k: e.get(k) for k in
                             ("name", "type", "aliases", "summary", "realm", "faction",
                              "life_status", "holder", "location") if e.get(k) not in (None, "", [])})
            terms.extend(nm for nm in names if nm not in terms)
    if ent_hits:
        out["entities"] = ent_hits[:8]

    # 2) 线索命中
    # QA P1-5：原实现只对 name/plan/secret/parties/... 做字面子串匹配，于是主角的
    # 全书驱动力线（如 GUN-003「娘的半缕残魂」——name 与 plan 里都没有主角名字）
    # 在 `ask 陆沉舟` 时整条漏掉；而 SKILL 的取证纪律是「凡要落笔一个旧数字且它不在
    # 眼前 → 必须先 ask」，漏召回直接导致主控凭印象编数。现补一层反向索引：
    #   a) holders 知情圈命中；
    #   b) 线所触章节（plant/update/escalate/remind/resolve/target）的定稿正文里
    #      出现过该实体名或别名 → 记为「同章在场」关联。
    # 直接字面命中仍排在前面，间接命中带 via 说明，主控可自行判断权重。
    try:
        lines = state.load_state(book, "lines")
    except (ValueError, FileNotFoundError):
        lines = {}
    # 逐章在场实体（名字/别名），供反向索引使用
    ch_entities: dict[int, set[str]] = {}
    try:
        _ent_names = [nm for nms in lookup.values() for nm in nms if nm and len(nm) >= 2]
    except Exception:
        _ent_names = []
    if _ent_names:
        for tok, _num, text in final_chapters(book):
            n = common.chapter_token_to_num(tok)
            if n:
                ch_entities[n] = {nm for nm in _ent_names if nm in text}

    def _touched_chapters(g: dict) -> set[int]:
        nums: set[int] = set()
        for k in ("plant_ch", "update_ch", "escalate_ch", "remind_ch", "resolve_ch", "target_ch"):
            v = g.get(k)
            if isinstance(v, list):
                nums.update(n for n in (common.chapter_token_to_num(x) for x in v) if n)
            else:
                n = common.chapter_token_to_num(v)
                if n:
                    nums.add(n)
        return nums

    direct: list[dict] = []
    indirect: list[dict] = []
    for arr, kind in (("foreshadows", "foreshadow"), ("misunderstandings", "misunderstanding"),
                      ("knowledge", "knowledge")):
        for g in lines.get(arr, []):
            gid = str(g.get("id", ""))
            blob = " ".join(str(g.get(k, "")) for k in
                            ("id", "name", "plan", "content", "parties", "truth", "secret", "note"))
            rec = {"id": gid, "kind": kind, "status": g.get("status"),
                   "target_ch": g.get("target_ch"),
                   "desc": str(g.get("name") or g.get("secret") or g.get("content") or "")[:60]}
            if q == gid or any(t in blob for t in terms):
                direct.append(rec)
                continue
            # 反向索引
            via = []
            holders = [str(h).strip() for h in (g.get("holders") or []) if str(h).strip()]
            if holders and any(nm and len(nm) >= 2 and any(nm in h or h in nm for h in holders)
                               for nm in terms):
                via.append("holders 知情圈")
            co = sorted(n for n in _touched_chapters(g)
                        if any(t in ch_entities.get(n, set()) for t in terms if len(t) >= 2))
            if co:
                via.append("同章在场 " + "/".join(f"ch_{n:03d}" for n in co[:3]))
            if via:
                indirect.append({**rec, "via": "；".join(via)})
    line_hits = direct + indirect
    if line_hits:
        out["lines"] = line_hits[:12]
        if indirect:
            out["lines_via_reverse_index"] = [r["id"] for r in indirect]

    # 3) 账本命中
    try:
        led = state.load_state(book, "ledger")
    except (ValueError, FileNotFoundError):
        led = {}
    pool_terms = set()
    for pid, p in (led.get("pools") or {}).items():
        for t in (pid, p.get("name"), p.get("unit")):
            t = str(t or "")
            if len(t) >= 2 and (t in q or q in t):
                pool_terms.add(pid)
    tx_hits = []
    for t in reversed(led.get("transactions") or []):
        subj = str(t.get("subject", ""))
        if t.get("pool") in pool_terms or any(s in subj for s in terms):
            tx_hits.append({"chapter": t.get("chapter"), "pool": t.get("pool"),
                            "delta": t.get("delta"), "subject": subj[:40],
                            "balance_after": t.get("balance_after")})
        if len(tx_hits) >= 8:
            break
    if tx_hits:
        out["ledger"] = tx_hits
        out["pools_now"] = {pid: p.get("current") for pid, p in (led.get("pools") or {}).items()}

    # 4) 编年史 / 危机时钟 / 梗概命中
    try:
        tl = state.load_state(book, "timeline")
    except (ValueError, FileNotFoundError):
        tl = {}
    ev_hits = [{"time": e.get("time"), "event": str(e.get("event", ""))[:60], "chapter": e.get("chapter")}
               for e in reversed(tl.get("events") or [])
               if any(s in str(e.get("event", "")) for s in terms)][:8]
    if ev_hits:
        out["events"] = ev_hits
    clock_hits = [{"name": c.get("name"), "target_ch": c.get("target_ch"), "status": c.get("status"),
                   "desc": str(c.get("desc", ""))[:50]}
                  for c in tl.get("clocks") or []
                  if any(s in (str(c.get("name", "")) + str(c.get("desc", ""))) for s in terms)]
    if clock_hits:
        out["clocks"] = clock_hits[:6]
    try:
        syn = state.load_state(book, "synopsis").get("chapters", {})
    except (ValueError, FileNotFoundError):
        syn = {}
    syn_hits = [{"chapter": tok, "title": v.get("title", ""), "synopsis": str(v.get("synopsis", ""))[:60]}
                for tok, v in sorted(syn.items())
                if any(s in (str(v.get("title", "")) + str(v.get("synopsis", ""))) for s in terms)]
    if syn_hits:
        out["synopsis"] = syn_hits[-6:]

    # 5) 现场快照命中
    try:
        cur = state.load_state(book, "current")
    except (ValueError, FileNotFoundError):
        cur = {}
    if any(s in json.dumps(cur, ensure_ascii=False, default=str) for s in terms):
        out["current"] = {k: v for k, v in cur.items() if v not in ("", [], None)}

    # 6) 正文原句证据（近章优先，仅用 ≥2 字词匹配）
    # QA P1-5：原实现每章只取第一句命中就 break，实测 ch_001 提及 18 次只回 1 句，
    # 主控拿到的证据面过窄。改为每章最多 3 句、总量 12 句。
    usable = [t for t in dict.fromkeys(terms) if len(t) >= 2]
    text_hits = []
    if usable:
        for tok, _, text in reversed(final_chapters(book)):
            per_ch = 0
            for sent in _sentences(text):
                hit_terms = [t for t in usable if t in sent]
                if hit_terms:
                    text_hits.append({"chapter": tok, "terms": hit_terms[:3],
                                      "quote": sent.strip()[:90]})
                    per_ch += 1
                    if per_ch >= 3:
                        break
            if len(text_hits) >= 12:
                break
    if text_hits:
        out["text_hits"] = text_hits
    out["notes"] = ["未命中 = 合法事实（账面与正文均无记录）；本命令只读取证、零裁决，语义判断归主控。"]
    return out


def pov(book: Path, name: str) -> dict:
    """pov：角色视角包（只读推导，advisory）。

    从现有账本推导「该角色此刻知道什么 / 不知道什么」：
    - 已揭示知识（KNO Revealed）+ 其登场章节的编年史事件 = 他应知信息（公开/亲历）；
    - 未揭示知识（KNO Concealed）= 按账本他不知情（若正文另有交代，以正文为准）。
    严禁据此硬写入正文——语义裁决归主控与起草员。
    """
    target = str(name or "").strip()
    out: dict = {"kind": "pov", "name": target}
    if not target:
        out["error"] = "角色名为空（示例：studio pov 苏九娘）"
        return out
    try:
        ents = state.load_state(book, "entities").get("entries", [])
    except (ValueError, FileNotFoundError):
        ents = []
    lookup = entity_lookup(book)
    resolved = None
    for primary, names in lookup.items():
        if target == primary or target in names:
            resolved = primary
            break
    if resolved is None:
        cands = [p for p, names in lookup.items()
                 if len(target) >= 2 and any(target in nm or nm in target for nm in names)]
        out["error"] = f"实体「{target}」未登记"
        if cands:
            out["candidates"] = cands[:8]
        return out

    e = next((x for x in ents if x.get("name") == resolved), {}) or {}
    names = lookup[resolved]
    out["resolved"] = resolved
    out["profile"] = {k: e.get(k) for k in
                      ("type", "aliases", "summary", "realm", "faction", "life_status",
                       "status", "attitude", "dossier", "golden_quote", "card")
                      if e.get(k) not in (None, "", [])}
    if e.get("charges") is not None:
        out["profile"]["charges"] = f"{e['charges']}/{e.get('max_charges', '?')}"

    carries = [{"name": it.get("name"), "location": it.get("location", ""),
                "condition": it.get("condition", ""), "charges": it.get("charges")}
               for it in ents
               if it.get("type") == "item" and it.get("status", "active") == "active"
               and str(it.get("holder", "")) in names]
    if carries:
        out["carries"] = carries
    if e.get("relations"):
        out["relations"] = e["relations"]

    try:
        cur = state.load_state(book, "current")
    except (ValueError, FileNotFoundError):
        cur = {}
    out["on_stage_now"] = any(nm in (cur.get("present_characters") or []) for nm in names)

    footprint = []
    for tok, _, text in final_chapters(book):
        if sum(count_aliases(text, names).values()):
            footprint.append(tok)
    if footprint:
        out["appearances"] = {"first": footprint[0], "last": footprint[-1],
                              "recent": footprint[-10:]}
    seen_chapters = {common.chapter_token_to_num(tok) or 0 for tok in footprint}

    try:
        lines = state.load_state(book, "lines")
    except (ValueError, FileNotFoundError):
        lines = {}
    try:
        tl = state.load_state(book, "timeline")
    except (ValueError, FileNotFoundError):
        tl = {}
    knows = {"public_knowledge": [], "lived_events": [], "same_chapter_events": []}
    for k in lines.get("knowledge", []):
        if str(k.get("status", "")).strip().lower() == "revealed":
            knows["public_knowledge"].append({"id": k.get("id"), "secret": str(k.get("secret", ""))[:50]})
    knows["public_knowledge"] = knows["public_knowledge"][-8:]
    # QA P1-3：原实现把「该角色登场章节的全部编年史」一律算作他「应知」，于是主角独自
    # 在家的私密场景也会被标给同章出场过的配角——正好把知情差喂反。现按事件文本是否
    # 点到该角色（名字/别名）分两档：lived_events = 事件里有他，可当亲历；
    # same_chapter_events = 仅同章发生，明确不保证亲历。
    for ev in tl.get("events") or []:
        ch_num = common.chapter_token_to_num(ev.get("chapter")) or 0
        if not (ch_num and ch_num in seen_chapters):
            continue
        ev_text = str(ev.get("event", ""))
        rec = {"chapter": ev.get("chapter"), "event": ev_text[:50]}
        if any(nm and nm in ev_text for nm in names if len(str(nm)) >= 2):
            knows["lived_events"].append(rec)
        else:
            knows["same_chapter_events"].append(rec)
    knows["lived_events"] = knows["lived_events"][-8:]
    knows["same_chapter_events"] = knows["same_chapter_events"][-8:]
    out["knows"] = knows
    # QA P17：holders 知情圈——秘密线的知情方角色不再被误标「不应知情」
    def _in_holders(k: dict) -> bool:
        holders = [str(h).strip() for h in (k.get("holders") or []) if str(h).strip()]
        if not holders:
            return False
        return any(nm and (nm in holders or any(nm in h or h in nm for h in holders))
                   for nm in names if len(str(nm)) >= 2)

    out["unknown_to_char"] = {
        "items": [{"id": k.get("id"), "secret": str(k.get("secret", ""))[:50],
                   "note": str(k.get("note", "") or "")[:40],
                   **({"holders": [str(h) for h in k.get("holders")]} if k.get("holders") else {})}
                  for k in lines.get("knowledge", [])
                  if str(k.get("status", "")).strip().lower() != "revealed"
                  and not _in_holders(k)][-8:],
        "note": "按账本未揭示 = 该角色不应知情（holders 知情圈内的角色已剔除）；若正文已另行交代，以正文为准。"}

    open_lines = []
    for arr, kind in (("foreshadows", "foreshadow"), ("misunderstandings", "misunderstanding"),
                      ("knowledge", "knowledge")):
        for g in lines.get(arr, []):
            if str(g.get("status", "")).strip().lower() in ("resolved", "revealed"):
                continue
            blob = " ".join(str(g.get(k, "")) for k in
                            ("name", "content", "plan", "parties", "secret", "note"))
            if any(nm in blob for nm in names if len(nm) >= 2):
                open_lines.append({"id": g.get("id"), "kind": kind, "status": g.get("status"),
                                   "target_ch": g.get("target_ch"),
                                   "desc": str(g.get("name") or g.get("content") or g.get("secret") or "")[:40]})
    if open_lines:
        out["open_lines"] = open_lines[:10]
    out["notes"] = [
        "本命令由现有账本推导（advisory）；语义与写法裁决归主控/起草员。",
        "knows.lived_events = 事件文本点到该角色，可当亲历；"
        "knows.same_chapter_events = 仅同章发生，不保证亲历（写对手戏严禁当作他知道）。",
    ]
    return out


def names(book: Path) -> dict:
    """names：跨章专名漂移扫描（只读，零裁决）。

    输出三类事实：
    - unregistered：跨章高频但未注册的专名候选（jieba NER，缺库退化为 n-gram）；
    - variant_clusters：候选间的近似簇（包含关系或编辑相似 ≥0.8）——同物异名风险；
    - known_variants：疑似既有实体的变体写法（该挂别名还是建实体，归主控）。
    """
    finals = final_chapters(book)
    out: dict = {"kind": "names", "final_chapters": len(finals),
                 "unregistered": [], "variant_clusters": [], "known_variants": []}
    if not finals:
        return out
    proj = common.load_json(book / "project.json", default={}) or {}
    lookup = entity_lookup(book)
    known: set[str] = {str(proj.get("protagonist", "")).strip()}
    for names_list in lookup.values():
        known.update(nm for nm in names_list if nm)
    try:
        pools = state.load_state(book, "ledger").get("pools", {})
    except (ValueError, FileNotFoundError):
        pools = {}
    for p in pools.values():
        for t in (p.get("name"), p.get("unit")):
            if t:
                known.add(str(t))
    known.discard("")

    per: dict[str, dict[str, int]] = {}
    if _HAS_JIEBA:
        for tok, _, text in finals:
            for w, flag in pseg.cut(text):
                if flag in ("nr", "ns", "nt", "nz") and 2 <= len(w) <= 6:
                    per.setdefault(w, {}).setdefault(tok, 0)
                    per[w][tok] += 1
    else:
        for tok, _, text in finals:
            for seg in re.split(r"[^\u4e00-\u9fff]+", text):
                if len(seg) < 3:
                    continue
                # QA P3/P18：n-gram 退化路径同样最小长度 3（2 字碎片不再入候选）
                for L in (3, 4):
                    for i in range(len(seg) - L + 1):
                        g = seg[i:i + L]
                        per.setdefault(g, {}).setdefault(tok, 0)
                        per[g][tok] += 1

    raw_cands = []
    for w, chs in per.items():
        total = sum(chs.values())
        if total < NAME_SCAN_MIN_COUNT or w in known or is_candidate_noise(w, pools):
            continue
        raw_cands.append((w, total, sorted(chs)))

    known_variants, unregistered = [], []
    # QA P2-3：称谓类变体（周叔 ↔ 老周头、陈嫂 ↔ 陈家的）既不互相包含、首字也不同，
    # 旧 host 判定三条全部落空 → 掉进 unregistered，于是「周叔 = 老周头别名」这条唯一
    # 可执行的建议两边都不给。补一条：共享一个非通用汉字 + 候选是 2~3 字称谓词。
    _APPELLATION_TAIL = "叔伯婆嫂爷娘哥姐师公姑婶舅姨"
    _GENERIC_CHARS = set("的了一是个人在中有大这上不为和与到说就把被从向他她它")

    def _appellation_host(w: str) -> list[str]:
        if not (2 <= len(w) <= 3) or w[-1] not in _APPELLATION_TAIL:
            return []
        core = {c for c in w if c not in _GENERIC_CHARS and c not in _APPELLATION_TAIL}
        if not core:
            return []
        return sorted({k for k in known if len(k) >= 2 and k != w
                       and any(c in k for c in core)})

    for w, total, chs in raw_cands:
        hosts = sorted({k for k in known if len(k) >= 2 and
                        (k in w or w in k or
                         (k[0] == w[0] and difflib.SequenceMatcher(None, w, k).ratio() >= 0.5))})
        hosts = sorted(set(hosts) | set(_appellation_host(w)))
        if hosts:
            known_variants.append({"name": w, "count": total, "chapters": chs[-5:], "of": hosts[:3]})
        else:
            unregistered.append((w, total, chs))

    clusters = []
    for w, total, chs in sorted(unregistered, key=lambda x: -x[1]):
        placed = False
        for cl in clusters:
            head = cl["head"]
            if head in w or w in head or difflib.SequenceMatcher(None, w, head).ratio() >= 0.8:
                cl["members"].append({"name": w, "count": total, "chapters": chs[-5:]})
                placed = True
                break
        if not placed:
            clusters.append({"head": w, "members": [{"name": w, "count": total, "chapters": chs[-5:]}]})

    out["unregistered"] = [{"name": w, "count": t, "chapters": chs[-5:]}
                           for w, t, chs in unregistered[:15]]
    out["variant_clusters"] = [cl for cl in clusters if len(cl["members"]) >= 2][:8]
    out["known_variants"] = known_variants[:10]
    out["notes"] = ["只出数、零裁决：是否注册/挂别名/改名归主控；近似写法也可能是正文修辞。"]
    return out
