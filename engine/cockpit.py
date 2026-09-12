"""cockpit：主控态势驾驶舱与自愈雷达（专供 AI / 主控秒懂全链路态势与自愈决策）。

功能矩阵：
1. workflow：精准定位当前章节与活跃工序 Stage，提供 0 歧义的下一步调度指令与标准派发参数。
2. dramatic_momentum：计算戏剧动力学（承接余震 aftershock、悬顶危机 active_pressures、现场信息差机锋 dramatic_irony、两两张力网络 scene_tensions）。
3. health_and_remedies：全书事实核验、确定性断言体检与具备可操作性的自愈处方（Remedies）。
4. critic_radar：直接透视上一章读者催更便签（体感/连续性红旗/最想看/最怕踩），免去主控翻读外部文件。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import checks, common, evidence, graph, state
from .commands._shared import parse_audit_frontmatter  # 仲裁报告 front-matter 解析（Stage 5 仲裁看板）


def _infer_active_chapter(book: Path) -> str:
    """自动推断当前最需要推进或处理的章节编号。

     P1-4：口径与 `status` 的「下一章」统一——**连续推进，绝不跳章**。
    原实现取 beats/raw/final/inbox/synopsis 里出现过的最大章号，于是一份游离的
    未来章 beats（如手滑 `beats new ch_7`）会把工序指针劫持到 ch_007，而 `status`
    仍说 ch_005；主控按 SKILL「严禁猜测工序，直接执行 next_action.command」就会跳过
    中间章。现改为：锚点 = max(最后定稿章, 最后封存章)，指针 = [1, 锚点+1] 里第一个
    尚未封存的章号。
    """
    nums_with_artifact: set[int] = set()
    for area in ("beats", "raw", "final"):
        for f in common.find_chapter_files(book, area):
            num = common.chapter_number_from_name(f.name)
            if num:
                nums_with_artifact.add(num)
    inbox = book / "state" / "inbox"
    if inbox.is_dir():
        for p in inbox.glob("ch_*.json"):
            num = common.chapter_number_from_name(p.name)
            if num:
                nums_with_artifact.add(num)

    synopsis = state.load_state(book, "synopsis")
    syn = synopsis.get("chapters", {})
    if isinstance(syn, dict):
        synced_chapters = set(syn.keys())
    elif isinstance(syn, list):
        synced_chapters = {c.get("chapter") for c in syn if isinstance(c, dict)}
    else:
        synced_chapters = set()

    synced_nums = {n for n in (common.chapter_token_to_num(sc) for sc in synced_chapters) if n}
    final_nums = {common.chapter_number_from_name(f.name) or 0
                  for f in common.find_chapter_files(book, "final")}
    final_nums.discard(0)

    anchor = max([0, *synced_nums, *final_nums])
    for n in range(1, anchor + 2):
        if n not in synced_nums:
            return f"ch_{n:03d}"
    return f"ch_{anchor + 1:03d}"


def stray_artifacts(book: Path, active_ch: str) -> list[str]:
    """ P1-4：超前于工序指针的游离工件（只提示，不改变指针）。"""
    n_active = common.chapter_token_to_num(active_ch) or 0
    out: list[str] = []
    for area in ("beats", "raw", "final"):
        for f in common.find_chapter_files(book, area):
            num = common.chapter_number_from_name(f.name)
            if num and num > n_active:
                out.append(f"{area}/{f.name}")
    return sorted(out)


def _find_chapter_vol(book: Path, ch: str) -> str:
    """确定章节所属分卷目录名称。"""
    ch_num = common.chapter_token_to_num(ch) or 1
    beats_files = common.find_chapter_files(book, "beats", ch)
    if beats_files:
        try:
            rel_parts = beats_files[-1].relative_to(book / "outlines").parts
            if rel_parts and rel_parts[0].startswith("vol_"):
                return rel_parts[0]
        except (OSError, ValueError):
            pass
    for vdir in sorted((book / "outlines").glob("vol_*")):
        outline_file = vdir / "outline.md"
        if outline_file.is_file():
            try:
                otext = outline_file.read_text(encoding="utf-8", errors="ignore")
                m = re.findall(r"ch[_\-](\d{1,4})", otext)
                if m and int(m[0]) <= ch_num <= int(m[-1]):
                    return vdir.name
            except OSError:
                pass
    return f"vol_{(ch_num - 1) // 50 + 1:02d}"


def _after_keyword(line: str, keyword: str) -> str:
    """取便签行中关键词之后的内容（容忍 emoji/加粗/列表前缀，如 `- 💬 **本章体感**：xxx`）。"""
    m = re.search(re.escape(keyword), line)
    if not m:
        return ""
    return line[m.end():].strip()


def _clean_value(text: str) -> str:
    """清洗提取值：去列表/加粗残留、去"（仅供参考）"类包裹说明、去尾随冒号。"""
    v = re.sub(r"^[:：\s*#\-]+", "", text).strip()
    v = re.sub(r"^[（(][^）)]*[)）][:：]?\s*", "", v).strip()
    v = re.sub(r"[:：]\s*$", "", v).strip()
    return v


def _item_text(line: str) -> str:
    """提取分区列表项的实质内容（去序号、去【标签】前缀）。"""
    s = re.sub(r"^[\d一二三四五六七八九十]+[\.、]\s*", "", line.strip())
    s = re.sub(r"^[-*]\s*", "", s)
    s = re.sub(r"^【[^】]*】[:：]?\s*", "", s)
    return s.strip()


def _get_critic_radar(book: Path, ch_num: int) -> dict[str, str]:
    """读取上一章读者催更便签，提炼体感、连续性红旗、期待与避坑点。

    兼容三种写法：① 字段直写（`- 🚩 **连续性红旗**：xxx`）；
    ② 标题行带内容（`### ⚠️ 最怕踩：圣母`）；
    ③ 标题+分区列表（SKILL 模板格式：标题下首条列表项作为该维度摘要）。
    """
    radar = {"prev_chapter": "", "vibe": "", "anticipation": "", "taboos": "", "continuity": "",
             "fatigue": "", "foreshadow_info": "", "protagonist_liveliness": "",
             "character_sympathy": ""}
    if ch_num <= 1:
        return radar

    prev_ch = f"ch_{ch_num - 1:03d}"
    radar["prev_chapter"] = prev_ch
    critic_path = book / "log" / "critic" / f"{prev_ch}.md"
    if not critic_path.is_file():
        return radar

    def _put(field: str, value: str) -> None:
        if value and not radar[field]:
            radar[field] = value

    def _taboo_kw(s: str) -> str:
        """避坑字段关键词：最长匹配优先，避免“读者最怕踩的坑：”把“的坑”当内容。"""
        for kw in ("最怕踩的坑", "最怕踩", "避坑"):
            if kw in s:
                return kw
        return ""

    # 每字段关键词变体容错（最长优先）——Critic 子代理的标签写法漂移
    # （如「体感」vs「本章体感」）不再静默丢失该维度
    _FIELD_KWS = (
        ("vibe", ("本章体感", "阅读体感", "体感")),
        ("continuity", ("连续性红旗", "连续性", "红旗")),
        ("fatigue", ("阅读疲劳度", "疲劳度", "疲劳")),
        ("foreshadow_info", ("伏笔与信息差", "信息差")),
        ("protagonist_liveliness", ("主角活人感", "活人感")),
        ("character_sympathy", ("配角路人缘", "角色路人缘", "路人缘")),
    )
    _ANTICIPATION_KWS = ("下章最想看", "最想看", "迫切期待")

    # 优先解析便签中可能附带的 JSON 结构化块 ```json { ... } ```
    try:
        text = critic_path.read_text(encoding="utf-8", errors="replace")
        m_json = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m_json:
            try:
                c_data = json.loads(m_json.group(1))
                if isinstance(c_data, dict):
                    for k in ("vibe", "fatigue", "foreshadow_info", "protagonist_liveliness", "character_sympathy", "continuity"):
                        if c_data.get(k):
                            _put(k, str(c_data[k]))
                    if c_data.get("anticipation"):
                        ants = c_data["anticipation"]
                        _put("anticipation", "；".join(ants) if isinstance(ants, list) else str(ants))
                    if c_data.get("taboos"):
                        _put("taboos", str(c_data["taboos"]))
                    if c_data.get("water_level"):
                        radar["water_level"] = str(c_data["water_level"])
            except json.JSONDecodeError:
                pass
    except OSError:
        pass

    section = None  # 标题开启的分区（anticipation/taboos），供列表项回填
    try:
        text = critic_path.read_text(encoding="utf-8", errors="replace")
        for raw in text.splitlines():
            s = raw.strip()
            if not s:
                continue
            if s.startswith("#"):
                section = None
                hit_ant = next((kw for kw in _ANTICIPATION_KWS if kw in s), None)
                if hit_ant:
                    section = "anticipation"
                    _put("anticipation", _clean_value(_after_keyword(s, hit_ant)))
                else:
                    kw = _taboo_kw(s)
                    if kw:
                        section = "taboos"
                        _put("taboos", _clean_value(_after_keyword(s, kw)))
                if section and radar[section]:
                    section = None  # 标题行已自带内容，无需列表回填
                continue
            matched = False
            for field, kws in _FIELD_KWS:
                hit = next((kw for kw in kws if kw in s), None)
                if not hit:
                    continue
                v = _clean_value(_after_keyword(s, hit))
                if field == "continuity":
                    if v and v != "无":
                        _put(field, v)
                else:
                    _put(field, v)
                matched = True
                break
            if not matched:
                hit_ant = next((kw for kw in _ANTICIPATION_KWS if kw in s), None)
                if hit_ant:
                    _put("anticipation", _clean_value(_after_keyword(s, hit_ant)))
                    section = None
                    matched = True
                else:
                    kw = _taboo_kw(s)
                    if kw:
                        _put("taboos", _clean_value(_after_keyword(s, kw)))
                        section = None
                        matched = True
            if not matched and section and not radar[section] \
                    and re.match(r"^([\d一二三四五六七八九十]+[\.、]|[-*])", s):
                _put(section, _item_text(s))
    except OSError:
        pass  # 便签不可读：雷达字段留空（：不再吞全部异常）

    # 便签存在但雷达字段全空 → 明示「格式疑似偏离模板」，不再让主控误读为「无反馈」
    try:
        _text = critic_path.read_text(encoding="utf-8", errors="replace")
        _is_skeleton = "SKELETON" in _text[:400] or "（待评）" in _text[:1200]
        _content_lines = [ln for ln in _text.splitlines()
                          if ln.strip() and not ln.strip().startswith(("#", "<!--", "-->"))]
        _values = [radar[k] for k in ("vibe", "anticipation", "taboos", "continuity", "fatigue",
                                      "foreshadow_info", "protagonist_liveliness", "character_sympathy")]
        if not _is_skeleton and len(_content_lines) >= 3 and not any(_values):
            radar["format_warning"] = ("便签存在但雷达 8 字段全空——格式疑似偏离规范模板"
                                       "（关键词：本章体感/连续性红旗/疲劳度/信息差/活人感/路人缘/最想看/最怕踩），"
                                       "请回读原文核对；雷达不作「无反馈」解读")
    except OSError:
        pass
    return radar


def _extract_dramatic_irony(lines: dict, scene_chars: list[str]) -> list[str]:
    """提取与现场登场角色直接相关的认知差、假象与核心秘密。"""
    irony_list: list[str] = []
    char_set = set(scene_chars)

    # 1. 误会与认知差 (misunderstandings)
    for m in lines.get("misunderstandings", []):
        if str(m.get("status", "")).lower() in ("resolved", "defused"):
            continue
        parties = str(m.get("parties", ""))
        content = str(m.get("content", ""))
        truth = str(m.get("truth", "待揭示"))
        mid = m.get("id", "MIS")
        # 只要涉及主角或现场角色
        if any(c in parties or c in content for c in char_set) or not scene_chars:
            irony_list.append(f"[{mid} 认知差] 误解假象：{content} ｜ 事实真相：{truth}（涉及：{parties}）")

    # 2. 核心秘密与情报隔离 (knowledge)
    for k in lines.get("knowledge", []):
        if str(k.get("status", "")).lower() in ("revealed", "public"):
            continue
        kid = k.get("id", "KNO")
        secret = str(k.get("secret", ""))
        # 原写法 k.get("note", "保密中") 对**空串**失效——state.py 落盘时写的
        # 是 "note": ""，于是默认值取不到，dramatic_irony 输出留下空尾巴「知情边界：」。
        # beats 里同一信息用 `or "保密中"` 显示正常，两处口径现统一。
        note = str(k.get("note") or "保密中")
        if any(c in secret or c in note for c in char_set) or not scene_chars:
            irony_list.append(f"[{kid} 秘密差] 核心秘密：{secret} ｜ 知情边界：{note}")

    return irony_list


def _extract_lines_radar(lines: dict, ch_num: int) -> dict[str, Any]:
    """对全书伏笔暗线进行智能分级分类与生命周期雷达监测。

    分类维度：
    1. imminent: 即时短线/临界线（预定在当前章及未来3章内回收，或已逾期）
    2. volume_mid: 卷内主干中线（预定在本卷内 50 章以内回收）
    3. epic_longline: 跨卷史诗长线（标记为 'longline' 或目标跨越当前卷）
    4. dormant_warnings: 沉寂饥饿暗线（植入距今 >= 10章未提及/推进）
    """
    vol_end = ((ch_num - 1) // 50 + 1) * 50
    imminent: list[str] = []
    volume_mid: list[str] = []
    epic_longline: list[str] = []
    dormant_warnings: list[str] = []

    total_active_foreshadows = 0
    total_longline_foreshadows = 0

    # 汇总遍历三大类：foreshadows (GUN), misunderstandings (MIS), knowledge (KNO)
    categories = [
        ("foreshadows", "GUN", ("resolved",)),
        ("misunderstandings", "MIS", ("resolved", "defused")),
        ("knowledge", "KNO", ("revealed", "public")),
    ]

    for key, prefix, resolved_statuses in categories:
        items = lines.get(key, [])
        for item in items:
            status = str(item.get("status", "")).strip().lower()
            if status in resolved_statuses:
                continue

            lid = item.get("id", prefix)
            target = item.get("target_ch")
            plant = item.get("plant_ch")

            # 提取描述标题与细节
            if key == "foreshadows":
                title = item.get("name", "未命名伏笔")
                plan = item.get("plan", "")
                detail = f"「{title}」{plan}" if plan else f"「{title}」"
                total_active_foreshadows += 1
                if target == "longline":
                    total_longline_foreshadows += 1
            elif key == "misunderstandings":
                parties = item.get("parties", "")
                content = item.get("content", "")
                detail = f"「{parties}」{content}"
            else:  # knowledge
                secret = item.get("secret", "")
                detail = f"{secret}"

            # 1. 沉寂饥饿检测 (距今已 >= 10 章)
            if isinstance(plant, int) and (ch_num - plant) >= 10:
                dormant_warnings.append(
                    f"[{lid}] 💤 沉寂饥饿警告：埋设于 ch_{plant:03d}，距今已 {ch_num - plant} 章未推进！内容：{detail}"
                )

            # 2. 跨卷长线
            if target == "longline" or (isinstance(target, int) and target > vol_end):
                tgt_str = "全书史诗长线" if target == "longline" else f"跨卷长线(目标 ch_{target:03d})"
                epic_longline.append(f"[{lid}] 🌌 {tgt_str}：{detail} (当前状态: {item.get('status', 'Active')})")
            # 3. 即时短线 / 逾期临界
            elif isinstance(target, int) and target <= ch_num + 3:
                diff = target - ch_num
                if diff < 0:
                    status_str = f"🚨【已逾期 {abs(diff)} 章待收束】"
                elif diff == 0:
                    status_str = "🔥【本章预定引爆点】"
                else:
                    status_str = f"⏳【距引爆仅剩 {diff} 章】(预定 ch_{target:03d})"
                imminent.append(f"[{lid}] {status_str}：{detail}")
            # 4. 卷内主干中线
            elif isinstance(target, int):
                diff = target - ch_num
                volume_mid.append(f"[{lid}] 🎯【卷内中线·还剩 {diff} 章】(目标 ch_{target:03d})：{detail}")
            else:
                # 未指定 target_ch 的，默认按卷内中线观察
                volume_mid.append(f"[{lid}] 🎯【未定收束章】：{detail}")

    stats = {
        "active_foreshadows_count": total_active_foreshadows,
        "longline_foreshadows_count": total_longline_foreshadows,
        "imminent_count": len(imminent),
        "dormant_count": len(dormant_warnings),
    }

    return {
        "imminent": imminent,
        "volume_mid": volume_mid,
        "epic_longline": epic_longline,
        "dormant_warnings": dormant_warnings,
        "stats": stats,
    }


def _load_final_texts(book: Path, current_ch: int) -> dict[int, str]:
    """一次性预读 1..current_ch-1 的定稿文本（键=章号）。

    供角色沉寂/死库存雷达共用：避免每个实体各自重新 glob+read 全部 final。
    走 evidence.final_chapters 口径，天然支持多卷、版本择优及首行章题剥离。
    """
    texts: dict[int, str] = {}
    for tok, n, text in evidence.final_chapters(book):
        if n < current_ch:
            texts[n] = text
    return texts


def _compute_character_dormancy(book: Path, current_ch: int,
                                final_texts: dict[int, str] | None = None) -> list[str]:
    """滑动窗口计算核心角色沉寂预警（>=3章未露面或未登场）。"""
    alerts = []
    if current_ch <= 2:
        return alerts
    if final_texts is None:
        final_texts = _load_final_texts(book, current_ch)

    char_files = list((book / "characters").glob("*.md"))
    char_names = [f.stem for f in char_files if not f.stem.startswith(".")]

    entity_aliases: dict[str, list[str]] = {}
    try:
        entries = state.load_state(book, "entities").get("entries", [])
        for edata in entries:
            cname = str(edata.get("name", "")).strip()
            if not cname:
                continue
            aliases = [str(a).strip() for a in edata.get("aliases", []) if a and str(a).strip()]
            entity_aliases[cname] = aliases
            if edata.get("type") == "person" and cname not in char_names:
                char_names.append(cname)
    except (ValueError, OSError):
        pass  # 实体账本损坏：退化为仅 characters/ 目录名册

    char_last_seen = {c: 0 for c in char_names}

    # 1. 扫描各章正文（含别名）
    for ch_idx, text in final_texts.items():
        for c in char_names:
            names_to_check = [c] + entity_aliases.get(c, [])
            if any(nm and nm in text for nm in names_to_check):
                char_last_seen[c] = ch_idx

    # 2. 补核 timeline 事实事件（防止首次出场以代称入戏，但事实台账已明确登记）
    try:
        events = state.load_state(book, "timeline").get("events", [])
        for ev in events:
            ch_num = common.chapter_number_from_name(str(ev.get("chapter", "")))
            if ch_num and ch_num in final_texts:
                ev_str = str(ev.get("event", ""))
                for c in char_names:
                    names_to_check = [c] + entity_aliases.get(c, [])
                    if any(nm and nm in ev_str for nm in names_to_check):
                        if ch_num > char_last_seen.get(c, 0):
                            char_last_seen[c] = ch_num
    except (ValueError, OSError):
        pass

    proj = common.load_json(book / "project.json", default={}) or {}
    protagonist = proj.get("protagonist", "主角名")

    for c, last_ch in char_last_seen.items():
        if c in (protagonist, "protagonist"):
            continue
        if last_ch > 0:
            dormant_count = current_ch - 1 - last_ch
            if dormant_count >= 3:
                alerts.append(f"👤 [角色沉寂预警] 「{c}」已连续 {dormant_count} 章未露面(上次登场: ch_{last_ch:03d})，建议当章考虑安排其出场、互动或侧面传讯。")
        elif current_ch >= 4:
            alerts.append(f"👤 [角色登场提醒] 「{c}」已在人物卡中设定，但在前 {current_ch - 1} 章正文中尚未正式登场/被提及，若为当卷重要角色，建议尽早在适当场景引出。")

    return alerts


def _compute_tension_rhythm(book: Path, current_ch: int) -> list[str]:
    """正弦张力潮汐波峰分析（防连续高潮导致多巴胺疲劳，防连续平缓导致弃书）。"""
    alerts = []
    if current_ch <= 2:
        return alerts

    recent_scores = []
    recent_modes = []
    for ch_idx in range(max(1, current_ch - 3), current_ch):
        ch_tok = f"ch_{ch_idx:03d}"
        beats_files = list((book / "outlines").glob(f"*/beats/{ch_tok}.md"))
        if not beats_files:
            continue
        text = beats_files[0].read_text(encoding="utf-8", errors="ignore")
        m_score = re.search(r"^tension_score:\s*(\d+)", text, re.MULTILINE)
        m_mode = re.search(r"^stage_mode:\s*(\w+)", text, re.MULTILINE)
        if m_score:
            recent_scores.append(int(m_score.group(1)))
        if m_mode:
            recent_modes.append(m_mode.group(1))

    if len(recent_scores) >= 2 and all(s >= 8 for s in recent_scores[-2:]):
        alerts.append("🌊 [张力正弦律建议] 近期连续处于高位张力博弈(张力>=8)，为防读者多巴胺疲劳，建议当章选用 Harvest(清点) 或 Simmering(试探) 适度缓冲。")
    elif len(recent_scores) >= 3 and all(s <= 5 for s in recent_scores[-3:]):
        alerts.append("⚡ [张力正弦律建议] 近期连续平缓(张力<=5)，建议当章拉升冲突对抗，安排矛盾激化点与高潮爆发。")

    return alerts


def _compute_dead_inventory(book: Path, current_ch: int,
                            final_texts: dict[int, str] | None = None) -> list[str]:
    """背包资产周转与沉睡道具/词条雷达。"""
    alerts = []
    if current_ch <= 3:
        return alerts
    if final_texts is None:
        final_texts = _load_final_texts(book, current_ch)

    try:
        entries = state.load_state(book, "entities").get("entries", [])
        tl_events = state.load_state(book, "timeline").get("events", [])
        for edata in entries:
            if edata.get("type") == "item":
                iname = str(edata.get("name", "")).strip()
                if iname and iname not in ("我悟了，你随意",):
                    aliases = [iname] + [str(a).strip() for a in edata.get("aliases", []) if a and str(a).strip()]
                    last_seen_ch = 0
                    for ch_idx, text in final_texts.items():
                        if any(a in text for a in aliases):
                            last_seen_ch = ch_idx
                    for ev in tl_events:
                        ch_num = common.chapter_number_from_name(str(ev.get("chapter", "")))
                        if ch_num and ch_num in final_texts:
                            ev_str = str(ev.get("event", ""))
                            if any(a in ev_str for a in aliases):
                                if ch_num > last_seen_ch:
                                    last_seen_ch = ch_num
                    if last_seen_ch > 0 and (current_ch - 1 - last_seen_ch) >= 3:
                        alerts.append(f"🎒 [沉睡道具提醒] 道具/词条「{iname}」已连续 {current_ch - 1 - last_seen_ch} 章未登场(上次使用: ch_{last_seen_ch:03d})，可考虑在后续战力推演、融合升华或剧情破局时调用。")
    except (ValueError, OSError):
        pass  # 状态账本损坏：跳过沉睡道具提醒

    return alerts


def get_algorithmic_guidance(book: Path, current_ch: int) -> list[str]:
    """聚合所有确定性算法制导胶囊（finals 只读一次，供沉寂/死库存雷达共用）。"""
    final_texts = _load_final_texts(book, current_ch)
    guidance = []
    guidance.extend(_compute_character_dormancy(book, current_ch, final_texts))
    guidance.extend(_compute_tension_rhythm(book, current_ch))
    guidance.extend(_compute_dead_inventory(book, current_ch, final_texts))
    return guidance


def build_cockpit_briefing(book: Path, ch: str | None = None) -> dict[str, Any]:
    """计算并构建主控态势驾驶舱完整数据模型。"""
    # NOVEL_STUDIO_DEBUG=1 时聚合各节耗时（briefing.debug_timing_ms + stderr）
    import time as _time
    timings: dict[str, float] = {}
    t_start = _time.perf_counter()
    proj = common.load_json(book / "project.json", default={}) or {}
    target_ch = ch if ch else _infer_active_chapter(book)
    ch_num = common.chapter_token_to_num(target_ch) or 1
    ch_tok = f"ch_{ch_num:03d}"
    vol = _find_chapter_vol(book, ch_tok)
    # 游离的超前工件只提示，不参与指针推断
    stray = stray_artifacts(book, ch_tok)
    if stray:
        common.debug(f"cockpit: 工序指针 {ch_tok}；游离超前工件 {stray}")

    cur = {key: state.load_state(book, key) for key in ("current", "entities", "lines", "synopsis", "timeline")}
    timings["state_load_ms"] = round((_time.perf_counter() - t_start) * 1000, 1)

    # 1. 确定工作流与工序状态
    beats_files = common.find_chapter_files(book, "beats", ch_tok)
    raw_files = common.find_chapter_files(book, "raw", ch_tok)
    # Stage 3A/3B 分轨（V3.3 流水线）：raw_v1 = Drafter 毛坯，raw_v2 = Editor 骨肉稿，
    # raw_v3 = Stylist 脱水预定稿。
    # 此前把 `version >= 2` 一把抓成 raw_v2，导致 raw_v3 在驾驶舱里不存在：状态机
    # 从「有 raw_v2」直接跳到「有 final」，把 Stage 3B 脱水与 Stage 4C 定稿塌缩成
    # 一步，并把 Stage 4C 错标成「Stage 3B（脱水）／actor=Stylist」、交付目标错指
    # final/——与 AGENTS.md 角色矩阵（只有 Fixer 写 final）直接冲突。
    raw_v1_files = [f for f in raw_files if common.chapter_version_from_name(f.name) < 2]
    raw_v2_files = [f for f in raw_files if common.chapter_version_from_name(f.name) == 2]
    raw_v3_files = [f for f in raw_files if common.chapter_version_from_name(f.name) >= 3]
    final_files = common.find_chapter_files(book, "final", ch_tok)
    inbox_normal = (book / "state" / "inbox" / f"{ch_tok}.json").is_file()
    inbox_processed = (book / "state" / "inbox" / "processed" / f"{ch_tok}.json").is_file()
    inbox_failed = (book / "state" / "inbox" / "failed" / f"{ch_tok}.json").is_file()
    inbox_file = inbox_normal or inbox_processed
    critic_file = False
    _cf = book / "log" / "critic" / f"{ch_tok}.md"
    if _cf.is_file():
        try:
            # 引擎预填的 SKELETON 骨架不代表 Stage 4B 已完成，防「假便签」阻断真子代理派发
            critic_file = "SKELETON" not in _cf.read_text(encoding="utf-8", errors="replace")[:400]
        except OSError:
            critic_file = True
    # Stage 5 仲裁闸门：sync 在 audit_mode=strict 下强制要求带 front-matter 的仲裁报告，
    # 驾驶舱此前不追踪它，顺着「下一步」走必然在 Stage 5 撞墙。
    audit_mode = str(proj.get("audit_mode", "strict")).strip().lower()
    audit_ready = audit_mode == "off"
    audit_state = "off" if audit_ready else "missing"
    _af = book / "log" / "audit" / f"{ch_tok}.md"
    if not audit_ready and _af.is_file():
        try:
            _fm = parse_audit_frontmatter(_af.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            _fm = None
        if _fm is None:
            audit_state = "no_frontmatter"
        else:
            audit_ready = True
            try:
                _logic_n = int(_fm.get("logic", 0) or 0)
            except (TypeError, ValueError):
                _logic_n = 0
            # 与 sync 闸门同口径：hard 或 logic 任一未裁定都算 blocked（驾驶舱不能比闸门松）
            audit_state = ("blocked" if (int(_fm.get("hard", 0) or 0) > 0 or _logic_n > 0)
                           and not bool(_fm.get("adjudicated", False)) else "pass")

    syn = cur["synopsis"].get("chapters", {})
    if isinstance(syn, dict):
        synced_chapters = set(syn.keys())
    elif isinstance(syn, list):
        synced_chapters = {c.get("chapter") for c in syn if isinstance(c, dict)}
    else:
        synced_chapters = set()
    is_synced = ch_tok in synced_chapters

    status = {
        "beats": bool(beats_files),
        "raw": bool(raw_v1_files),
        "raw_v2": bool(raw_v2_files),
        "raw_v3": bool(raw_v3_files),
        # Stage 4A 的交付物（问题清单）与 Stage 5 闸门报告是**两份不同工件**：
        # issues_*.md 由 Auditor 子代理产出、是 Stage 4C 定稿师的输入；ch_*.md 由引擎
        # `audit --write` 机械生成、是 sync 的闸门。驾驶舱此前只追踪后者，
        # 于是完全无从提示「先跑 Auditor 出问题清单」。
        "issues": (book / "log" / "audit" / f"issues_{ch_tok}.md").is_file(),
        "final": bool(final_files),
        "proposal": inbox_file,
        "proposal_failed": inbox_failed,
        "critic": critic_file,
        "audit": audit_ready,
        "audit_state": audit_state,
        "audit_mode": audit_mode,
        "synced": is_synced,
    }

    # 判定当前 Stage 与下一步行动指令
    if is_synced:
        curr_stage = "Completed (当章已封存)"
        next_ch = f"ch_{ch_num + 1:03d}"
        next_action = {
            "actor": "Director",
            "stage": "Stage 1",
            "instruction": f"当章已全部完工并同步封存，推进至下一章 {next_ch}"
                           "（按章程取证规则：ask=不在眼前必问 ／ pov=跨章对手戏必跑 ／ calendar=排产参考）",
            "command": f"python studio.py beats new {next_ch} --write",
            "target_file": f"outlines/{vol}/beats/{next_ch}.md"
        }
    elif not status["beats"]:
        curr_stage = "Stage 1 (细纲构思)"
        next_action = {
            "actor": "Director",
            "stage": "Stage 1",
            "instruction": "吸纳上一章读者催更便签与戏剧余震，生成并确认细纲任务书落盘"
                           "（按章程取证规则：ask=不在眼前必问 ／ pov=跨章对手戏必跑 ／ calendar=排产参考）",
            "command": f"python studio.py beats new {ch_tok} --write",
            "target_file": f"outlines/{vol}/beats/{ch_tok}.md"
        }
    elif not status["raw"]:
        curr_stage = "Stage 2 (初稿起草)"
        next_action = {
            "actor": "Drafter",
            "stage": "Stage 2",
            "instruction": "向起草员 Drafter 下达 Stage 2 标准工序派发令，放飞算力展开核心场景",
            "command": f"python studio.py pack {ch_tok} --full",
            "target_file": f"manuscript/{vol}/raw/{ch_tok}_v1.md"
        }
    elif not status["raw_v2"]:
        curr_stage = "Stage 3A (骨肉重塑)"
        next_action = {
            "actor": "Editor",
            "stage": "Stage 3A",
            "instruction": "向精修师 Editor 下达 Stage 3A 标准工序派发令：剧情做加法、潜台词与气口缝合，产出初修骨肉稿",
            "command": f"view_file manuscript/{vol}/raw/{ch_tok}_v1.md",
            "target_file": f"manuscript/{vol}/raw/{ch_tok}_v2.md"
        }
    elif not status["raw_v3"]:
        curr_stage = "Stage 3B (通俗脱水与扫读优化)"
        next_action = {
            "actor": "Stylist",
            "stage": "Stage 3B",
            "instruction": "向脱水师 Stylist 下达 Stage 3B 标准工序派发令：减法去油、去冷脸、斩断反刍，产出脱水预定稿 raw_v3",
            "command": f"view_file manuscript/{vol}/raw/{ch_tok}_v2.md",
            "target_file": f"manuscript/{vol}/raw/{ch_tok}_v3.md"
        }
    elif not status["critic"] or not status["issues"]:
        # Stage 4A/4B 并发：Auditor 出问题清单（Stage 4C 定稿师的**输入**）＋ Critic 出催更便签。
        # 二者都以 raw_v3 为源，必须先于 Stage 4C 完成——否则 Fixer 拿不到问题清单。
        curr_stage = "Stage 4A/4B (并发审查与催更便签)"
        missing = []
        if not status["issues"]:
            missing.append("Auditor (Stage 4A-问题清单)")
        if not status["critic"]:
            missing.append("Critic (Stage 4B-老白催更便签)")
        next_action = {
            "actor": "Auditor & Critic (并发)",
            "stage": "Stage 4A/4B",
            "instruction": ("在单次 invoke_subagent 调用中并发唤起审查员 Auditor（交付 "
                            f"log/audit/issues_{ch_tok}.md 问题清单）与催更员 Critic"
                            f"（交付 log/critic/{ch_tok}.md 便签），二者均以 raw_v3 为源"),
            "command": f"view_file manuscript/{vol}/raw/{ch_tok}_v3.md",
            "target_file": f"log/audit/issues_{ch_tok}.md | log/critic/{ch_tok}.md",
            **({"missing": missing} if missing else {})
        }
    elif not status["final"]:
        curr_stage = "Stage 4C (终局定稿)"
        next_action = {
            "actor": "Fixer",
            "stage": "Stage 4C",
            "instruction": ("向定稿师 Fixer 下达 Stage 4C 标准工序派发令：读 beats + raw_v3 + "
                            f"log/audit/issues_{ch_tok}.md 靶向微调正文硬矛盾，落盘全书唯一法定定稿 final"),
            "command": f"view_file manuscript/{vol}/raw/{ch_tok}_v3.md",
            "target_file": f"manuscript/{vol}/final/{ch_tok}.md"
        }
    elif not status["proposal"]:
        curr_stage = "Stage 4D (增量事实提案)"
        if status.get("proposal_failed"):
            next_action = {
                "actor": "Director / Reader (修复 failed/ 提案)",
                "stage": "Stage 4D",
                "instruction": (f"本章提案位于 state/inbox/failed/{ch_tok}.json（上次 sync 校验未过）；"
                                "请就地修复该 JSON 后重跑 sync，引擎会自动捡回，无需重头起草提案"),
                "command": f"python studio.py sync {ch_tok} --dry-run",
                "target_file": f"state/inbox/failed/{ch_tok}.json"
            }
        else:
            next_action = {
                "actor": "Reader",
                "stage": "Stage 4D",
                "instruction": ("向审计员 Reader 下达 Stage 4D 标准工序派发令："
                                "以 final 为唯一法定事实源交付事实提案 JSON"),
                "command": f"view_file manuscript/{vol}/final/{ch_tok}.md",
                "target_file": f"state/inbox/{ch_tok}.json"
            }
    elif not status["audit"] or status.get("audit_state") == "blocked":
        # 引擎仲裁报告（由 final 机械生成，Stage 5 闸门必需）——排在 Stage 4D 之后、sync 之前
        curr_stage = "Stage 5 前置 (仲裁闸门报告)"
        if status.get("audit_state") == "blocked":
            instruct = ("仲裁报告存在硬矛盾且未裁定：请在报告中完成交叉核实并将 adjudicated 设为 true，"
                        f"或修正 hard 计数后重跑 `python studio.py audit {ch_tok} --write`")
        else:
            instruct = (f"运行 `python studio.py audit {ch_tok} --write` 生成带 front-matter 的"
                        "仲裁报告并补写裁决（Stage 5 闸门必需）")
        next_action = {
            "actor": "Auditor",
            "stage": "Stage 5 前置",
            "instruction": instruct,
            "command": f"python studio.py audit {ch_tok} --write",
            "target_file": f"log/audit/{ch_tok}.md"
        }
    else:
        curr_stage = "Stage 5 (状态同步与快照)"
        next_action = {
            "actor": "Director",
            "stage": "Stage 5",
            "instruction": "主控审定 Reader 提案，一键执行 sync 原子合并账目并封存快照"
                           "（审定存疑处可 `studio ask <关键词>` 只读取证后再裁决）",
            "command": f"python studio.py sync {ch_tok}",
            "target_file": f"state/snapshots/"
        }

    # 2. 计算戏剧动力学 (Dramatic Momentum)
    # 余震 (aftershock)
    aftershock = cur["current"].get("aftershock")
    if not aftershock:
        aftershock = cur["current"].get("situation") or "前情平稳过渡，暂无强烈震荡"

    # 悬顶危机倒计时 (active_pressures)
    active_pressures = list(cur["current"].get("active_pressures") or [])
    for clock in cur["timeline"].get("clocks", []):
        if str(clock.get("status", "")).lower() == "active":
            target = clock.get("target_ch")
            cname = clock.get("name", "未命名危机")
            cdesc = clock.get("desc", "")
            if isinstance(target, int):
                diff = target - ch_num
                if diff <= 0:
                    active_pressures.append(f"🚨【危机已逾期 {abs(diff)} 章】「{cname}」（目标 ch_{target:03d}）：{cdesc}")
                elif diff <= 5:
                    active_pressures.append(f"⏳【危机倒计时仅剩 {diff} 章】「{cname}」（爆发目标 ch_{target:03d}）：{cdesc}")

    # 主线里程碑推进与逾期监测
    milestones = cur["timeline"].get("milestones", [])
    total_ms = len(milestones)
    achieved_ms = sum(1 for m in milestones if m.get("status") == "achieved")
    pending_ms = [m for m in milestones if m.get("status") == "pending"]
    pending_ms.sort(key=lambda m: m.get("target_ch", 9999))
    next_ms = pending_ms[0] if pending_ms else None

    for m in pending_ms:
        target = m.get("target_ch")
        mtitle = m.get("title", "")
        if isinstance(target, int):
            diff = target - ch_num
            if diff <= 0:
                active_pressures.append(f"🚩【主线里程碑已逾期】[{m.get('id')}]「{mtitle}」（目标 ch_{target:03d}）：尚未达成")
            elif diff <= 3:
                active_pressures.append(f"🚩【主线里程碑临近】[{m.get('id')}]「{mtitle}」（目标 ch_{target:03d}，还差 {diff} 章）")

    # 十章图书管理员巡检提示
    if ch_num > 0 and ch_num % 10 == 0:
        active_pressures.append(f"📚【图书管理员巡检关口】当前为第 {ch_num} 章（10章整数关口），建议调度 Librarian 巡查补漏")

    # 现场角色集合（主角 + 现场在场 + 细纲点名登场）
    scene_chars = list(dict.fromkeys(
        [proj.get("protagonist", "")] +
        list(cur["current"].get("present_characters") or [])
    ))
    if beats_files:
        try:
            b_text = beats_files[-1].read_text(encoding="utf-8", errors="replace")
            for ent in cur["entities"].get("entries", []):
                ename = ent.get("name")
                if ename and ename not in scene_chars:
                    if ename in b_text or any(a and a in b_text for a in ent.get("aliases", [])):
                        scene_chars.append(ename)
        except (ValueError, OSError):
            pass  # 实体账本损坏：现场名册退化为 current.present
    scene_chars = [c for c in scene_chars if c]

    # 信息差机锋 (Dramatic Irony)
    dramatic_irony = _extract_dramatic_irony(cur["lines"], scene_chars)

    # 现场人际张力拓扑 (Scene Tensions)
    scene_tensions = []
    try:
        full_G = graph.build_narrative_graph(book)
        scene_tensions = graph.extract_scene_tensions(full_G, scene_chars)
    except (ValueError, OSError):
        pass  # 拓扑构建失败（如状态损坏）：张力拓扑留空

    timings["workflow_momentum_ms"] = round((_time.perf_counter() - t_start) * 1000, 1)

    # 3. 老白读者催更雷达 (Critic Radar)
    critic_radar = _get_critic_radar(book, ch_num)

    # 4. 伏笔暗线分类雷达 (Lines Radar)
    lines_radar = _extract_lines_radar(cur["lines"], ch_num)

    # 4.5 确定性算法制导胶囊 (Algorithmic Guidance)
    algorithmic_guidance = get_algorithmic_guidance(book, ch_num)

    timings["radars_guidance_ms"] = round((_time.perf_counter() - t_start) * 1000, 1)

    # 5. 健康度与自愈处方 (Health & Remedies)
    remedies = checks.get_self_healing_remedies(book, ch_tok)
    timings["health_remedies_ms"] = round((_time.perf_counter() - t_start) * 1000, 1)
    if common.debug_enabled():
        common.debug(f"cockpit 分节耗时: {timings}（总 {timings['health_remedies_ms']}ms）")
    errors = [r for r in remedies if r["level"] == "error"]
    warnings = [r for r in remedies if r["level"] == "warning"]

    # 判定是否存在不可自动恢复的死锁
    deadlock_codes = {"project_missing", "project_corrupt"}
    is_deadlock = any(e["code"] in deadlock_codes or not e.get("can_auto_heal", True) for e in errors)

    briefing = {
        "schema": "novel-studio.cockpit/v1",
        "book": book.name,
        "title": proj.get("title", book.name),
        "target_chapter": ch_tok,
        "vol": vol,
        "workflow": {
            "chapter": ch_tok,
            "vol": vol,
            "current_stage": curr_stage,
            "status": status,
            "next_action": next_action,
            "stray_ahead_artifacts": stray
        },
        "dramatic_momentum": {
            "aftershock": aftershock,
            "active_pressures": active_pressures,
            "dramatic_irony": dramatic_irony,
            "scene_tensions": scene_tensions
        },
        "algorithmic_guidance": algorithmic_guidance,
        "critic_radar": critic_radar,
        "lines_radar": lines_radar,
        "milestones_progress": {
            "total": total_ms,
            "achieved": achieved_ms,
            "rate": f"{achieved_ms}/{total_ms}" if total_ms else "0/0",
            "next": next_ms
        },
        "health_and_remedies": {
            "ok": len(errors) == 0,
            "errors_count": len(errors),
            "warnings_count": len(warnings),
            "is_deadlock": is_deadlock,
            "requires_human_intervention": is_deadlock,
            "remedies": remedies
        }
    }
    if common.debug_enabled():
        briefing["debug_timing_ms"] = timings
    return briefing


def render_cockpit_terminal(briefing: dict[str, Any]) -> None:
    """在终端优雅渲染态势驾驶舱（支持 rich 彩色面板）。"""
    try:
        from rich.console import Console
        from rich.panel import Panel

        console = Console()

        wf = briefing["workflow"]
        dm = briefing["dramatic_momentum"]
        cr = briefing["critic_radar"]
        hr = briefing["health_and_remedies"]
        act = wf["next_action"]
        st = wf["status"]

        # 标题栏
        console.print()
        console.rule(f"[bold cyan]🚀 Novel Studio 态势驾驶舱 ｜ {briefing['title']} ({briefing['target_chapter']})[/bold cyan]")

        # 1. 工作流看板
        st_beats = "✅" if st["beats"] else "⭕"
        st_raw = "✅" if st["raw"] else "⭕"
        st_raw2 = "✅" if st.get("raw_v2") else "⭕"
        st_raw3 = "✅" if st.get("raw_v3") else "⭕"
        st_issues = "✅" if st.get("issues") else "⭕"
        st_final = "✅" if st["final"] else "⭕"
        st_prop = "✅" if st["proposal"] else "⭕"
        st_crit = "✅" if st["critic"] else "⭕"
        # 仲裁看板带状态后缀：缺报告 / 缺 front-matter / 硬矛盾未裁决 都要一眼可辨
        st_audit = "✅" if st.get("audit") else "⭕"
        _ast = st.get("audit_state", "")
        _audit_label = {"pass": "✅ 通过", "blocked": "🔴 硬矛盾未裁决",
                        "no_frontmatter": "❌ 缺 front-matter", "missing": "⭕ 缺报告",
                        "off": "➖ 已关闭 (audit_mode=off)"}.get(_ast, "⭕ 缺报告")
        st_sync = "✅" if st["synced"] else "⭕"

        # 工序状态按真实依赖链排列：1 → 2 → 3A → 3B → 4A/4B → 4C → 4D → 5
        status_line = (
            f"细纲 beats: {st_beats}  毛坯 raw_v1: {st_raw}  初修 raw_v2: {st_raw2}  "
            f"脱水 raw_v3: {st_raw3}\n"
            f"问题清单(4A): {st_issues}  定稿 final(4C): {st_final}  "
            f"事实提案(4D): {st_prop}  催更便签(4B): {st_crit}\n"
            f"事实仲裁: {_audit_label}  快照同步: {st_sync}"
        )

        wf_text = (
            f"[bold yellow]当前推进工序：[/bold yellow]{wf['current_stage']} ｜ [cyan]所属分卷：[/cyan]{wf['vol']}\n"
            f"[bold yellow]工序完成状态：[/bold yellow]{status_line}\n\n"
            f"[bold green]👉 下一步执行指令：[/bold green][bold white]{act['instruction']}[/bold white]\n"
            f"[dim]   建议操作/命令：{act['command']} ｜ 交付目标：{act['target_file']}[/dim]"
        )
        # 游离的超前工件显式提示，避免主控误以为指针跳章
        if wf.get("stray_ahead_artifacts"):
            wf_text += ("\n\n[bold yellow]⚠️ 游离超前工件（不参与指针推断）：[/bold yellow]"
                        + "、".join(wf["stray_ahead_artifacts"][:6])
                        + "\n[dim]   工序按「连续推进，绝不跳章」定位；如为误建请删除或补齐中间章。[/dim]")
        console.print(Panel(wf_text, title=f"🎯 [bold]工作流导航 ({briefing['target_chapter']})[/bold]", border_style="cyan"))

        # 2. 戏剧动力学看板
        dm_lines = []
        dm_lines.append(f"[bold red]⚡ 开篇承接余震：[/bold red]{dm['aftershock']}")
        if dm["active_pressures"]:
            dm_lines.append("\n[bold magenta]⏳ 悬顶危机倒计时：[/bold magenta]")
            for p in dm["active_pressures"]:
                dm_lines.append(f"  • {p}")
        if dm["dramatic_irony"]:
            dm_lines.append("\n[bold yellow]🎭 现场信息差机锋（AI写对手戏必用）：[/bold yellow]")
            for di in dm["dramatic_irony"]:
                dm_lines.append(f"  • {di}")
        if dm["scene_tensions"]:
            dm_lines.append("\n[bold blue]🔗 现场两两恩怨张力：[/bold blue]")
            for st_item in dm["scene_tensions"]:
                dm_lines.append(f"  • {st_item}")

        console.print(Panel("\n".join(dm_lines), title="⚡ [bold]戏剧动力学与现场张力态势[/bold]", border_style="magenta"))

        # 3. 催更雷达看板
        if cr.get("prev_chapter"):
            cr_lines = [
                f"[dim]来源便签：log/critic/{cr['prev_chapter']}.md[/dim]",
                f"[bold green]🌟 老白体感反馈：[/bold green]{cr.get('vibe', '暂无')}",
            ]
            if cr.get("format_warning"):
                cr_lines.append(f"[bold red]🚨 {cr['format_warning']}[/bold red]")
            if cr.get("continuity"):
                cr_lines.append(f"[bold red]🚩 连续性红旗：[/bold red]{cr['continuity']}")
            cr_lines.append(f"[bold cyan]🔥 下章迫切期待：[/bold cyan]{cr.get('anticipation', '暂无')}")
            cr_lines.append(f"[bold yellow]⚠️ 剧情避坑警示：[/bold yellow]{cr.get('taboos', '暂无')}")
            cr_text = "\n".join(cr_lines)
            console.print(Panel(cr_text, title=f"📡 [bold]老白催更雷达 (参考 {cr['prev_chapter']})[/bold]", border_style="yellow"))

        # 4. 伏笔暗线分类雷达看板
        lr = briefing.get("lines_radar", {})
        if lr:
            lr_lines = []
            stats = lr.get("stats", {})
            lr_lines.append(
                f"[dim]伏笔配额：活跃伏笔 {stats.get('active_foreshadows_count', 0)}/8 条 ｜ 跨卷长线 {stats.get('longline_foreshadows_count', 0)}/5 条[/dim]"
            )
            if lr.get("imminent"):
                lr_lines.append("\n[bold red]🔥 即时临界短线（本章及未来3章紧迫）：[/bold red]")
                for item in lr["imminent"]:
                    lr_lines.append(f"  • {item}")
            if lr.get("dormant_warnings"):
                lr_lines.append("\n[bold yellow]💤 沉寂暗线预警（>=10章未提，谨防烂尾吃书）：[/bold yellow]")
                for item in lr["dormant_warnings"]:
                    lr_lines.append(f"  • {item}")
            if lr.get("volume_mid"):
                lr_lines.append("\n[bold cyan]🎯 卷内主干中线（本卷内有序推进）：[/bold cyan]")
                for item in lr["volume_mid"]:
                    lr_lines.append(f"  • {item}")
            if lr.get("epic_longline"):
                lr_lines.append("\n[bold magenta]🌌 跨卷史诗长线（战略暗线守望）：[/bold magenta]")
                for item in lr["epic_longline"]:
                    lr_lines.append(f"  • {item}")

            console.print(Panel("\n".join(lr_lines), title="🕸️ [bold]伏笔暗线分类雷达 (Lines Radar)[/bold]", border_style="blue"))

        # 4.5 确定性算法制导胶囊
        ag = briefing.get("algorithmic_guidance", [])
        if ag:
            ag_text = "\n".join(f"  • {item}" for item in ag)
            console.print(Panel(ag_text, title="⚙️ [bold]确定性算法制导胶囊 (Algorithmic Guidance)[/bold]", border_style="cyan"))

        # 5. 健康度与自愈处方
        if hr["ok"]:
            border_col = "green"
            if not hr["warnings_count"]:
                health_text = "[bold green]✅ 全书事实与因果逻辑体检 100% 达标，无任何报错或警告！[/bold green]"
            else:
                lines = [
                    "[bold green]✅ 系统工程与核心事实体检完全达标（阻断性错误: 0）！[/bold green]",
                    f"[dim]📢 检出 {hr['warnings_count']} 项长线创作审美与宏观参考提示（非阻断，严禁停滞主流程去平账）：[/dim]\n"
                ]
                for r in hr["remedies"]:
                    if r["level"] == "warning":
                        lines.append(f"💭 【{r['code']}】 {r['msg']}")
                health_text = "\n".join(lines)
            console.print(Panel(health_text, title="🩺 [bold]剧情健康度舱（放行通过 · 阻断: 0）[/bold]", border_style=border_col))
        else:
            border_col = "red"
            lines = [f"[bold red]🚨 检出 {hr['errors_count']} 项阻断性错误（死锁: {'需人工介入' if hr['is_deadlock'] else '可按自愈指令修复'}）：[/bold red]\n"]
            for r in hr["remedies"]:
                if r["level"] == "error":
                    lines.append(f"❌ 【{r['code']}】 {r['msg']}")
                    if r.get("remedy"):
                        lines.append(f"   🚨 [修复方案] {r['remedy']}")
                    if r.get("action_command"):
                        lines.append(f"   💻 [自愈指令] {r['action_command']}")
            health_text = "\n".join(lines)
            console.print(Panel(health_text, title="🩺 [bold]剧情健康度与自愈处方舱（阻断拦截）[/bold]", border_style=border_col))
        console.print()

    except ImportError:
        # Fallback to plain text
        print(f"\n=== Novel Studio 态势驾驶舱: {briefing['title']} ({briefing['target_chapter']}) ===")
        print(f"当前推进工序：{briefing['workflow']['current_stage']}")
        print(f"下一步行动：{briefing['workflow']['next_action']['instruction']}")
        print(f"执行命令：{briefing['workflow']['next_action']['command']}")
        print(f"开篇余震：{briefing['dramatic_momentum']['aftershock']}")
        if briefing['dramatic_momentum']['active_pressures']:
            print("悬顶危机：")
            for p in briefing['dramatic_momentum']['active_pressures']:
                print(f"  - {p}")
        if briefing['dramatic_momentum']['dramatic_irony']:
            print("信息差机锋：")
            for di in briefing['dramatic_momentum']['dramatic_irony']:
                print(f"  - {di}")
        if briefing.get('lines_radar'):
            lr = briefing['lines_radar']
            print(f"伏笔雷达：即时临界 {len(lr.get('imminent', []))} 条，卷内主干 {len(lr.get('volume_mid', []))} 条，跨卷长线 {len(lr.get('epic_longline', []))} 条")
            for item in lr.get('imminent', []):
                print(f"  • {item}")
        print(f"体检状态：Errors {briefing['health_and_remedies']['errors_count']}, Warnings {briefing['health_and_remedies']['warnings_count']}")
        if briefing['health_and_remedies']['errors_count'] == 0:
            print("  ✅ 阻断性错误: 0，体检放行通过！warnings 均为长线参考，无需执行平账！")
        else:
            for r in briefing['health_and_remedies']['remedies']:
                if r["level"] == "error":
                    print(f"  ❌ [{r['code']}] {r['msg']}")
                    if r.get("remedy"):
                        print(f"     🚨 [修复方案] {r['remedy']}")
                    if r.get("action_command"):
                        print(f"     💻 [自愈指令] {r['action_command']}")
        print()
