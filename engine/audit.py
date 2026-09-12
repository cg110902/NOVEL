"""engine/audit.py: 确定性矛盾排查探针（8大机械探针：在场/充能/金额/KNO/不可逆/认知差/别名漂移/称谓与修饰词对账）。

设计原则：
1. 0 Token 消耗、极速（<0.2s）、确定性机械计算；
2. 零主观裁决：输出 CandidateContradiction（候选矛盾点），由 Auditor 子代理进一步仲裁；
3. 输出 candidate_hard（硬矛盾候选）与 candidate_soft（软存疑候选）两个分级；
4. 证据确凿：每条候选必须携带正文行号/原句及对应账本条目 (state_ref)。
"""
from __future__ import annotations

import difflib
import json
import re
from pathlib import Path
from typing import Any

from . import common, state
from .models.entities import EntityStatus, EntityType

try:
    import jieba
    import jieba.posseg as pseg
    try:
        jieba.setLogLevel(60)
    except Exception:
        pass
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False


from engine import vocab

_STOP_WORDS = vocab.STOP_WORDS
# 死者"以活人身份发言/行动"的判定用词。用于替代原先过宽的「本行含任意左引号」判据。
_SPEECH_VERBS = vocab.SPEECH_VERBS



def _deceased_speaks(content: str, name: str) -> bool:
    """判定已故角色是否在正文行中「以活人身份发言」。

    修复说明：原判据末段是 `f"「" in content or f"“" in content`——f-string 无占位符，
    等价于「本行含任意左引号」，而中文小说几乎每行对白都带引号，于是任何提及死者
    的行都会被判成 candidate_hard（硬矛盾），淹没真正的问题。

    改为两条更贴近语义的判据：
      1. 死者名紧跟发言动词（道/说/…）——活人发言；
      2. 死者名紧贴引号边界（「陆沉舟 / 陆沉舟」）——对白归属或直呼。
    行内其余位置出现死者名不再单独构成硬矛盾候选。
    """
    if not name:
        return False
    if any(f"{name}{v}" in content for v in _SPEECH_VERBS):
        return True
    # 引号边界判定收敛到 common.is_quote_adjacent：原先只认「」/“”，而流水线实际产出
    # 用的是 ASCII 双引号，导致本判据对全部实战稿件静默失明。
    return common.is_quote_adjacent(content, name)



def _parse_cn_number(s: str) -> int | None:
    """中文数字转整数（委托 common.cn_to_int，唯一实现）。

    旧实现把「亿」当普通数字位处理：三亿 → cur 被 100000000 覆盖成 100000000、
    两亿同样得 100000000；且遇到不认识的字是 `continue` 静默跳过（如「二十个」
    会被算成 20）。现统一走 common.cn_to_int：万/亿按节进位，未知字符返回 None。
    """
    return common.cn_to_int(s)


def _find_mentions_with_lines(lines: list[str], keyword: str) -> list[tuple[int, str]]:
    """在文本行中查找关键字，返回 (1-based行号, 裁剪行内容)。"""
    hits = []
    if not keyword or len(keyword) < 2:
        return hits
    for idx, line in enumerate(lines, start=1):
        if keyword in line:
            clean = line.strip()
            if len(clean) > 80:
                clean = clean[:77] + "…"
            hits.append((idx, clean))
    return hits


# ---------------------------------------------------------------------------
# 7 大确定性探针
# ---------------------------------------------------------------------------

def probe_locked_facts(text: str, lines: list[str], n: int, locked_st: dict, ents_st: list[dict]) -> list[dict]:
    """探针 1：不可逆事实违背（LOCK 事实刚性防吃书）。"""
    candidates = []
    entries = locked_st.get("entries", []) if isinstance(locked_st, dict) else []
    for lock in entries:
        if not isinstance(lock, dict):
            continue
        lid = lock.get("id", "LOCK")
        kind = lock.get("kind", "fact")
        fact = lock.get("fact", "")
        since = lock.get("since_ch", "ch_000")
        since_num = common.chapter_token_to_num(since) or 0
        if n <= since_num:
            continue

        if kind == "death":
            deceased_name = ""
            # 修复：原条件 `name in fact or life_status == "deceased"` 会在遍历到第一个
            # 已故实体时就 break，与 fact 讲的是谁完全无关——「张三已死」的事实会被
            # 安到李四头上（张冠李戴）。改为先按事实文本精确匹配，匹配不上才用
            # 「唯一/首个已故实体」兜底。
            for ent in ents_st:
                name = ent.get("name", "")
                if name and name in fact:
                    deceased_name = name
                    break
            if not deceased_name:
                for ent in ents_st:
                    if ent.get("life_status") == "deceased":
                        deceased_name = ent.get("name", "")
                        break
            if not deceased_name:
                m = re.search(r"([^已确认于在被]{2,4})(?:已|确认|在|身亡|死亡|殒落)", fact)
                if m:
                    deceased_name = m.group(1).strip()

            if deceased_name:
                hits = _find_mentions_with_lines(lines, deceased_name)
                for line_no, content in hits:
                    if any(p in content for p in vocab.DEATH_EXEMPT_PATTERNS):
                        continue
                    if _deceased_speaks(content, deceased_name):
                        candidates.append({
                            "probe": "locked_facts",
                            "severity": "candidate_hard",
                            "line_no": line_no,
                            "also_flagged_by": "retired_entity_on_stage",
                            "title": f"不可逆事实违背：已故角色「{deceased_name}」疑似活人出场/发言",
                            "description": f"已于 {since} 登记死亡的不可逆事实 [{lid}]（{fact}），但在本章出现对白或行动。",
                            "evidence": f"L{line_no}: {content}",
                            "state_ref": lid,
                            "suggestion": "请核对正文是否为回忆/幻觉；若为活人登场，属严重硬性吃书，需定向修复或替换登场人物。"
                        })
                        break

        elif kind in ("destruction", "disbandment"):
            target_name = ""
            for ent in ents_st:
                name = ent.get("name", "")
                if name and name in fact:
                    target_name = name
                    break
            if target_name:
                hits = _find_mentions_with_lines(lines, target_name)
                for line_no, content in hits:
                    if any(p in content for p in vocab.FACILITY_ACTIVE_PATTERNS):
                        candidates.append({
                            "probe": "locked_facts",
                            "severity": "candidate_hard",
                            "line_no": line_no,
                            "also_flagged_by": None,
                            "title": f"不可逆事实违背：已摧毁/解散的「{target_name}」疑似如常运转",
                            "description": f"已于 {since} 登记摧毁/解散的不可逆事实 [{lid}]（{fact}），但正文出现正常运作描写。",
                            "evidence": f"L{line_no}: {content}",
                            "state_ref": lid,
                            "suggestion": "核对该设施是否应为废墟/旧址，避免出现人员正常出入或消费情节。"
                        })
                        break
    return candidates


def _not_yet_effective_deceased(locked_st: dict, ents_st: list[dict], n: int) -> set[str]:
    """本章**或更晚**才登记死亡的已故实体名（时点豁免）。

    最典型的就是「本章当场战死」的角色：他在本章绝大部分篇幅里活得好好的，
    正文里当然会被反复提及；而 sync 之后实体表已把他标成 deceased，
    本探针只读实体表、拿不到时点，于是必然误报「已亡角色活跃出场」。
    （ch_002 实战：崔烈在窄道里被李玄一拳打死，全章都在场，却被判成已亡者出场。）

    probe_locked_facts 早已用 `if n <= since_num: continue` 做了同一时点豁免——
    本章或更晚才登记的事实，在本章时点尚未生效。本函数把该豁免补给探针 2，
    判据仍是既有的 locked.since_ch，不引入新字段。
    """
    entries = locked_st.get("entries", []) if isinstance(locked_st, dict) else []
    pending = [str(lk.get("fact", "")) for lk in entries
               if isinstance(lk, dict)
               and n <= (common.chapter_token_to_num(lk.get("since_ch", "ch_000")) or 0)]
    if not pending:
        return set()
    out = set()
    for ent in ents_st:
        name = ent.get("name", "")
        if name and ent.get("life_status") == "deceased" and any(name in f for f in pending):
            out.add(name)
    return out


def probe_location_presence(text: str, lines: list[str], cur_st: dict, ents_st: list[dict],
                            exempt_names: set[str] | None = None) -> list[dict]:
    """探针 2：空间与在场探针（检查角色地理空间跳跃与存活状态）。

    exempt_names：本章或更晚才登记死亡的实体——其死亡在本章时点尚未生效。
    """
    candidates = []
    exempt = exempt_names or set()
    for ent in ents_st:
        name = ent.get("name", "")
        if not name:
            continue
        if ent.get("life_status") == "deceased":
            if name in exempt:
                continue  # 本章才死（或更晚才死）：本章提及属正常，不是「活跃出场」
            hits = _find_mentions_with_lines(lines, name)
            for line_no, content in hits:
                # 死亡当章及后世章里，凡同句带死亡叙事词（尸体/遇害/出殡/遗言/坟/棺等）的提及，
                # 多为死亡报道、回忆或吊唁，不应判为「活人出场」；真正“复活登场”通常无此类词。
                # 列表须与 probe_locked_facts 的 exempt_pats 精神一致，但比其更宽：
                # locked_facts 只对发言/引号句判硬矛盾，本探针按纯提及判，必须把死亡叙事排除干净。
                if any(p in content for p in vocab.DEATH_CONTEXT_PATTERNS):
                    continue
                candidates.append({
                    "probe": "location_presence",
                    "severity": "candidate_hard",
                    "line_no": line_no,
                    "also_flagged_by": "retired_entity_on_stage",
                    "title": f"已亡角色活跃出场：实体「{name}」已故但出现于正文",
                    "description": f"实体台账记录「{name}」生命状态为 deceased，但在本章活跃出场。",
                    "evidence": f"L{line_no}: {content}",
                    "state_ref": f"entities.{name}",
                    "suggestion": "核实人物是否已死亡；若是回忆请注明，否则请替换为存活角色。"
                })
                break

        ent_loc = str(ent.get("location", "") or "").strip()
        status = str(ent.get("status", "") or "").strip()
        if status in ("imprisoned", "sealed", "isolated") or any(k in ent_loc for k in vocab.ISOLATED_LOC_KEYWORDS):
            hits = _find_mentions_with_lines(lines, name)
            if hits:
                for line_no, content in hits:
                    if not any(k in content for k in vocab.ISOLATED_EXEMPT_KEYWORDS):
                        candidates.append({
                            "probe": "location_presence",
                            "severity": "candidate_soft",
                            "line_no": line_no,
                            "also_flagged_by": None,
                            "title": f"封闭空间角色出场存疑：实体「{name}」处于「{ent_loc or status}」",
                            "description": f"实体记录处于受困/偏远地点，但在本章场景出场且无越狱/传讯前置动作。",
                            "evidence": f"L{line_no}: {content}",
                            "state_ref": f"entities.{name}",
                            "suggestion": "补充角色脱困说明、千里传音或化身交代，防止空间瞬移穿帮。"
                        })
                        break
    return candidates


def probe_charges_possession(text: str, lines: list[str], ents_st: list[dict], cur_st: dict) -> list[dict]:
    """探针 3：道具与充能探针（检查零充能或已消耗道具的违规使用）。"""
    candidates = []
    use_verbs = vocab.ITEM_USE_VERBS
    for ent in ents_st:
        etype = ent.get("type", "")
        # 只认模型里真实存在的 EntityType.ITEM。此前还列了 artifact/weapon/consumable/prop
        # 四个值，但 EntityType 枚举根本没有它们（合法值仅 person/item/place/location/
        # faction/other），提案层会被 schema 拒收 → 这四个分支是永不执行的死代码，
        # 看着「支持多种道具类型」，实际一个都不支持。
        if etype != EntityType.ITEM.value:
            continue
        name = ent.get("name", "")
        charges = ent.get("charges")
        status = ent.get("status", "")
        aliases = ent.get("aliases", []) or []
        names_to_check = [name] + [a for a in aliases if a]

        # status 的合法值只有 active/retired（EntityStatus 枚举）；此前判的
        # exhausted/consumed/destroyed/lost 四个值一个都存不进来（schema 直接拒收），
        # 于是「已耗尽」实际上只可能由 charges==0 触发。现改为：
        #   ① charges == 0（充能耗尽，最硬的信号）；
        #   ② status == retired（实体已退场，合法值）；
        #   ③ condition 文本明示损毁/耗尽（模型里「道具完损状态」就是这一字段）。
        cond = str(ent.get("condition", "") or "")
        is_exhausted = (charges == 0 or status == EntityStatus.RETIRED.value
                        or any(w in cond for w in vocab.ITEM_EXHAUSTED_WORDS))
        if not is_exhausted:
            continue

        for check_name in names_to_check:
            hits = _find_mentions_with_lines(lines, check_name)
            for line_no, content in hits:
                if any(v in content for v in use_verbs):
                    candidates.append({
                        "probe": "charges_possession",
                        "severity": "candidate_hard",
                        "line_no": line_no,
                        "also_flagged_by": "item_charges_exhausted",
                        "title": f"已耗尽道具违规使用：道具「{name}」（charges={charges}/status={status}）",
                        "description": f"账本记录道具「{name}」已耗尽或销毁，但正文出现使用动作。",
                        "evidence": f"L{line_no}: {content}",
                        "state_ref": f"entities.{name}",
                        "suggestion": "核验道具是否在前期已消耗完毕；若是新获取同名道具或残存灵力，需在正文明确交代。"
                    })
                    break
    return candidates


def probe_amount_ledger(text: str, lines: list[str], led_st: dict) -> list[dict]:
    """探针 4：账本金额一致性（检查正文交易支出与账本余额矛盾）。"""
    candidates = []
    pools = led_st.get("pools", {}) if isinstance(led_st, dict) else {}
    _verbs_pat = "|".join(vocab.MONEY_VERBS)
    # 单位交替必须「长者优先」：CURRENCY_UNITS 里 "两" 排在 "两银子/两白银/两黄金" 之前，
    # 正则交替取先匹配者，于是「九十两银子」只捕获到 "两"、「九十块灵石」只捕获到 "块"，
    # 后面按单位名找池的分支全部落空——探针形同不存在。按长度降序即可。
    _units_pat = "|".join(sorted(vocab.CURRENCY_UNITS, key=len, reverse=True))
    # 亿 原先不在数字字符集里，「花费三亿灵石」整句匹配不上 → 探针静默。补上。
    money_pat = re.compile(rf"(?:{_verbs_pat})\s*([0-9一二两三四五六七八九十百千万亿]+)\s*({_units_pat})")
    # 池键解析改为对齐本书真实账本：单位词命中某池的 name/unit 即认定该池。
    # 此前只认 silver/spirit_stone/copper/gold 四个硬编码英文键，而引擎内置池叫
    # standard_currency、书里的池键名由作者自定（中文/拼音都可能），于是绝大多数书
    # 的这个探针一次都不会触发。
    def _resolve_pool(unit: str) -> str | None:
        best_key, best_len = None, 0
        for key, meta in pools.items():
            if not isinstance(meta, dict):
                continue
            for token in (str(meta.get("name", "")).strip(), str(meta.get("unit", "")).strip(), str(key)):
                # 只认「池的 name/unit/key 出现在捕获单位里」这一个方向：
                # 池声明的 unit="两" 落在正文捕获的 "两银子" 里是合法命中；
                # 反过来（unit in token）才是危险的——正文捕获 "文" 会误挂到名叫
                # 「文献阁」的池上，故该方向已删。取命中 token 最长者，避免
                # "灵石" 与 "极品灵石" 同时命中时挂错池。
                if token and token in unit and len(token) > best_len:
                    best_key, best_len = key, len(token)
        return best_key
    for line_no, line in enumerate(lines, start=1):
        for m in money_pat.finditer(line):
            raw_num, unit = m.group(1), m.group(2)
            val = _parse_cn_number(raw_num)
            if val is None or val <= 0:
                continue
            pool_key = _resolve_pool(unit)

            if pool_key and pool_key in pools:
                # 账本口径：池余额键是 current（每次合并由流水全量重算）；balance 是旧版
                # 流水条目字段，池对象上不存在——读它恒得 0，会把「余额内正常支出」全误报。
                _pool = pools[pool_key] if isinstance(pools[pool_key], dict) else {}
                _bal_raw = _pool.get("current")
                if _bal_raw is None:
                    _bal_raw = _pool.get("initial", 0)
                try:
                    bal = int(_bal_raw)
                except (TypeError, ValueError):
                    bal = None
                if bal is None:
                    continue
                if any(k in line for k in vocab.SPENDING_VERBS) and val > bal:
                    candidates.append({
                        "probe": "amount_ledger",
                        "severity": "candidate_soft",
                        "line_no": line_no,
                        "also_flagged_by": "amount_unsupported",
                        "title": f"金额收支存疑：正文支出 {val} {unit} 大于账本余额 ({bal})",
                        "description": f"正文出现单次大额支出，但对应资源池 {pool_key} 当前余额仅为 {bal}。",
                        "evidence": f"L{line_no}: {line.strip()[:80]}",
                        "state_ref": f"ledger.pools.{pool_key}",
                        "suggestion": "核对是否有先期入账未登入提案，或修改正文数值使之与财务账本自洽。"
                    })
    return candidates


_SPEAKER_MODS = vocab.SPEAKER_MODS_PATTERN


# 引号对白区间（用于把旁白从行里剥出来）
_QUOTE_SPAN_RE = re.compile(r"[“「『\"]([^”」』\"\n]{0,200})[”」』\"]")
_INNER_THOUGHT = vocab.INNER_THOUGHT_MARKERS
_NEGATION = vocab.SECRET_NEGATION_MARKERS


def _entity_roster(ents_st: list[dict] | None) -> dict[str, str]:
    """{实体 id / 法定名 / 别名 → 法定名}：把各种写法归一到法定名。"""
    roster: dict[str, str] = {}
    for e in ents_st or []:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "")).strip()
        if not name:
            continue
        keys = [str(e.get("id", "")).strip(), name]
        keys += [str(a).strip() for a in (e.get("aliases") or [])]
        for k in keys:
            if k and k not in roster:
                roster[k] = name
    return roster


def _resolve_pov_character(book: Path, cur_st: dict | None,
                           ents_st: list[dict] | None, n: int) -> str | None:
    """解析本章视角角色的法定名；指名不到就返回 None。

    **只在能指名到具体角色时才返回值**——这是本探针不误报的关键：
      · 「群像切片 / 双线交替 / 主角视角」这类是视角**模式**，不是角色名。
        群像与全知视角下，旁白陈述任何人都不知情的秘密是合法的，必须放过；
      · 指名不到时，旁白里的「他」无从归因，宁可不报。

    取值顺序：① `current.pov_ref`（结构化引用，且被 verify_state 校验过）；
    ② beats front-matter 的 `pov`（形如「林牧·视角」，剥掉后缀后须命中实体名册）。
    """
    roster = _entity_roster(ents_st)
    if not roster:
        return None
    ref = str((cur_st or {}).get("pov_ref") or "").strip()
    if ref:
        hit = roster.get(ref)
        if hit:
            return hit
    try:
        beats = common.find_chapter_files(book, "beats", n)
    except (OSError, ValueError):
        beats = []
    for bf in (beats[-1:]) if beats else ():
        try:
            fm = common.parse_front_matter(bf.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        cand = str(fm.get("pov") or "").strip()
        for suf in ("·视角", "·視角", "视角", "視角", "·POV", " POV", "POV",
                    "·之视角", "之视角"):
            if cand.endswith(suf):
                cand = cand[: -len(suf)]
                break
        cand = cand.strip(" ··-—:：")
        if cand and cand in roster:
            return cand
    return None


def probe_secret_leakage(text: str, lines: list[str], lines_st: dict,
                         ents_st: list[dict] | None = None,
                         pov_name: str | None = None) -> list[dict]:
    """探针 5：KNO 秘密知情差泄露。

    两条射程：
      ① 对白：不知情角色的台词直接谈及秘密（原有限度）；
      ② **旁白 / 心理描写**：本章视角角色不在知情圈内，旁白却把秘密当既定事实陈述
         ——视角人物不可能知道，属视角穿帮。此路只有 `pov_name` 指名到具体角色
         时才判定（群像/全知视角下旁白知情合法，指名不到一律放过，见
         `_resolve_pov_character`）。

    两路共用同一套关键词命中口径，且都只出 `candidate_soft` 交由 Auditor 仲裁。
    """
    candidates = []
    knowledge = lines_st.get("knowledge", []) if isinstance(lines_st, dict) else []
    # 说话人候选名册：注册实体名 + 别名（越长者优先匹配——先验：引号前紧邻的已知人名
    # 就是说话人，比正则盲抓「老赵拍着桌子道」整串准确）
    speaker_roster: list[str] = []
    for e in ents_st or []:
        if not isinstance(e, dict):
            continue
        for nm in [str(e.get("name", ""))] + [str(a) for a in (e.get("aliases") or [])]:
            nm = nm.strip()
            if len(nm) >= 2 and nm not in speaker_roster:
                speaker_roster.append(nm)
    speaker_roster.sort(key=len, reverse=True)
    # 别名归一：holders 写别名而说话人检出法定名（或反之）时不得误标泄密。
    # 两边都归一到法定名后比对（registry 失败则回退裸字符串比对，原行为）。
    def _canon(v) -> str:
        try:
            from .objects.registry import build_registry, resolve_ref as _rr
            ent = _rr(_kn_reg, v)
            if isinstance(ent, dict) and ent.get("name"):
                return str(ent["name"])
        except Exception:
            pass
        return str(v or "").strip()
    try:
        from .objects.registry import build_registry as _breg
        _kn_reg = _breg({"entries": [e for e in (ents_st or []) if isinstance(e, dict)]})
    except Exception:
        _kn_reg = {}
    for kno in knowledge:
        status = str(kno.get("status", "")).lower()
        if status in ("revealed", "公开"):
            continue
        kid = kno.get("id", "KNO")
        secret = str(kno.get("secret", "")).strip()
        holders = kno.get("holders") or kno.get("knower") or []
        knower = {_canon(k) for k in holders if str(k).strip()}
        if not secret or len(secret) < 4:
            continue

        keywords = []
        if _HAS_JIEBA:
            for w, flag in pseg.cut(secret):
                if flag in ("n", "nr", "ns", "nt", "nz", "v", "a") and len(w) >= 2 and w not in _STOP_WORDS:
                    keywords.append(w)
        else:
            keywords = [w for w in re.findall(r"[\u4e00-\u9fa5]{2,4}", secret) if w not in _STOP_WORDS]

        if not keywords:
            continue

        for line_no, line in enumerate(lines, start=1):
            flagged_this_line = False
            for m_q in re.finditer(r"[“「『\"]([^”」』\"\n]{4,80})[”」』\"]", line):
                q = m_q.group(1)
                hit_kws = [kw for kw in keywords if kw in q]
                if len(hit_kws) >= 2 or (len(hit_kws) == 1 and len(hit_kws[0]) >= 4 and hit_kws[0] in q):
                    speaker = None
                    # 1) 已知实体名册：取引号左侧最近处出现（含道/说前 6 字窗口内）的名字
                    head = line[:m_q.start()]
                    window = head
                    best = None
                    for nm in speaker_roster:
                        pos = window.rfind(nm)
                        if pos >= 0 and (best is None or pos > best[1]):
                            best = (nm, pos)
                    if best is not None and len(head) - (best[1] + len(best[0])) <= 12:
                        speaker = best[0]
                    # 2) 兜底：旧正则启发（去修饰词）
                    if speaker is None:
                        m_spk = re.search(rf"([^，。！？\s]{{2,6}}?)(?:{_SPEAKER_MODS})*(?:道|说|笑|叹|喝|问)[:：]", line)
                        if m_spk:
                            speaker = m_spk.group(1).strip()
                            speaker = re.sub(rf"(?:{_SPEAKER_MODS})+$", "", speaker).strip()
                    if speaker and knower and _canon(speaker) not in knower:
                        candidates.append({
                            "probe": "secret_leakage",
                            "severity": "candidate_soft",
                            "line_no": line_no,
                            "also_flagged_by": None,
                            "title": f"知情差穿帮存疑：[{kid}] 秘密内容疑似由不知情角色「{speaker}」道出",
                            "description": f"未公开知情线 [{kid}]（知情人: {','.join(knower) or '仅主角'}），角色「{speaker}」在台词中提及核心要素（{', '.join(hit_kws)}）。",
                            "evidence": f"L{line_no}: {line.strip()[:80]}",
                            "state_ref": kid,
                            "suggestion": "核查该台词是否属于泄密穿帮；若是试探套话应写明心机，若不知情则需调整用词。"
                        })
                        flagged_this_line = True
                        break
            if flagged_this_line:
                continue

            # ---- ② 旁白 / 心理描写：视角人物不该知道，旁白却当既定事实陈述 ----
            if not (pov_name and knower and pov_name not in knower):
                continue
            narration = _QUOTE_SPAN_RE.sub(" ", line)
            if len(narration.strip()) < 4:
                continue
            hit_kws = [kw for kw in keywords if kw in narration]
            if not (len(hit_kws) >= 2
                    or (len(hit_kws) == 1 and len(hit_kws[0]) >= 4)):
                continue
            # 「他不知道水井下藏着银子」是反证，不是泄密——没有这道闸就是笑话
            if any(neg in narration for neg in _NEGATION):
                continue
            channel = ("心理描写" if any(m in narration for m in _INNER_THOUGHT)
                       else "旁白")
            candidates.append({
                "probe": "secret_leakage",
                "severity": "candidate_soft",
                "line_no": line_no,
                "also_flagged_by": None,
                "title": (f"知情差穿帮存疑：[{kid}] 秘密疑似在{channel}中泄露"
                          f"（视角角色「{pov_name}」不在知情圈内）"),
                "description": (f"未公开知情线 [{kid}]（知情人: {','.join(knower) or '仅主角'}），"
                                f"本章视角角色「{pov_name}」不在知情圈内，但{channel}把秘密当既定事实"
                                f"陈述（命中：{', '.join(hit_kws)}）——该视角人物无从知晓。"),
                "evidence": f"L{line_no}: {line.strip()[:80]}",
                "state_ref": kid,
                "suggestion": (f"核查本章视角是否确为「{pov_name}」：若是，{channel}不得陈述其不知情的秘密，"
                               f"可改为猜测/存疑句式，或把这段交给知情者视角的章节。"
                               f"若本章本就是全知/群像视角，请把 beats 的 pov 写成模式名"
                               f"（如「群像切片」「双线交替」）而不是角色名，以免误报。"),
            })
    return candidates


def probe_cognition_stubs(text: str, lines: list[str], lines_st: dict, cog_st: dict | None = None) -> list[dict]:
    """探针 6：认知差与误解冲突（检查未澄清误解前两方的突兀协同，以及与已有认知表的直接冲突）。"""
    candidates = []
    misunderstandings = lines_st.get("misunderstandings", []) if isinstance(lines_st, dict) else []
    for mis in misunderstandings:
        if str(mis.get("status", "")).lower() in ("resolved", "closed"):
            continue
        mid = mis.get("id", "MIS")
        raw_parties = mis.get("parties")
        # 台账 parties 在 v2 schema 起为字符串（如「张彪与李玄」）；老书遗留可能为数组。
        # 一律归一成实体名列表再取前两个主体——绝不可把字符串当字符数组切片，
        # 否则「陆沉舟与官差」会误拆成「陆」「沉」两个单字主体。
        if isinstance(raw_parties, str):
            plist = [x.strip() for x in re.split(r"[与和及、，,·×/\s]+", raw_parties) if x.strip()]
        elif isinstance(raw_parties, list):
            plist = [str(x).strip() for x in raw_parties if str(x).strip()]
        else:
            plist = []
        if len(plist) < 2:
            continue
        p1, p2 = plist[0], plist[1]
        content = mis.get("content", "")
        if (len(p1) >= 2 and p1 in text) and (len(p2) >= 2 and p2 in text):
            coop_words = vocab.COOP_WORDS
            for line_no, line in enumerate(lines, start=1):
                if (p1 in line or p2 in line) and any(w in line for w in coop_words):
                    candidates.append({
                        "probe": "cognition_stubs",
                        "severity": "candidate_soft",
                        "line_no": line_no,
                        "also_flagged_by": None,
                        "title": f"误解未解前突兀协同：[{mid}]（{str(content)[:20]}）",
                        "description": f"角色「{p1}」与「{p2}」之间尚有未解误会 [{mid}]，但在正文表现出高度信任或亲密协同动作。",
                        "evidence": f"L{line_no}: {line.strip()[:80]}",
                        "state_ref": mid,
                        "suggestion": "核查二人是否有中间澄清戏；若无，应保持暗中提防与言语机锋，不可提前破冰。"
                    })
                    break

    # 检查 state/cognition.json 中的显式认知条目
    if cog_st and isinstance(cog_st, dict):
        for cog in cog_st.get("entries", []):
            cid = cog.get("id", "COG")
            char = cog.get("character", "")
            kind = cog.get("kind")
            content = cog.get("content", "")
            if kind == "misunderstanding" and char and char in text:
                contradict_words = vocab.CONTRADICT_WORDS
                for line_no, line in enumerate(lines, start=1):
                    if char in line and any(w in line for w in contradict_words):
                        candidates.append({
                            "probe": "cognition_stubs",
                            "severity": "candidate_soft",
                            "line_no": line_no,
                            "also_flagged_by": None,
                            "title": f"角色认知越界穿帮：[{cid}]「{char}」持有认知误解",
                            "description": f"角色「{char}」在认知台账中标记持有误解 [{cid}]（{content[:25]}），但在正文中直接出现全知/看穿描述。",
                            "evidence": f"L{line_no}: {line.strip()[:80]}",
                            "state_ref": cid,
                            "suggestion": "核查该角色是否应在本章澄清误解；若尚未澄清，严禁使用全知视角心理描写。"
                        })
                        break
    return candidates


def probe_alias_drift(text: str, lines: list[str], ents_st: list[dict]) -> list[dict]:
    """探针 7：实体分裂与别名漂移（检查高相似度近似名，防笔误立新名）。"""
    candidates = []
    known_names = {}
    known_all = set()
    for ent in ents_st:
        name = ent.get("name", "")
        if name:
            known_names[name] = ent
            known_all.add(name)
            for a in (ent.get("aliases") or []):
                if a:
                    known_all.add(str(a))

    if not _HAS_JIEBA or len(known_names) == 0:
        return candidates

    words_freq = {}
    for w, flag in pseg.cut(text):
        if flag in ("nr", "nz", "ns", "nt") and 2 <= len(w) <= 4:
            if w not in _STOP_WORDS and w not in known_all:
                words_freq[w] = words_freq.get(w, 0) + 1

    for word, count in words_freq.items():
        if count < 2:
            continue
        for known in known_names:
            if len(word) == len(known) and len(word) >= 2:
                sim = 0.0
                if _HAS_RAPIDFUZZ:
                    sim = fuzz.ratio(word, known) / 100.0
                else:
                    sim = difflib.SequenceMatcher(None, word, known).ratio()

                if 0.65 <= sim < 1.0:
                    hits = _find_mentions_with_lines(lines, word)
                    line_no = hits[0][0] if hits else None
                    loc_str = f"L{hits[0][0]}: {hits[0][1]}" if hits else ""
                    candidates.append({
                        "probe": "alias_drift",
                        "severity": "candidate_soft",
                        "line_no": line_no,
                        "also_flagged_by": None,
                        "title": f"实体别名漂移存疑：「{word}」与既有实体「{known}」极度近似",
                        "description": f"正文出现 {count} 次新词「{word}」，与既有实体「{known}」相似度达 {sim:.0%}，疑似同音/形近笔误导致实体另立新名。",
                        "evidence": loc_str,
                        "state_ref": f"entities.{known}",
                        "suggestion": f"确认正文是否确为既有角色「{known}」；若是，请统一定稿写法或将其追加至 aliases。"
                    })
                    break
    return candidates


def probe_address_mismatch(text: str, lines: list[str], book: Path, ch_num: int, ents_st: list[dict]) -> list[dict]:
    """探针 8：法定称谓漂移与禁忌称呼探针（防人设/称谓吃书）。"""
    candidates = []
    char_dir = book / "characters"
    if not char_dir.is_dir():
        return candidates

    seen_evidence = set()
    for f in char_dir.glob("*.md"):
        if f.name.endswith(".example.md") or f.stem == "character_card_standard":
            continue
        ctext = f.read_text(encoding="utf-8", errors="replace")
        for forbidden_match in re.finditer(r"(?:严禁|禁止)(?:出现|称呼|使用)?\s*([^\n。；]+)", ctext):
            fpart = forbidden_match.group(1)
            quotes = re.findall(r"[“\"「]([^”\"」]+)[”\"」]", fpart)
            if not quotes:
                continue

            for bad_term in quotes:
                if len(bad_term) < 2:
                    continue
                for idx, line in enumerate(lines, start=1):
                    dialogues = common.iter_line_dialogues(line)
                    for diag in dialogues:
                        if bad_term in diag:
                            ev_key = (idx, bad_term)
                            if ev_key in seen_evidence:
                                continue
                            seen_evidence.add(ev_key)
                            clean_line = line.strip()
                            if len(clean_line) > 80:
                                clean_line = clean_line[:77] + "…"
                            candidates.append({
                                "probe": "address_mismatch",
                                "severity": "candidate_hard",
                                "line_no": idx,
                                "also_flagged_by": None,
                                "title": f"法定称谓禁忌触犯：对白出现严禁称呼「{bad_term}」",
                                "description": f"卡片「{f.name}」明文锁定严禁使用称谓「{bad_term}」，但正文对白中出现该词汇，构成违规称谓漂移。",
                                "evidence": f"L{idx}: {clean_line}",
                                "state_ref": f"characters/{f.name}",
                                "suggestion": f"请对照细纲法定称谓清单，使用唯一指定称谓替换违禁词「{bad_term}」。"
                            })
    return candidates


# 称谓核的剥离字符：省略号 / 引号 / 各类标点与空白
_ADDR_TRIM_CHARS = "…⋯.。，,、·\"'“”‘’「」『』（）() \t　"


def _addr_core(term: str) -> str:
    """剥掉省略号/引号/标点，留下可机械校验的称谓核。

    例：叶澜心对李玄的法定称谓是「……你」这种**带省略号的代词形态**——机械查它
    既脆弱（省略号写法多变）又必然假阳性（「你」在正文里到处都是），故 core 长度
    < 2 时一律跳过；这类形态交 Auditor 的 LLM 语义层判断。
    """
    return str(term).strip().strip(_ADDR_TRIM_CHARS).strip()


def _present_name_set(cur_st: dict, ents_st: list[dict]) -> set[str]:
    """本章在场角色名集合（含别名与实体 id 展开）。

    在场唯一来源 = `current.present_characters`。**不能用「名字是否出现在正文」判在场**：
    ch_001 里李玄的名字通篇未出现（叶澜心此时还不知道他叫什么），
    但他确是在场说话的人，用正文判在场会直接漏掉他。
    """
    raw: list[str] = []
    if isinstance(cur_st, dict):
        v = cur_st.get("present_characters")
        if isinstance(v, list):
            raw = [str(x).strip() for x in v if str(x).strip()]
    names: set[str] = set(raw)
    for e in ents_st:
        name = str(e.get("name") or "").strip()
        alts = [str(a).strip() for a in (e.get("aliases") or []) if str(a).strip()]
        if name in raw or any(a in raw for a in alts) or str(e.get("id") or "") in raw:
            names.add(name)
            names.update(alts)
    names.discard("")
    return names


def probe_address_never_surfaced(text: str, lines: list[str], book: Path, ch_num: int,
                                 ents_st: list[dict], cur_st: dict) -> list[dict]:
    """探针 8 反向补盲：法定称谓「该叫却没叫」。

    `probe_address_mismatch` 只查一个方向——「卡片严禁的称呼是否出现」。
    ch_001 实战暴露了反向盲区：细纲明令李玄首句须以「丫头」称呼叶澜心，而 raw_v3
    里整个称谓缺失，探针却一声不吭（因为它根本不查「该叫却没叫」）。

    这里用 state 里机器可读的 address_matrix（`{目标: 我称呼对方}`，存的是**当前阶段**
    的法定形态，已随剧情推进更新）补上这一向。

    候选统一记在 `probe="address_mismatch"` 名下：这是同一探针的正反两面，
    探针总数仍为 8，不改变既有 audit JSON 契约。
    """
    candidates: list[dict] = []
    present = _present_name_set(cur_st, ents_st)
    if not present:
        return candidates
    for e in ents_st:
        if str(e.get("type") or "").lower() != "person":
            continue
        matrix = e.get("address_matrix")
        if not isinstance(matrix, dict) or not matrix:
            continue
        owner = str(e.get("name") or "").strip()
        if not owner or owner not in present:
            continue
        owner_in_text = owner in text
        for target, term in matrix.items():
            tgt = str(target).strip()
            # 对方不在场 → 本章本就没有开口称呼的场景，不报
            if not tgt or tgt not in present:
                continue
            core = _addr_core(term)
            # 代词/省略号形态不可机械校验（见 _addr_core）
            if len(core) < 2:
                continue
            if core in text:
                continue
            note = (f"（注：{owner} 的名字本身也未在正文出现，在场判定以 state 为准）"
                    if not owner_in_text else "")
            candidates.append({
                "probe": "address_mismatch",
                "severity": "candidate_soft",
                "line_no": None,
                "also_flagged_by": None,
                "title": f"法定称谓未落笔：{owner} 通篇未以「{core}」称呼 {tgt}",
                "description": (f"state 的 address_matrix 锁定 {owner} 对 {tgt} 的法定称谓为"
                                f"「{core}」，双方本章均在场，但正文通篇未出现该称谓。{note}"),
                "evidence": f"正文未出现「{core}」；在场名单含 {owner}、{tgt}",
                "state_ref": f"persons[{owner}].address_matrix[{tgt}]",
                "suggestion": (f"若本章 {owner} 确有开口机会，请让其以法定称谓「{core}」称呼 {tgt}"
                               "（称谓递进是长线人物关系的一部分）；若确无开口场合，可忽略本条。"),
            })
    return candidates


# ---------------------------------------------------------------------------
# 聚合入口
# ---------------------------------------------------------------------------

def run_audit(book: Path, ch: str) -> dict[str, Any]:
    """执行全部 8 项确定性机械审计探针，输出候选矛盾点汇总。"""
    n = common.chapter_token_to_num(ch)
    tok = f"ch_{n:03d}" if n else ch
    if not n:
        return {"chapter": ch, "error": f"无法解析章节号: {ch!r}"}

    finals = common.find_chapter_files(book, "final", n)
    target_file = None
    is_raw_fallback = False
    if finals:
        target_file = finals[-1]
    else:
        raws = common.find_chapter_files(book, "raw", n)
        if raws:
            target_file = raws[-1]
            is_raw_fallback = True
        else:
            return {"chapter": tok, "error": f"未找到 {tok} 的 manuscript 稿件（final 或 raw 均不存在）"}

    raw_text = target_file.read_text(encoding="utf-8", errors="replace")
    lines = raw_text.splitlines()
    text = "\n".join(lines)

    locked_st = state.load_state(book, "locked") if (book / "state" / "locked.json").is_file() else {}
    _ent_ok = any((book / "state" / f"{k}.json").is_file() for k in state.KIND_TABLES)
    ents_st = state.load_state(book, "entities").get("entries", []) if _ent_ok else []
    cur_st = state.load_state(book, "current") if (book / "state" / "current.json").is_file() else {}
    lines_st = state.load_state(book, "lines") if (book / "state" / "lines.json").is_file() else {}
    led_st = state.load_state(book, "ledger") if (book / "state" / "ledger.json").is_file() else {}
    cog_st = state.load_state(book, "cognition") if (book / "state" / "cognition.json").is_file() else {}

    raw_candidates: list[dict] = []
    raw_candidates.extend(probe_locked_facts(text, lines, n, locked_st, ents_st))
    raw_candidates.extend(probe_location_presence(
        text, lines, cur_st, ents_st,
        exempt_names=_not_yet_effective_deceased(locked_st, ents_st, n)))
    raw_candidates.extend(probe_charges_possession(text, lines, ents_st, cur_st))
    raw_candidates.extend(probe_amount_ledger(text, lines, led_st))
    # 视角角色：只有指名得到具体角色，旁白/心理描写的知情差穿帮才可判定
    pov_name = _resolve_pov_character(book, cur_st, ents_st, n)
    raw_candidates.extend(probe_secret_leakage(text, lines, lines_st, ents_st, pov_name))
    raw_candidates.extend(probe_cognition_stubs(text, lines, lines_st, cog_st))
    raw_candidates.extend(probe_alias_drift(text, lines, ents_st))
    raw_candidates.extend(probe_address_mismatch(text, lines, book, n, ents_st))
    # 探针 8 的反向补盲：法定称谓「该叫却没叫」（候选同样计入 address_mismatch）
    raw_candidates.extend(probe_address_never_surfaced(text, lines, book, n, ents_st, cur_st))

    candidates = []
    for idx, c in enumerate(raw_candidates, start=1):
        c["id"] = f"AUDIT-{idx:03d}"
        candidates.append(c)

    hard_count = sum(1 for c in candidates if c.get("severity") == "candidate_hard")
    soft_count = sum(1 for c in candidates if c.get("severity") == "candidate_soft")

    probe_counts = {
        "locked_facts": sum(1 for c in candidates if c.get("probe") == "locked_facts"),
        "location_presence": sum(1 for c in candidates if c.get("probe") == "location_presence"),
        "charges_possession": sum(1 for c in candidates if c.get("probe") == "charges_possession"),
        "amount_ledger": sum(1 for c in candidates if c.get("probe") == "amount_ledger"),
        "secret_leakage": sum(1 for c in candidates if c.get("probe") == "secret_leakage"),
        "cognition_stubs": sum(1 for c in candidates if c.get("probe") == "cognition_stubs"),
        "alias_drift": sum(1 for c in candidates if c.get("probe") == "alias_drift"),
        "address_mismatch": sum(1 for c in candidates if c.get("probe") == "address_mismatch"),
    }

    rel_path = target_file.relative_to(book).as_posix()
    return {
        "chapter": tok,
        "file": rel_path,
        "fallback_raw": is_raw_fallback,
        # 本章视角角色（None = 指名不到，旁白/心理描写的知情差扫描不启用）
        "pov": pov_name,
        "total_candidates": len(candidates),
        "hard_count": hard_count,
        "soft_count": soft_count,
        "probe_counts": probe_counts,
        "candidates": candidates,
    }
