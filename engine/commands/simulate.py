"""simulate：Stage 1 主控（Director）剧情推演沙盒与参谋件。

两大核心能力：
1. `simulate impact`：因果链影响测算（若角色死亡/道具损毁/机密揭露，有哪些伏笔、主线里程碑与人际关系将被波及）
2. `simulate branch`：走向假说沙盘（为下一章生成 2~3 条互相隔离的走向方案至 log/branches/ch_XXX.md，绝不污染正史）
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import common, evidence, graph as graph_mod, state
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


# ---------------------------------------------------------------------------
# 1. simulate impact
# ---------------------------------------------------------------------------
def simulate_impact(book: Path, entity: str | None = None, line_id: str | None = None,
                    action: str | None = None) -> dict:
    """测算实体异动或伏笔变更对全书因果链的冲击。"""
    proj = common.load_json(book / "project.json", default={}) or {}
    protagonist = str(proj.get("protagonist", "")).strip()

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
        cog_st = state.load_state(book, "cognition").get("entries", [])
    except (ValueError, FileNotFoundError):
        cog_st = []

    lookup = evidence.entity_lookup(book)

    out: dict = {
        "kind": "simulate_impact",
        "action": action or "mutate",
        "warnings": [],
        "affected_lines": [],
        "unblocked_lines": [],
        "affected_items": [],
        "affected_milestones": [],
        "affected_relations": [],
        "affected_cognition": [],
    }

    # 实体冲击推演（如：杀死某角色、损毁某法宝）
    if entity:
        target_name = entity.strip()
        names = lookup.get(target_name, [target_name])
        for pri, aliases in lookup.items():
            if target_name in aliases:
                names = aliases
                target_name = pri
                break

        target_ent = next((e for e in ents_st if e.get("name") in names), None)
        out["target_entity"] = {
            "name": target_name,
            "type": target_ent.get("type") if target_ent else "unknown",
            "status": target_ent.get("status") if target_ent else "unknown",
            "life_status": target_ent.get("life_status") if target_ent else "unknown",
        }

        # 致命警告检测
        if any(nm == protagonist for nm in names):
            out["warnings"].append(f"🔴 [致命主线崩坏风险] 实体「{target_name}」是本书唯一主角！若其死亡，全书主线脊柱将直接瓦解！")

        if target_ent and target_ent.get("life_status") == "deceased":
            out["warnings"].append(f"⚠️ 实体「{target_name}」在 state/entities.json 中已是死亡状态（deceased），无需重复执行击杀动作。")

        # 1) 波及伏笔与机密
        def _hit_names(text_blob: str) -> bool:
            return any(nm and nm in text_blob for nm in names if len(nm) >= 2)

        for f in lines_st.get("foreshadows", []):
            if str(f.get("status", "")).lower() != "resolved":
                blob = f.get("name", "") + " " + str(f.get("plan", ""))
                if _hit_names(blob):
                    out["affected_lines"].append({
                        "id": f.get("id"),
                        "kind": "foreshadow",
                        "label": f.get("name"),
                        "target_ch": f.get("target_ch"),
                        "reason": "伏笔内容直接点名该实体",
                    })

        for m in lines_st.get("misunderstandings", []):
            if str(m.get("status", "")).lower() != "resolved":
                blob = str(m.get("parties", "")) + " " + str(m.get("content", ""))
                if _hit_names(blob):
                    out["affected_lines"].append({
                        "id": m.get("id"),
                        "kind": "misunderstanding",
                        "label": m.get("parties"),
                        "target_ch": m.get("target_ch"),
                        "reason": "误会双方或内容涉及该实体",
                    })

        for k in lines_st.get("knowledge", []):
            if str(k.get("status", "")).lower() != "revealed":
                holders = [str(h) for h in (k.get("holders") or [])]
                if any(_hit_names(h) for h in holders):
                    out["affected_lines"].append({
                        "id": k.get("id"),
                        "kind": "knowledge",
                        "label": k.get("secret"),
                        "target_ch": k.get("target_ch"),
                        "reason": f"该实体为机密持有者（holders: {holders}），其异动将导致机密泄露或失传",
                    })

        # 2) 随身物品
        for it in ents_st:
            if it.get("type") == "item" and str(it.get("holder", "")) in names:
                out["affected_items"].append({
                    "name": it.get("name"),
                    "charges": it.get("charges"),
                    "condition": it.get("condition"),
                    "status": "将变为无主/遗留物，需在正文交代去向",
                })

        # 3) 主线里程碑
        for ms in (tl_st.get("milestones") or []):
            if str(ms.get("status", "")).lower() == "pending":
                ms_text = ms.get("title", "") + " " + str(ms.get("desc", ""))
                if _hit_names(ms_text):
                    out["affected_milestones"].append({
                        "id": ms.get("id"),
                        "title": ms.get("title"),
                        "target_ch": ms.get("target_ch"),
                        "impact": "里程碑任务与该实体直接挂钩，实体异动可能导致里程碑无法如期达成",
                    })

        # 4) 社交人际网络
        for e in ents_st:
            if e.get("name") in names:
                for rel in (e.get("relations") or []):
                    out["affected_relations"].append({
                        "target": rel.get("target"),
                        "type": rel.get("type"),
                        "desc": rel.get("desc"),
                    })

    # 线索冲击推演（如：揭示秘密 KNO-001 或回收伏笔 GUN-001）
    if line_id:
        lid = line_id.strip()
        out["target_line_id"] = lid

        # 检索依赖此线索的前置依赖 (requires)
        all_lines = (lines_st.get("foreshadows", []) +
                     lines_st.get("misunderstandings", []) +
                     lines_st.get("knowledge", []))
        for g in all_lines:
            reqs = [str(r) for r in (g.get("requires") or [])]
            if lid in reqs:
                out["unblocked_lines"].append({
                    "id": g.get("id"),
                    "name": g.get("name") or g.get("secret") or g.get("parties"),
                    "status": g.get("status"),
                    "impact": f"前置条件 [{lid}] 满足，此线索将被解锁，可推进下一阶段",
                })

    return out


# ---------------------------------------------------------------------------
# 2. simulate branch
# ---------------------------------------------------------------------------
def simulate_branch(book: Path, ch: str | None = None, count: int = 3, write: bool = False) -> dict:
    """为下一章生成 2~3 条互相隔离的走向假说沙盒（写至 log/branches/ch_XXX.md）。"""
    cur_num = common.chapter_token_to_num(ch) if ch else (common.latest_chapter_number(book, "final") or 1)
    tok = f"ch_{cur_num:03d}"
    next_tok = f"ch_{cur_num + 1:03d}"

    try:
        cur_st = state.load_state(book, "current")
    except (ValueError, FileNotFoundError):
        cur_st = {}
    try:
        lines_st = state.load_state(book, "lines")
    except (ValueError, FileNotFoundError):
        lines_st = {}
    try:
        tl_st = state.load_state(book, "timeline")
    except (ValueError, FileNotFoundError):
        tl_st = {}

    # 提取到期线与活跃时钟
    due_lines = [
        f"[{g.get('id')}] {g.get('name') or g.get('parties') or g.get('secret')}"
        for arr in ("foreshadows", "misunderstandings", "knowledge")
        for g in lines_st.get(arr, [])
        if g.get("target_ch") == cur_num + 1 and str(g.get("status", "")).lower() not in ("resolved", "revealed")
    ]
    due_clocks = [
        c.get("name") for c in (tl_st.get("clocks") or [])
        if str(c.get("status", "")).lower() == "active" and c.get("target_ch") == cur_num + 1
    ]

    where_now = f"{cur_st.get('location', '原处')} ｜ {cur_st.get('time', '当时')}"
    sit_now = cur_st.get("situation", "局势胶着")
    goal_now = cur_st.get("goal", "达成阶段突破")
    press = cur_st.get("active_pressures")
    if isinstance(press, list):
        press_now = "；".join(str(x) for x in press if x) or "未知危机逼近"
    else:
        press_now = str(press).strip() if press else "未知危机逼近"

    branches = [
        {
            "branch_id": "Branch_A",
            "name": "走向 A：激进摊牌 · 危机爆发（高张力突破）",
            "style": "强对抗 / 节奏突进 / 危机兑现",
            "core_event": f"主角主动引爆【{press_now}】，不再隐忍试探，与对手直接碰撞正面摊牌。",
            "cognition_play": "打破既有信息壁垒，迫使某项关键机密被当众公开，消除假象。",
            "resource_cost": "剧烈：可能消耗重要战斗道具或触发不可逆伤情，账面资金大额流出。",
            "causal_risk": "主线冲突急剧升温，若本章未能彻底收口，下章必须面对强烈的余震收拾局势。",
            "recommendation": "适合在分卷四分位节点（如 50%、75%）或主线压抑多章后的大爆发。"
        },
        {
            "branch_id": "Branch_B",
            "name": "走向 B：暗流迂回 · 悬疑博弈（中张力蓄水）",
            "style": "知情差博弈 / 侧面调查 / 借力打力",
            "core_event": f"主角暂避锋芒，在【{where_now}】利用第三方中介或配角视角暗中布局，搜集致命证据。",
            "cognition_play": "维持并利用知情差，让对手自以为得计，实则步入主角预设的信息陷阱。",
            "resource_cost": "温和：几乎无重大损耗，反而可能借机缴获或换取新情报/资源。",
            "causal_risk": "需注意推进微波澜拉扯，严禁滑向无冲突的纯日常流水账。",
            "recommendation": "适合高潮之后的情绪缓冲、战力巩固，或大决战前的蓄水铺垫。"
        },
        {
            "branch_id": "Branch_C",
            "name": "走向 C：意外变数 · 规则破壁（反转破局）",
            "style": "突发意外 / 外部势力介入 / 时钟临界",
            "core_event": f"外部第三方势力突然介入打破平衡，或时钟【{due_clocks[0] if due_clocks else '未知变量'}】提前敲响，原有博弈规则被推翻。",
            "cognition_play": "敌我双方同时面对突发混乱，产生新的认知误区或被迫达成临时利益同盟。",
            "resource_cost": "不可测：涉及突发性道具转移、地理位置强行迁移或阵营重构。",
            "causal_risk": "需确保意外变数在 bible 世界规则内有迹可循，杜绝机械降神。",
            "recommendation": "适合在多方势力僵持不下、陷入叙事瓶颈时强行破局。"
        },
    ][:count]

    md_lines = [
        f"# {next_tok} 剧情推演沙盒（多分支假说参谋单）",
        "<!-- ⚠️ 参谋件属性说明：",
        "     本文件由 studio.py simulate branch 自动推演生成，放置于 log/branches/ 目录，",
        "     纯供 Stage 1 主控（Director）作为发散构思与横向比较的参谋参考；",
        "     本文件的任何内容【绝不写入正史】、绝不影响 state/ 状态与 outlines/ 大纲；",
        "     主控最终采纳其中一条走向后，请按常规工序将其提炼并写入 beats/ 细纲任务书。 -->",
        "",
        f"## 📍 当前正史锚点 ({tok})",
        f"- **时地与在场**：{where_now}",
        f"- **当前处境**：{sit_now}",
        f"- **主角目标**：{goal_now}",
        f"- **悬顶危机**：{press_now}",
        f"- **预定到期伏笔**：{', '.join(due_lines) or '无紧急到期线'}",
        "",
        f"## 🎲 下一章 ({next_tok}) 候选走向假说（共 {len(branches)} 条）",
    ]

    for b in branches:
        md_lines += [
            f"### 方案：{b['name']}",
            f"- **风格调性**：{b['style']}",
            f"- **核心情节点**：{b['core_event']}",
            f"- **信息与认知博弈**：{b['cognition_play']}",
            f"- **账目与道具损耗**：{b['resource_cost']}",
            f"- **潜在因果链风险**：{b['causal_risk']}",
            f"- **主控采纳建议**：{b['recommendation']}",
            ""
        ]

    content = "\n".join(md_lines) + "\n"
    target_file = book / "log" / "branches" / f"{next_tok}.md"

    written = False
    if write:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        common.atomic_write_text(target_file, content)
        written = True

    return {
        "kind": "simulate_branch",
        "anchor_chapter": tok,
        "next_chapter": next_tok,
        "branches_count": len(branches),
        "branches": branches,
        "written": str(target_file.relative_to(book)) if written else None,
        "markdown": content,
    }


# ---------------------------------------------------------------------------
# 3. cmd_simulate 总调度
# ---------------------------------------------------------------------------
def cmd_simulate(args) -> int:
    book = ws_gate(args)
    if book is None:
        return ws_gate_code()

    sub_act = getattr(args, "simulate_action", None)
    if sub_act == "impact":
        ent = getattr(args, "entity", None)
        line = getattr(args, "line", None)
        act = getattr(args, "action", None)
        if not ent and not line:
            print("❌ simulate impact 需要 --entity <名称> 或 --line <线索ID>")
            return 2
        payload = simulate_impact(book, entity=ent, line_id=line, action=act)
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        # Terminal Rich / Text Output
        lines_md = [
            f"# 💥 因果链影响测算报告（模拟动作：{payload['action']}）",
            f"- **目标对象**：{ent or line}",
        ]
        if payload["warnings"]:
            lines_md.append("\n## ⚠️ 高危警示")
            for w in payload["warnings"]:
                lines_md.append(f"- {w}")

        if payload["affected_lines"]:
            lines_md.append(f"\n## 📜 波及伏笔与机密 ({len(payload['affected_lines'])} 项)")
            for al in payload["affected_lines"]:
                lines_md.append(f"- **[{al['id']}] ({al['kind']})** {al['label']} ➔ {al['reason']}")

        if payload["unblocked_lines"]:
            lines_md.append(f"\n## 🔓 解锁后续伏笔 ({len(payload['unblocked_lines'])} 项)")
            for ul in payload["unblocked_lines"]:
                lines_md.append(f"- **[{ul['id']}]** {ul['name']} ➔ {ul['impact']}")

        if payload["affected_items"]:
            lines_md.append(f"\n## 🗡️ 波及随身道具 ({len(payload['affected_items'])} 件)")
            for it in payload["affected_items"]:
                lines_md.append(f"- **{it['name']}** (charges: {it.get('charges', '?')}) ➔ {it['status']}")

        if payload["affected_milestones"]:
            lines_md.append(f"\n## 🚩 波及主线里程碑 ({len(payload['affected_milestones'])} 项)")
            for ms in payload["affected_milestones"]:
                lines_md.append(f"- **[{ms['id']}] {ms['title']}** ➔ {ms['impact']}")

        if payload["affected_relations"]:
            lines_md.append(f"\n## 👥 波及人际网络 ({len(payload['affected_relations'])} 条)")
            for r in payload["affected_relations"]:
                lines_md.append(f"- ➔ {r['target']} ({r['type']}): {r.get('desc','')}")

        full_text = "\n".join(lines_md)
        if _HAS_RICH and console:
            console.print(Panel(
                Markdown(full_text),
                title="[bold yellow]💥 [因果链推演测算] 模拟报告[/bold yellow]",
                border_style="yellow",
                padding=(1, 2)
            ))
        else:
            print(full_text)
        return 0

    elif sub_act == "branch":
        ch = getattr(args, "chapter", None)
        cnt = getattr(args, "count", 3) or 3
        to_write = bool(getattr(args, "write", False))
        payload = simulate_branch(book, ch=ch, count=cnt, write=to_write)
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if to_write:
            print(f"✅ 剧情假说沙盘已写入: {payload['written']}")
            print("   （纯参谋件，绝不污染正史；主控确定方案后提炼至 beats 即可）")
            return 0

        if _HAS_RICH and console:
            console.print(Panel(
                Markdown(payload["markdown"]),
                title=f"[bold purple]🎲 [剧情走向假说沙盘] {payload['anchor_chapter']} ➔ {payload['next_chapter']}[/bold purple]",
                border_style="magenta",
                padding=(1, 2)
            ))
        else:
            print(payload["markdown"])
        return 0

    print("❌ simulate 需要 impact 或 branch 子命令（如: studio simulate impact --entity 苏九娘）")
    return 2
