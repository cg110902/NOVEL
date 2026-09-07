"""engine/audit.py: 确定性矛盾排查探针（7大机械探针：在场/充能/金额/KNO/不可逆/认知差/别名漂移）。

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
      1. 死者名紧跟发言动词（道/说/冷笑/…）——活人发言；
      2. 死者名紧贴引号边界（「陆沉舟 / 陆沉舟」）——对白归属或直呼。
    行内其余位置出现死者名不再单独构成硬矛盾候选。
    """
    if not name:
        return False
    if any(f"{name}{v}" in content for v in _SPEECH_VERBS):
        return True
    return (f"「{name}" in content or f"“{name}" in content
            or f"{name}」" in content or f"{name}”" in content)


_CN_NUM_MAP = vocab.CN_NUM_MAP



def _parse_cn_number(s: str) -> int | None:
    """简易中文数字转整数（覆盖常用小额银钱数额）。"""
    s = s.strip()
    if s.isdigit():
        return int(s)
    try:
        if len(s) == 1 and s in _CN_NUM_MAP:
            return _CN_NUM_MAP[s]
        if len(s) == 2 and s.startswith("十") and s[1] in _CN_NUM_MAP:
            return 10 + _CN_NUM_MAP[s[1]]
        if "万" in s:
            parts = s.split("万", 1)
            w_part = _parse_cn_number(parts[0]) or 1
            r_part = _parse_cn_number(parts[1]) if parts[1] else 0
            return w_part * 10000 + (r_part or 0)
        total = 0
        cur = 0
        for ch in s:
            v = _CN_NUM_MAP.get(ch)
            if v is None:
                continue
            if v in (10, 100, 1000):
                total += (cur or 1) * v
                cur = 0
            else:
                cur = v
        total += cur
        return total if total > 0 else None
    except Exception:
        return None


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


def probe_location_presence(text: str, lines: list[str], cur_st: dict, ents_st: list[dict]) -> list[dict]:
    """探针 2：空间与在场探针（检查角色地理空间跳跃与存活状态）。"""
    candidates = []
    for ent in ents_st:
        name = ent.get("name", "")
        if not name:
            continue
        if ent.get("life_status") == "deceased":
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
        if etype not in ("item", "artifact", "weapon", "consumable", "prop"):
            continue
        name = ent.get("name", "")
        charges = ent.get("charges")
        status = ent.get("status", "")
        aliases = ent.get("aliases", []) or []
        names_to_check = [name] + [a for a in aliases if a]

        is_exhausted = (charges == 0) or (status in ("exhausted", "consumed", "destroyed", "lost"))
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
                        "also_flagged_by": "item_charges_zero",
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
    _units_pat = "|".join(vocab.CURRENCY_UNITS)
    money_pat = re.compile(rf"(?:{_verbs_pat})\s*([0-9一二两三四五六七八九十百千万]+)\s*({_units_pat})")
    for line_no, line in enumerate(lines, start=1):
        for m in money_pat.finditer(line):
            raw_num, unit = m.group(1), m.group(2)
            val = _parse_cn_number(raw_num)
            if val is None or val <= 0:
                continue
            pool_key = None
            if "两" in unit or "银" in unit or "白银" in unit:
                pool_key = "silver" if "silver" in pools else None
            elif "灵石" in unit or "灵晶" in unit or "仙玉" in unit or "玄晶" in unit:
                pool_key = "spirit_stone" if "spirit_stone" in pools else None
            elif "铜钱" in unit or "文" in unit:
                pool_key = "copper" if "copper" in pools else None
            elif "金" in unit or "黄金" in unit:
                pool_key = "gold" if "gold" in pools else None

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
                        "also_flagged_by": "amount_unmatched",
                        "title": f"金额收支存疑：正文支出 {val} {unit} 大于账本余额 ({bal})",
                        "description": f"正文出现单次大额支出，但对应资源池 {pool_key} 当前余额仅为 {bal}。",
                        "evidence": f"L{line_no}: {line.strip()[:80]}",
                        "state_ref": f"ledger.pools.{pool_key}",
                        "suggestion": "核对是否有先期入账未登入提案，或修改正文数值使之与财务账本自洽。"
                    })
    return candidates


_SPEAKER_MODS = vocab.SPEAKER_MODS_PATTERN


def probe_secret_leakage(text: str, lines: list[str], lines_st: dict,
                         ents_st: list[dict] | None = None) -> list[dict]:
    """探针 5：KNO 秘密知情差泄露（检查不知情者在对话中直接谈及秘密）。"""
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
    for kno in knowledge:
        status = str(kno.get("status", "")).lower()
        if status in ("revealed", "公开"):
            continue
        kid = kno.get("id", "KNO")
        secret = str(kno.get("secret", "")).strip()
        holders = kno.get("holders") or kno.get("knower") or []
        knower = set(str(k).strip() for k in holders)
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
                    if speaker and knower and speaker not in knower:
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
                        break
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


# ---------------------------------------------------------------------------
# 聚合入口
# ---------------------------------------------------------------------------

def run_audit(book: Path, ch: str) -> dict[str, Any]:
    """执行全部 7 项确定性机械审计探针，输出候选矛盾点汇总。"""
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
    ents_st = state.load_state(book, "entities").get("entries", []) if (book / "state" / "entities.json").is_file() else []
    cur_st = state.load_state(book, "current") if (book / "state" / "current.json").is_file() else {}
    lines_st = state.load_state(book, "lines") if (book / "state" / "lines.json").is_file() else {}
    led_st = state.load_state(book, "ledger") if (book / "state" / "ledger.json").is_file() else {}
    cog_st = state.load_state(book, "cognition") if (book / "state" / "cognition.json").is_file() else {}

    raw_candidates: list[dict] = []
    raw_candidates.extend(probe_locked_facts(text, lines, n, locked_st, ents_st))
    raw_candidates.extend(probe_location_presence(text, lines, cur_st, ents_st))
    raw_candidates.extend(probe_charges_possession(text, lines, ents_st, cur_st))
    raw_candidates.extend(probe_amount_ledger(text, lines, led_st))
    raw_candidates.extend(probe_secret_leakage(text, lines, lines_st, ents_st))
    raw_candidates.extend(probe_cognition_stubs(text, lines, lines_st, cog_st))
    raw_candidates.extend(probe_alias_drift(text, lines, ents_st))

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
    }

    rel_path = target_file.relative_to(book).as_posix()
    return {
        "chapter": tok,
        "file": rel_path,
        "fallback_raw": is_raw_fallback,
        "total_candidates": len(candidates),
        "hard_count": hard_count,
        "soft_count": soft_count,
        "probe_counts": probe_counts,
        "candidates": candidates,
    }
