"""读者记忆派生层：从已定稿正文推算「读者还记得什么」。

定位（与 cognition 的区别）：
- cognition 建模的是**角色**知道什么（角色之间的信息差）；
- 本模块建模的是**读者**可能记得什么（正文是读者唯一信息来源）。
两者是不同的账，不可互相替代。

判定性质：只能判「正文提到过」，不能判「读者理解了」，因此所有输出都是
**下界**——报「久未重现」可靠，不报不代表读者真记得。故消费方（checks）
一律按 advisory 使用，禁止据此阻断。

性能口径（如实记录，勿误读）：本模块对 finals 的扫描是**每个公开函数入口
各一遍**（line_memory_map 一遍、key_fact_memory 一遍），函数内部禁止再读盘；
R3 起正文来源优先走 SQLite 增量缓存（db.finals_from_index，指纹新鲜才用，
失配/无库回退文件全扫）——匹配语义恒为子串匹配，FTS 只当缓存不当召回器，
故阈值无需重校准（jieba 分词 MATCH 查全不能保证子串超集，不可当召回用，
此即此前「切换前须重校准」警告的落地方案：不切换语义、只换数据源）。

已知盲区（诚实清单，详见 PLAN_CONSISTENCY_50W §8）：
- locked.fact 若不含任何已登记实体名/别名，提词为空 → 该条**静默脱离监控**
 （是漏报不是误报：本模块所有闸门只报「曾出现后久未重现」）；
- line_terms_for 经 match_norm 虚词归一（P2：“无主的空灯”可命中“无主空灯”），但结构性改写（换主语/隐喻指代）仍漏检——接受漏报。
"""
from __future__ import annotations

from pathlib import Path

from . import common, db, evidence, state

# 阈值默认值：按「读者记忆相对卷结构」定的经验值（日更读者 + 单卷 40~60 章），
# 非实测。均可由 project.json 的 reader_memory 键覆盖（走 PARAM_SPEC，不硬编码）。
DEFAULTS = {
    "working_window": 25,        # 工作记忆：读者清楚记得（约半个卷）
    "fuzzy_window": 70,          # 模糊记忆边界：超过即入印象区（约一个卷多）
    "cold_line_base": 25,        # 冷线阈值基数（weight=1 时）
    "cold_line_per_weight": 8,   # 每级 weight 放宽的章数
}

TIERS = ("working", "fuzzy", "impression", "never")


def tiers_for(book: Path) -> dict:
    """读取 project.json 的 reader_memory 覆盖值，缺失/非法则逐键回落默认。"""
    proj = common.load_json(book / "project.json", default={}) or {}
    cfg = proj.get("reader_memory") or {}
    out = dict(DEFAULTS)
    if isinstance(cfg, dict):
        for k in DEFAULTS:
            v = cfg.get(k)
            if isinstance(v, int) and not isinstance(v, bool) and v >= 1:
                out[k] = v
    return out


def cold_threshold(tiers: dict, weight) -> int:
    """按线的权重放宽冷线阈值：权重越高，种植时越醒目，读者记得越久。

    与 evidence.line_sort_key 的既有约定一致（weight/level 即优先级），
    不引入新概念。非法权重（None/bool/字符串/小于 1）一律按 1 处理。
    """
    w = int(weight) if isinstance(weight, int) and not isinstance(weight, bool) and weight >= 1 else 1
    return tiers["cold_line_base"] + (w - 1) * tiers["cold_line_per_weight"]


def tier_of(gap: int | None, tiers: dict) -> str:
    """章距 → 读者记忆档位：working / fuzzy / impression / never。"""
    if gap is None:
        return "never"
    if gap <= tiers["working_window"]:
        return "working"
    if gap <= tiers["fuzzy_window"]:
        return "fuzzy"
    return "impression"


def _scan_last_seen(finals, terms: list[str]) -> tuple[int | None, int]:
    """在已读取的 finals 里扫提词，返回 (最后一次出现的章号, 出现过的章数)。

    - terms 为空 → (None, 0)（无信号，判 never，不参与冷线判定）；
    - 章号显式取 max 而非「迭代末项」：final_chapters 当前按 (卷, 章号) 升序
      返回，末项碰巧是最大章号，但那是实现细节不是契约——分卷重编号会让
      依赖迭代顺序的写法静默算错（修正 2）；
    - finals 必须已在调用方读取一次并复用，禁止在本函数内读盘。
    """
    if not terms:
        return None, 0
    last, hits = None, 0
    for _tok, num, text in finals:
        # 文本侧归一（与 line_terms_for 配对；每 final 每线一次 re.sub，约增 10~20% 扫描成本）
        if any(t in evidence.match_norm(text) for t in terms):
            last = num if last is None else max(last, num)
            hits += 1
    return last, hits


def _finals(book: Path) -> list:
    """R3 增量缓存读：索引新鲜时读 DB text 列，否则回退文件全扫。

    匹配语义恒为调用方的子串匹配（FTS 只当缓存不当召回器），
    指纹失配/无库一律回退——输出与 legacy 路径 bit 级一致。
    """
    try:
        cached = db.finals_from_index(book)
    except Exception:
        cached = None
    if cached is not None:
        return cached
    return list(evidence.final_chapters(book))


def line_memory_map(book: Path, tiers: dict | None = None) -> list[dict]:
    """全部未闭环线的读者记忆画像（每公开入口只读一遍 finals）。

    返回按「有具体章距者 gap 降序（越冷越前）、never 档殿后」排序，每条：
      {id, kind, label, target_ch, status, plant_ch, weight,
       last_seen_ch, seen_chapters, gap, tier, cold_threshold, is_cold}

    消费方注意：gap=None（never）排序在最后但**最需要处置**（从未落笔），
    用 never_surfaced() 单独取，勿只看第一条。
    """
    tiers = tiers or tiers_for(book)
    finals = _finals(book)                                # 只读一次（R3：DB 缓存优先）
    if not finals:
        return []
    cur_ch = max(n for _, n, _ in finals)

    reg_terms = [a for names in evidence.entity_lookup(book).values() for a in names]
    lines = state.load_state(book, "lines")
    out: list[dict] = []
    for kind, arr in (("foreshadow", "foreshadows"),
                      ("misunderstanding", "misunderstandings"),
                      ("knowledge", "knowledge")):
        spec = state.line_kind_spec(kind)
        for g in lines.get(arr, []) or []:
            if str(g.get("status", "")).strip().lower() == str(spec["resolved"]).lower():
                continue                                   # 已闭环的不需要读者记得
            terms = evidence.line_terms_for(g, kind, reg_terms)
            last, seen = _scan_last_seen(finals, terms)
            gap = (cur_ch - last) if last is not None else None
            weight = g.get("level" if kind == "misunderstanding" else "weight")
            thr = cold_threshold(tiers, weight)
            out.append({
                "id": str(g.get("id", "")), "kind": kind,
                "label": str(g.get("name") or g.get("parties") or g.get("secret") or ""),
                "target_ch": g.get("target_ch"), "status": str(g.get("status", "")),
                "plant_ch": g.get("plant_ch"), "weight": weight,
                "last_seen_ch": last, "seen_chapters": seen, "gap": gap,
                "tier": tier_of(gap, tiers),
                "cold_threshold": thr,
                "is_cold": gap is not None and gap > thr,
            })
    out.sort(key=lambda r: (r["gap"] is None, -(r["gap"] or 0)))
    return out


def key_fact_memory(book: Path, tiers: dict | None = None) -> list[dict]:
    """「已声明重要」事实集合（locked + 已揭示 knowledge）的记忆画像。

    范围严格限定这两个集合（书自己声明为重要的），不对全部认知条目生效——
    否则一次性事实会刷屏。locked 的提词退化为「fact 整句（≥4 字）+ fact 中
    出现的已登记专名」：fact 整句几乎不会逐字复现，靠专名承载检索；若 fact
    不含任何专名则提词只剩整句 → 大概率 never，即模块 docstring 所述盲区。
    """
    tiers = tiers or tiers_for(book)
    finals = _finals(book)                                # R3：DB 缓存优先
    if not finals:
        return []
    cur_ch = max(n for _, n, _ in finals)
    reg_terms = [a for names in evidence.entity_lookup(book).values() for a in names]
    out: list[dict] = []
    try:
        _ents = state.load_state(book, "entities").get("entries", []) or []
    except (ValueError, OSError):
        _ents = []
    _names_by_id: dict[str, list[str]] = {}
    for _e in _ents:
        if isinstance(_e, dict) and _e.get("id"):
            _names_by_id[str(_e["id"])] = (
                [str(_e.get("name", ""))]
                + [str(a) for a in _e.get("aliases", []) or []])

    for le in state.load_state(book, "locked").get("entries", []) or []:
        fact = str(le.get("fact", ""))
        terms = [t for t in (fact.strip(),) if len(t) >= 4]
        terms += [a for a in reg_terms if len(a) >= 2 and a in fact]
        # P2：refs 显式挂载的实体（id 或法定名）直接并入提词，不依赖 fact 文本命中
        for _r in (le.get("refs") or []):
            _r = str(_r or "").strip()
            if not _r:
                continue
            if _r in _names_by_id:
                terms += [t for t in _names_by_id[_r] if len(t) >= 2]
            elif len(_r) >= 2:
                terms.append(_r)
        last, _seen = _scan_last_seen(finals, terms)
        since = common.chapter_token_to_num(le.get("since_ch", "")) or 0
        gap = (cur_ch - last) if last is not None else None
        out.append({"source": "locked", "id": str(le.get("id", "")),
                    "label": fact[:40], "since_ch": since,
                    "last_seen_ch": last, "gap": gap, "tier": tier_of(gap, tiers)})

    kno_spec = state.line_kind_spec("knowledge")
    for g in state.load_state(book, "lines").get("knowledge", []) or []:
        if str(g.get("status", "")).strip().lower() != str(kno_spec["resolved"]).lower():
            continue                                       # 只看已揭示的秘密
        terms = evidence.line_terms_for(g, "knowledge", reg_terms)
        last, _seen = _scan_last_seen(finals, terms)
        gap = (cur_ch - last) if last is not None else None
        out.append({"source": "knowledge", "id": str(g.get("id", "")),
                    "label": str(g.get("secret", ""))[:40], "since_ch": 0,
                    "last_seen_ch": last, "gap": gap, "tier": tier_of(gap, tiers)})

    out.sort(key=lambda r: (r["gap"] is None, -(r["gap"] or 0)))
    return out


def never_surfaced(rows: list[dict]) -> list[dict]:
    """从 line_memory_map 的结果里筛出「已入账但正文从未落笔」的线。

    注意：入参是已算好的 rows，不自己调 line_memory_map——checks 里
    闸门 1/2 都要用同一份画像，各自重算会把全书正文扫两遍。
    """
    return [r for r in rows if r["tier"] == "never"]
