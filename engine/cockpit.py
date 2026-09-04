"""cockpit：主控态势驾驶舱与自愈雷达（专供 AI / 主控秒懂全链路态势与自愈决策）。

功能矩阵：
1. workflow：精准定位当前章节与活跃工序 Stage，提供 0 歧义的下一步调度指令与标准派发参数。
2. dramatic_momentum：计算戏剧动力学（承接余震 aftershock、悬顶危机 active_pressures、现场信息差机锋 dramatic_irony、两两张力网络 scene_tensions）。
3. health_and_remedies：全书事实核验、确定性断言体检与具备可操作性的自愈处方（Remedies）。
4. critic_radar：直接透视上一章读者催更便签（最想看/最怕踩），免去主控翻读外部文件。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from . import checks, common, evidence, graph, state


def _infer_active_chapter(book: Path) -> str:
    """自动推断当前最需要推进或处理的章节编号。"""
    ch_nums = set()
    for area in ("beats", "raw", "final"):
        for f in common.find_chapter_files(book, area):
            num = common.chapter_number_from_name(f.name)
            if num:
                ch_nums.add(num)
    inbox = book / "state" / "inbox"
    if inbox.is_dir():
        for p in inbox.glob("ch_*.json"):
            num = common.chapter_number_from_name(p.name)
            if num:
                ch_nums.add(num)

    synopsis = state.load_state(book, "synopsis")
    syn = synopsis.get("chapters", {})
    if isinstance(syn, dict):
        synced_chapters = set(syn.keys())
    elif isinstance(syn, list):
        synced_chapters = {c.get("chapter") for c in syn if isinstance(c, dict)}
    else:
        synced_chapters = set()

    for sc in synced_chapters:
        num = common.chapter_token_to_num(sc)
        if num:
            ch_nums.add(num)

    if not ch_nums:
        return "ch_001"

    max_ch = max(ch_nums)
    ch_tok = f"ch_{max_ch:03d}"

    if ch_tok in synced_chapters:
        # 已定稿封存，推进下一章
        return f"ch_{max_ch + 1:03d}"
    return ch_tok


def _find_chapter_vol(book: Path, ch: str) -> str:
    """确定章节所属分卷目录名称。"""
    ch_num = common.chapter_token_to_num(ch) or 1
    beats_files = common.find_chapter_files(book, "beats", ch)
    if beats_files:
        try:
            rel_parts = beats_files[-1].relative_to(book / "outlines").parts
            if rel_parts and rel_parts[0].startswith("vol_"):
                return rel_parts[0]
        except Exception:
            pass
    for vdir in sorted((book / "outlines").glob("vol_*")):
        outline_file = vdir / "outline.md"
        if outline_file.is_file():
            try:
                otext = outline_file.read_text(encoding="utf-8", errors="ignore")
                m = re.findall(r"\bch_?(\d+)\b", otext)
                if m and int(m[0]) <= ch_num <= int(m[-1]):
                    return vdir.name
            except Exception:
                pass
    return f"vol_{(ch_num - 1) // 50 + 1:02d}"


def _get_critic_radar(book: Path, ch_num: int) -> dict[str, str]:
    """读取上一章读者催更便签，提炼体感、期待与避坑点。"""
    radar = {"prev_chapter": "", "vibe": "", "anticipation": "", "taboos": ""}
    if ch_num <= 1:
        return radar

    prev_ch = f"ch_{ch_num - 1:03d}"
    radar["prev_chapter"] = prev_ch
    critic_path = book / "log" / "critic" / f"{prev_ch}.md"
    if not critic_path.is_file():
        return radar

    try:
        text = critic_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line_str = line.strip()
            if "本章体感" in line_str:
                radar["vibe"] = re.sub(r"^[-*#\s]*\**本章体感\**[:：\s]*", "", line_str)
            elif "最想看" in line_str:
                radar["anticipation"] = re.sub(r"^[-*#\s]*\**[下当]章最想看[什么]*\**[:：\s]*", "", line_str)
            elif "最怕踩" in line_str or "避坑" in line_str:
                radar["taboos"] = re.sub(r"^[-*#\s]*\**[下当]章最怕踩[什么]*\**[:：\s]*", "", line_str)
    except Exception:
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
        note = str(k.get("note", "保密中"))
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


def _compute_character_dormancy(book: Path, current_ch: int) -> list[str]:
    """滑动窗口计算核心角色沉寂预警（>=3章未露面或未登场）。"""
    alerts = []
    if current_ch <= 2:
        return alerts

    char_files = list((book / "characters").glob("*.md"))
    char_names = [f.stem for f in char_files if not f.stem.startswith(".")]

    try:
        entries = state.load_state(book, "entities").get("entries", [])
        for edata in entries:
            if edata.get("type") == "person":
                cname = edata.get("name")
                if cname and cname not in char_names:
                    char_names.append(cname)
    except Exception:
        pass

    char_last_seen = {c: 0 for c in char_names}

    for ch_idx in range(1, current_ch):
        ch_tok = f"ch_{ch_idx:03d}"
        final_files = list((book / "manuscript").glob(f"*/final/{ch_tok}.md"))
        if not final_files:
            continue
        text = final_files[0].read_text(encoding="utf-8", errors="ignore")
        for c in char_names:
            if c in text:
                char_last_seen[c] = ch_idx

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


def _compute_dead_inventory(book: Path, current_ch: int) -> list[str]:
    """背包资产周转与沉睡道具/词条雷达。"""
    alerts = []
    if current_ch <= 3:
        return alerts

    try:
        entries = state.load_state(book, "entities").get("entries", [])
        for edata in entries:
            if edata.get("type") == "item":
                iname = edata.get("name")
                if iname and iname not in ("我悟了，你随意",):
                    last_seen_ch = 0
                    for ch_idx in range(1, current_ch):
                        ch_tok = f"ch_{ch_idx:03d}"
                        final_files = list((book / "manuscript").glob(f"*/final/{ch_tok}.md"))
                        if final_files:
                            text = final_files[0].read_text(encoding="utf-8", errors="ignore")
                            if iname in text:
                                last_seen_ch = ch_idx
                    if last_seen_ch > 0 and (current_ch - 1 - last_seen_ch) >= 3:
                        alerts.append(f"🎒 [沉睡道具提醒] 道具/词条「{iname}」已连续 {current_ch - 1 - last_seen_ch} 章未登场(上次使用: ch_{last_seen_ch:03d})，可考虑在后续战力推演、融合升华或剧情破局时调用。")
    except Exception:
        pass

    return alerts


def get_algorithmic_guidance(book: Path, current_ch: int) -> list[str]:
    """聚合所有确定性算法制导胶囊。"""
    guidance = []
    guidance.extend(_compute_character_dormancy(book, current_ch))
    guidance.extend(_compute_tension_rhythm(book, current_ch))
    guidance.extend(_compute_dead_inventory(book, current_ch))
    return guidance


def build_cockpit_briefing(book: Path, ch: str | None = None) -> dict[str, Any]:
    """计算并构建主控态势驾驶舱完整数据模型。"""
    proj = common.load_json(book / "project.json", default={}) or {}
    target_ch = ch if ch else _infer_active_chapter(book)
    ch_num = common.chapter_token_to_num(target_ch) or 1
    ch_tok = f"ch_{ch_num:03d}"
    vol = _find_chapter_vol(book, ch_tok)

    cur = {key: state.load_state(book, key) for key in ("current", "entities", "lines", "synopsis", "timeline")}

    # 1. 确定工作流与工序状态
    beats_files = common.find_chapter_files(book, "beats", ch_tok)
    raw_files = common.find_chapter_files(book, "raw", ch_tok)
    final_files = common.find_chapter_files(book, "final", ch_tok)
    inbox_file = (book / "state" / "inbox" / f"{ch_tok}.json").is_file() or (book / "state" / "inbox" / "processed" / f"{ch_tok}.json").is_file()
    critic_file = (book / "log" / "critic" / f"{ch_tok}.md").is_file()

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
        "raw": bool(raw_files),
        "final": bool(final_files),
        "proposal": inbox_file,
        "critic": critic_file,
        "synced": is_synced,
    }

    # 判定当前 Stage 与下一步行动指令
    if is_synced:
        curr_stage = "Completed (当章已封存)"
        next_ch = f"ch_{ch_num + 1:03d}"
        next_action = {
            "actor": "Director",
            "stage": "Stage 1",
            "instruction": f"当章已全部完工并同步封存，推进至下一章 {next_ch}",
            "command": f"python studio.py beats new {next_ch} --write",
            "target_file": f"outlines/{vol}/beats/{next_ch}.md"
        }
    elif not status["beats"]:
        curr_stage = "Stage 1 (细纲构思)"
        next_action = {
            "actor": "Director",
            "stage": "Stage 1",
            "instruction": "吸纳上一章读者催更便签与戏剧余震，生成并确认细纲任务书落盘",
            "command": f"python studio.py beats new {ch_tok} --write",
            "target_file": f"outlines/{vol}/beats/{ch_tok}.md"
        }
    elif not status["raw"]:
        curr_stage = "Stage 2 (初稿起草)"
        next_action = {
            "actor": "Drafter",
            "stage": "Stage 2",
            "instruction": "向起草员 Drafter 下达 Stage 2 标准工序派发令，放飞算力展开3大场景",
            "command": f"python studio.py pack {ch_tok} --full",
            "target_file": f"manuscript/{vol}/raw/{ch_tok}_v1.md"
        }
    elif not status["final"]:
        curr_stage = "Stage 3 (文学重塑)"
        next_action = {
            "actor": "Editor",
            "stage": "Stage 3",
            "instruction": "向精修师 Editor 下达 Stage 3 标准工序派发令，切除解释性反刍，成型定稿",
            "command": f"view_file manuscript/{vol}/raw/{ch_tok}_v1.md",
            "target_file": f"manuscript/{vol}/final/{ch_tok}.md"
        }
    elif not status["proposal"] or not status["critic"]:
        curr_stage = "Stage 4 (双轨审计与催更)"
        missing = []
        if not status["proposal"]:
            missing.append("Reader (轨A-事实提案)")
        if not status["critic"]:
            missing.append("Critic (轨B-老白催更便签)")

        if not status["proposal"] and not status["critic"]:
            actor = "Reader & Critic (双轨并发)"
            target_f = f"state/inbox/{ch_tok}.json | log/critic/{ch_tok}.md"
            instruct = "在单次 invoke_subagent 调用中并发唤起 Reader (事实提案) 与 Critic (催更便签)"
        elif not status["proposal"]:
            actor = "Reader"
            target_f = f"state/inbox/{ch_tok}.json"
            instruct = "向审计员 Reader 下达 Stage 4A 标准工序派发令，交付事实提案 JSON"
        else:
            actor = "Critic"
            target_f = f"log/critic/{ch_tok}.md"
            instruct = "向催更员 Critic 下达 Stage 4B 标准工序派发令，交付老白催更便签"

        next_action = {
            "actor": actor,
            "stage": "Stage 4",
            "instruction": instruct,
            "command": f"view_file manuscript/{vol}/final/{ch_tok}.md",
            "target_file": target_f
        }
    else:
        curr_stage = "Stage 5 (状态同步与快照)"
        next_action = {
            "actor": "Director",
            "stage": "Stage 5",
            "instruction": "主控审定 Reader 提案，一键执行 sync 原子合并账目并封存快照",
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
        except Exception:
            pass
    scene_chars = [c for c in scene_chars if c]

    # 信息差机锋 (Dramatic Irony)
    dramatic_irony = _extract_dramatic_irony(cur["lines"], scene_chars)

    # 现场人际张力拓扑 (Scene Tensions)
    scene_tensions = []
    try:
        full_G = graph.build_narrative_graph(book)
        scene_tensions = graph.extract_scene_tensions(full_G, scene_chars)
    except Exception:
        pass

    # 3. 老白读者催更雷达 (Critic Radar)
    critic_radar = _get_critic_radar(book, ch_num)

    # 4. 伏笔暗线分类雷达 (Lines Radar)
    lines_radar = _extract_lines_radar(cur["lines"], ch_num)

    # 4.5 确定性算法制导胶囊 (Algorithmic Guidance)
    algorithmic_guidance = get_algorithmic_guidance(book, ch_num)

    # 5. 健康度与自愈处方 (Health & Remedies)
    remedies = checks.get_self_healing_remedies(book, ch_tok)
    errors = [r for r in remedies if r["level"] == "error"]
    warnings = [r for r in remedies if r["level"] == "warning"]

    # 判定是否存在不可自动恢复的死锁
    deadlock_codes = {"project_missing", "project_corrupt"}
    is_deadlock = any(e["code"] in deadlock_codes or not e.get("can_auto_heal", True) for e in errors)

    return {
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
            "next_action": next_action
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
        "health_and_remedies": {
            "ok": len(errors) == 0,
            "errors_count": len(errors),
            "warnings_count": len(warnings),
            "is_deadlock": is_deadlock,
            "requires_human_intervention": is_deadlock,
            "remedies": remedies
        }
    }


def render_cockpit_terminal(briefing: dict[str, Any]) -> None:
    """在终端优雅渲染态势驾驶舱（支持 rich 彩色面板）。"""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

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
        st_final = "✅" if st["final"] else "⭕"
        st_prop = "✅" if st["proposal"] else "⭕"
        st_crit = "✅" if st["critic"] else "⭕"
        st_sync = "✅" if st["synced"] else "⭕"

        status_line = (
            f"细纲 beats: {st_beats}  初稿 raw: {st_raw}  定稿 final: {st_final}  "
            f"事实提案: {st_prop}  催更便签: {st_crit}  快照同步: {st_sync}"
        )

        wf_text = (
            f"[bold yellow]当前推进工序：[/bold yellow]{wf['current_stage']} ｜ [cyan]所属分卷：[/cyan]{wf['vol']}\n"
            f"[bold yellow]工序完成状态：[/bold yellow]{status_line}\n\n"
            f"[bold green]👉 下一步执行指令：[/bold green][bold white]{act['instruction']}[/bold white]\n"
            f"[dim]   建议操作/命令：{act['command']} ｜ 交付目标：{act['target_file']}[/dim]"
        )
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
            cr_text = (
                f"[dim]来源便签：log/critic/{cr['prev_chapter']}.md[/dim]\n"
                f"[bold green]🌟 老白体感反馈：[/bold green]{cr.get('vibe', '暂无')}\n"
                f"[bold cyan]🔥 下章迫切期待：[/bold cyan]{cr.get('anticipation', '暂无')}\n"
                f"[bold yellow]⚠️ 剧情避坑警示：[/bold yellow]{cr.get('taboos', '暂无')}"
            )
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
        if hr["ok"] and not hr["warnings_count"]:
            health_text = "[bold green]✅ 全书事实与因果逻辑体检 100% 达标，无任何报错或警告！[/bold green]"
            border_col = "green"
        else:
            border_col = "red" if not hr["ok"] else "yellow"
            lines = [f"[bold]体检概况：[/bold]Errors: {hr['errors_count']}  Warnings: {hr['warnings_count']}  "
                     f"死锁阻断: {'🚨 是(需人类)' if hr['is_deadlock'] else '🟢 否(主控可自愈)'}\n"]
            for r in hr["remedies"]:
                icon = "❌" if r["level"] == "error" else "⚠️"
                lines.append(f"{icon} [{r['code']}] {r['msg']}")
                if r.get("remedy"):
                    lines.append(f"   💡 [自愈方案] {r['remedy']}")
                if r.get("action_command"):
                    lines.append(f"   💻 [自愈指令] {r['action_command']}")
            health_text = "\n".join(lines)

        console.print(Panel(health_text, title="🩺 [bold]剧情健康度与自愈处方舱[/bold]", border_style=border_col))
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
        for r in briefing['health_and_remedies']['remedies']:
            print(f"  [{r['level']}] {r['msg']} -> 自愈: {r.get('remedy')}")
        print()
