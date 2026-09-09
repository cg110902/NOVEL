"""recall：知乎长篇小说“残酷四问” 0 Token 机械自证命令。

纯账本推导、零 LLM 开销，瞬间输出四大核心维度：
1. 主要人物各自知道什么（认知台账 + KNO 知情圈 + MIS 误解）
2. 绝对不能修改的不可逆事实（locked 第七表 + 阵亡/退役实体）
3. 哪些伏笔仍未兑现（未回收线索 + 危机时钟 + 主线里程碑）
4. 下一章允许改变与绝对不许触碰的边界（红线约束与排产推荐）
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import common, evidence, state
from ._shared import _norm_ch, ws_gate, ws_gate_code

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    _HAS_RICH = True
    console = Console()
except ImportError:
    _HAS_RICH = False
    console = None


def run_recall(book: Path, ch: str | None = None) -> dict:
    """计算知乎残酷四问的确定性自证数据包。"""
    cur_num = common.chapter_token_to_num(ch) if ch else (common.latest_chapter_number(book, "final") or 1)
    tok = f"ch_{cur_num:03d}"
    next_tok = f"ch_{cur_num + 1:03d}"

    # 加载状态表
    try:
        cur_st = state.load_state(book, "current")
    except (ValueError, FileNotFoundError):
        cur_st = {}
    try:
        ents_st = state.load_state(book, "entities").get("entries", [])
    except (ValueError, FileNotFoundError):
        ents_st = []
    try:
        lines_st = state.load_state(book, "lines")
    except (ValueError, FileNotFoundError):
        lines_st = {}
    try:
        tl_st = state.load_state(book, "timeline")
    except (ValueError, FileNotFoundError):
        tl_st = {}
    try:
        led_st = state.load_state(book, "ledger")
    except (ValueError, FileNotFoundError):
        led_st = {}
    try:
        locked_st = state.load_state(book, "locked").get("entries", [])
    except (ValueError, FileNotFoundError):
        locked_st = []
    try:
        cog_st = state.load_state(book, "cognition").get("entries", [])
    except (ValueError, FileNotFoundError):
        cog_st = []

    proj = common.load_json(book / "project.json", default={}) or {}
    protagonist = str(proj.get("protagonist", "")).strip()
    lookup = evidence.entity_lookup(book)

    # -----------------------------------------------------------------------
    # 问 1：主要人物各自知道什么
    # -----------------------------------------------------------------------
    # 确定要展示的关键角色：主角 + 当前在场角色 + cognition中出现过的角色 + 活跃person实体
    target_chars = []
    if protagonist:
        target_chars.append(protagonist)
    for p in (cur_st.get("present_characters") or []):
        if p and p not in target_chars:
            target_chars.append(p)
    for c in cog_st:
        char = c.get("character")
        if char and char not in target_chars:
            target_chars.append(char)
    for e in ents_st:
        if e.get("type") == "person" and e.get("status", "active") == "active":
            nm = e.get("name")
            if nm and nm not in target_chars and len(target_chars) < 8:
                target_chars.append(nm)

    cognition_report = {}
    for char in target_chars:
        names = lookup.get(char, [char])
        def _match(nm_field: str | None) -> bool:
            if not nm_field:
                return False
            return any(nm and (nm == nm_field or nm in nm_field or nm_field in nm) for nm in names)

        # 1) 已知事实与目击事件
        char_cogs = [c for c in cog_st if _match(c.get("character"))]
        facts = [
            {"content": c.get("content"), "since_ch": c.get("since_ch"), "quote": c.get("quote")}
            for c in char_cogs if c.get("kind") in ("fact", "secret_known")
        ]

        # 2) 知晓机密（KNO holders）
        secrets_held = [
            {"id": k.get("id"), "secret": k.get("secret"), "since_ch": k.get("plant_ch")}
            for k in lines_st.get("knowledge", [])
            if any(_match(h) for h in (k.get("holders") or []))
        ]

        # 3) 怀疑与疑点
        suspicions = [
            {"content": c.get("content"), "since_ch": c.get("since_ch"), "quote": c.get("quote")}
            for c in char_cogs if c.get("kind") == "suspicion"
        ]

        # 4) 涉及误会
        misunderstandings = [
            {"content": c.get("content"), "since_ch": c.get("since_ch"), "quote": c.get("quote")}
            for c in char_cogs if c.get("kind") == "misunderstanding"
        ]
        for m in lines_st.get("misunderstandings", []):
            if str(m.get("status", "")).lower() != "resolved" and _match(m.get("parties")):
                misunderstandings.append({
                    "id": m.get("id"),
                    "content": m.get("content") or m.get("parties"),
                    "target_ch": m.get("target_ch")
                })

        # 5) 严禁知晓的未公开机密（非 holder）
        unknown_secrets = [
            {"id": k.get("id"), "secret": k.get("secret")[:30]}
            for k in lines_st.get("knowledge", [])
            if str(k.get("status", "")).lower() != "revealed"
            and not any(_match(h) for h in (k.get("holders") or []))
        ]

        cognition_report[char] = {
            "known_facts": facts[:6],
            "secrets_held": secrets_held[:5],
            "suspicions": suspicions[:5],
            "misunderstandings": misunderstandings[:5],
            "unknown_secrets_boundary": unknown_secrets[:6],
        }

    # -----------------------------------------------------------------------
    # 问 2：哪些事实绝对不能修改
    # -----------------------------------------------------------------------
    deceased_entities = [
        {"name": e.get("name"), "type": e.get("type"), "summary": e.get("summary")}
        for e in ents_st if e.get("life_status") == "deceased"
    ]
    retired_entities = [
        {"name": e.get("name"), "type": e.get("type"), "summary": e.get("summary")}
        for e in ents_st if e.get("status") == "retired"
    ]
    locked_items = [
        {
            "id": lk.get("id"),
            "kind": lk.get("kind"),
            "fact": lk.get("fact"),
            "since_ch": lk.get("since_ch"),
            "quote": lk.get("quote"),
            "note": lk.get("note"),
        }
        for lk in locked_st
    ]

    # R0：桥接双伤情通道——current.injury（主角旧口径）+ entities[].injury_level（逐实体）
    entity_injuries = [
        {"name": e.get("name"), "injury_level": e.get("injury_level"),
         "injury_desc": e.get("injury_desc", "")}
        for e in ents_st
        if type(e.get("injury_level")) is int and e["injury_level"] > 0
    ]
    irreversible_facts = {
        "locked_rules_and_events": locked_items,
        "deceased_characters": deceased_entities,
        "retired_entities": retired_entities,
        "permanent_injury": cur_st.get("injury") if cur_st.get("injury") not in ("", "完好", None) else None,
        "entity_injuries": entity_injuries,
    }

    # -----------------------------------------------------------------------
    # 问 3：哪些伏笔仍未兑现
    # -----------------------------------------------------------------------
    open_foreshadows = [
        {
            "id": f.get("id"),
            "name": f.get("name"),
            "plant_ch": f.get("plant_ch"),
            "target_ch": f.get("target_ch"),
            "weight": f.get("weight", 1),
            "overdue": isinstance(f.get("target_ch"), int) and f["target_ch"] <= cur_num,
        }
        for f in lines_st.get("foreshadows", [])
        if str(f.get("status", "")).lower() != "resolved"
    ]
    open_foreshadows.sort(key=lambda x: (0 if x["overdue"] else 1, x["target_ch"] if isinstance(x["target_ch"], int) else 9999))

    open_mis = [
        {
            "id": m.get("id"),
            "parties": m.get("parties"),
            "content": m.get("content"),
            "target_ch": m.get("target_ch"),
            "level": m.get("level", 1),
            "overdue": isinstance(m.get("target_ch"), int) and m["target_ch"] <= cur_num,
        }
        for m in lines_st.get("misunderstandings", [])
        if str(m.get("status", "")).lower() != "resolved"
    ]

    open_kno = [
        {
            "id": k.get("id"),
            "secret": k.get("secret"),
            "holders": k.get("holders", []),
            "target_ch": k.get("target_ch"),
            "overdue": isinstance(k.get("target_ch"), int) and k["target_ch"] <= cur_num,
        }
        for k in lines_st.get("knowledge", [])
        if str(k.get("status", "")).lower() != "revealed"
    ]

    active_clocks = [
        {
            "name": c.get("name"),
            "target_ch": c.get("target_ch"),
            "remaining_chapters": (c.get("target_ch") - cur_num) if isinstance(c.get("target_ch"), int) else None,
            "desc": c.get("desc"),
        }
        for c in (tl_st.get("clocks") or [])
        if str(c.get("status", "")).lower() == "active"
    ]

    pending_milestones = [
        {
            "id": ms.get("id"),
            "title": ms.get("title"),
            "target_ch": ms.get("target_ch"),
            "overdue": isinstance(ms.get("target_ch"), int) and ms["target_ch"] <= cur_num,
            "desc": ms.get("desc"),
        }
        for ms in (tl_st.get("milestones") or [])
        if str(ms.get("status", "")).lower() == "pending"
    ]

    pending_lines = {
        "foreshadows": open_foreshadows,
        "misunderstandings": open_mis,
        "knowledge": open_kno,
        "clocks": active_clocks,
        "milestones": pending_milestones,
    }

    # -----------------------------------------------------------------------
    # 问 4：下一章允许改变什么 / 绝对不许触碰什么
    # -----------------------------------------------------------------------
    due_lines = [
        item["id"] + f"（{item.get('name') or item.get('content') or item.get('secret')}）"
        for item in (open_foreshadows + open_mis + open_kno)
        if item.get("target_ch") in (cur_num, cur_num + 1)
    ]
    due_clocks = [c["name"] for c in active_clocks if c.get("target_ch") == cur_num + 1]
    due_milestones = [m["title"] for m in pending_milestones if m.get("target_ch") == cur_num + 1]
    pool_balances = {
        pid: f"{p.get('current', 0)} {p.get('unit', '')}"
        for pid, p in (led_st.get("pools") or {}).items()
    }

    strictly_forbidden = [
        f"严禁让已阵亡实体 [{', '.join(e['name'] for e in deceased_entities) or '无'}] 作为在世主体登场行动",
        "严禁推翻或违背 locked 台账所登记的既成事实",
        "严禁非 holders 角色知晓或提及未公开机密（防止上帝视角穿帮）",
        f"严禁透支账面资产（当前余额：{', '.join(f'{k}: {v}' for k, v in pool_balances.items()) or '无'}）",
    ]

    next_boundaries = {
        "target_chapter": next_tok,
        "allowed_and_encouraged": {
            "due_lines_for_action": due_lines or ["按大纲推进新剧情或布局新线"],
            "due_clocks": due_clocks,
            "due_milestones": due_milestones,
            "available_resources": pool_balances,
            "scene_movement": "允许根据细纲更新时地快照、人物伤势、心理走向与在场阵容",
        },
        "strictly_forbidden": strictly_forbidden,
    }

    return {
        "kind": "recall",
        "chapter": tok,
        "next_chapter": next_tok,
        "story_day": cur_st.get("time_day"),
        "character_cognition": cognition_report,
        "irreversible_facts": irreversible_facts,
        "pending_lines": pending_lines,
        "next_chapter_boundaries": next_boundaries,
    }


def render_recall_markdown(d: dict) -> str:
    """将 recall 数据包渲染为人性化 Markdown 报告。"""
    ch = d["chapter"]
    next_ch = d["next_chapter"]
    cog = d["character_cognition"]
    irrev = d["irreversible_facts"]
    lines = d["pending_lines"]
    bound = d["next_chapter_boundaries"]

    _sd = d.get("story_day")
    L = [
        f"# 🧭 [知乎长篇残酷四问 · 机械自证单] 锚定章节: {ch} ｜ 面向下一章: {next_ch}"
        + (f" ｜ 故事第 {_sd} 日" if type(_sd) is int else ""),
        "<!-- 本报告由确定性引擎基于 state/ 十一表真值 0 Token 瞬间推导，杜绝吃书与上帝视角。 -->",
        "",
        "## ❓ 问一：主要人物各自知道什么？（认知台账与知情圈）",
    ]
    for char, info in cog.items():
        L.append(f"### 👤 角色：**{char}**")
        if info["known_facts"]:
            L.append("- **确知事实**：")
            for f in info["known_facts"]:
                L.append(f"  - {f['content']}（出处: {f.get('since_ch', '前文')}）")
        else:
            L.append("- **确知事实**：（无特殊登记事实）")

        if info["secrets_held"]:
            L.append("- **知晓机密 (KNO)**：")
            for s in info["secrets_held"]:
                L.append(f"  - [{s['id']}] {s['secret']}")

        if info["suspicions"]:
            L.append("- **心中疑窦 (Suspicion)**：")
            for sp in info["suspicions"]:
                L.append(f"  - {sp['content']}")

        if info["misunderstandings"]:
            L.append("- **身陷误解 (Misunderstanding)**：")
            for mis in info["misunderstandings"]:
                L.append(f"  - {mis['content']}")

        if info["unknown_secrets_boundary"]:
            L.append("- ⛔ **知情红线（该角色绝对不知道的机密）**：")
            for unk in info["unknown_secrets_boundary"]:
                L.append(f"  - [{unk['id']}] {unk['secret']}...")
        L.append("")

    L.append("## ❓ 问二：哪些事实绝对不能修改？（不可逆底座与阵亡名单）")
    if irrev["locked_rules_and_events"]:
        L.append("### 🔒 不可逆台账 (LOCK)")
        for lk in irrev["locked_rules_and_events"]:
            L.append(f"- **[{lk['id']}] ({lk['kind']})** {lk['fact']}（始于 {lk.get('since_ch','?')}）")
    else:
        L.append("- 🔒 **不可逆台账**：（暂无条目）")

    if irrev["deceased_characters"]:
        L.append("### 💀 已阵亡/死亡实体")
        for dc in irrev["deceased_characters"]:
            L.append(f"- **{dc['name']}** ({dc.get('type','person')}): {dc.get('summary','')}")

    if irrev["retired_entities"]:
        L.append("### 📦 已退役/损毁实体")
        for re_ent in irrev["retired_entities"]:
            L.append(f"- **{re_ent['name']}**: {re_ent.get('summary','')}")

    if irrev.get("permanent_injury"):
        L.append(f"- 🩸 **伤残指征**：{irrev['permanent_injury']}")
    for inj in irrev.get("entity_injuries") or []:
        L.append(f"- 🩹 **{inj['name']}** 伤势 Lv{inj['injury_level']}"
                 + (f"：{inj['injury_desc']}" if inj.get("injury_desc") else ""))
    L.append("")

    L.append("## ❓ 问三：哪些伏笔仍未兑现？（未结算线索与时钟雷达）")
    L.append(f"- **未回收伏笔 ({len(lines['foreshadows'])} 条)**：")
    for f in lines["foreshadows"][:8]:
        overdue_str = " 🔴 [已逾期]" if f["overdue"] else ""
        # target_ch 允许 "longline" 字符串——:03d 仅适用于整数章号，否则文本模式崩溃
        tgt = f.get("target_ch")
        tgt_str = f"ch_{tgt:03d}" if isinstance(tgt, int) else str(tgt)
        L.append(f"  - [{f['id']}] {f['name']}（目标: {tgt_str}{overdue_str}）")
    if len(lines["foreshadows"]) > 8:
        L.append(f"  - ... 其余 {len(lines['foreshadows']) - 8} 条略")

    if lines["clocks"]:
        L.append("- **悬顶危机时钟 (Clocks)**：")
        for clk in lines["clocks"]:
            rem = f"剩余 {clk['remaining_chapters']} 章" if clk['remaining_chapters'] is not None else "倒计时中"
            L.append(f"  - ⏰ **{clk['name']}**（目标 ch_{clk.get('target_ch'):03d} ｜ {rem}）：{clk.get('desc','')}")

    if lines["milestones"]:
        L.append("- **主线里程碑航标 (Milestones)**：")
        for ms in lines["milestones"]:
            overdue_str = " 🔴 [逾期未达成]" if ms["overdue"] else ""
            L.append(f"  - 🚩 **[{ms['id']}] {ms['title']}**（目标 ch_{ms.get('target_ch'):03d}{overdue_str}）")
    L.append("")

    L.append(f"## ❓ 问四：下一章 ({next_ch}) 允许改变什么？禁止触碰什么？")
    L.append("### ✅ 允许与建议改变（剧情突破口）")
    for da in bound["allowed_and_encouraged"]["due_lines_for_action"]:
        L.append(f"- 🎯 **应答动作**：{da}")
    if bound["allowed_and_encouraged"]["due_clocks"]:
        for dc in bound["allowed_and_encouraged"]["due_clocks"]:
            L.append(f"- ⏰ **危机引爆**：时钟「{dc}」即将到期")
    if bound["allowed_and_encouraged"]["due_milestones"]:
        for dm in bound["allowed_and_encouraged"]["due_milestones"]:
            L.append(f"- 🚩 **主线突破**：里程碑「{dm}」排期达成")
    if bound["allowed_and_encouraged"]["available_resources"]:
        res_str = " ｜ ".join(f"{k}: {v}" for k, v in bound["allowed_and_encouraged"]["available_resources"].items())
        L.append(f"- 💰 **账面资产可用额**：{res_str}")

    L.append("")
    L.append("### ❌ 禁止触碰（叙事红线）")
    for fb in bound["strictly_forbidden"]:
        L.append(f"- 🚫 {fb}")

    return "\n".join(L) + "\n"


def cmd_recall(args) -> int:
    """CLI 执行入口：studio recall [ch_XXX] [--json]。"""
    book = ws_gate(args)
    if book is None:
        return ws_gate_code()
    ch = getattr(args, "chapter", None)
    if ch:
        ch = _norm_ch(ch)

    payload = run_recall(book, ch)
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    md_content = render_recall_markdown(payload)
    if _HAS_RICH and console:
        console.print(Panel(
            Markdown(md_content),
            title=f"[bold cyan]🧭 [长篇灵魂四问自证] {payload['chapter']} ➔ {payload['next_chapter']}[/bold cyan]",
            border_style="green",
            padding=(1, 2)
        ))
    else:
        print(md_content)
    return 0
