import html
import json
import re
from pathlib import Path

from . import common, evidence, state

def generate_dashboard_html(book: Path) -> str:
    """生成包含人物关系、伏笔看板、情绪节奏与实时状态的现代化交互式看板 HTML"""
    esc = html.escape  # P3-10: 所有插值过 esc，书名/实体名/summary 含 <>& 不再破版
    proj = common.load_json(book / "project.json", default={})
    title = esc(str(proj.get("title", "未命名作品")))
    genre = esc(str(proj.get("genre", "通用网文")))

    # 1. 状态与实体
    cur = state.load_state(book, "current")
    ents = state.load_state(book, "entities").get("entries", [])
    gaps_data = evidence.gaps(book)

    # 2. 章节与钩子分析
    chapters_info = []
    for tok, num, text in evidence.final_chapters(book):
        hook_info = evidence.detect_chapter_hook(text) if hasattr(evidence, "detect_chapter_hook") else {"type": "未知", "detail": ""}
        words = common.cjk_count(text)
        chapters_info.append({
            "chapter": esc(tok),
            "num": num,
            "words": words,
            "hook_type": esc(hook_info.get("type", "普通收尾")),
            "hook_desc": esc(hook_info.get("detail", "")[:30]),
        })
    
    # 3. 伏笔与暗线状态清洗
    active_guns = [g for g in gaps_data.get("foreshadows", []) if g.get("status") != "Resolved" and not g.get("overdue")]
    active_mis = [m for m in gaps_data.get("misunderstandings", []) if m.get("status") != "Resolved" and not m.get("overdue")]
    active_kno = [k for k in gaps_data.get("knowledge", []) if k.get("status") != "Revealed" and not k.get("overdue")]
    
    overdue_items = []
    for g in gaps_data.get("foreshadows", []):
        if g.get("overdue"):
            overdue_items.append({"id": g["id"], "title": g.get("name", ""), "desc": f"逾期 {g.get('idle_chapters', 0)} 章 ｜ 目标 ch_{g.get('target_ch')}"})
    for m in gaps_data.get("misunderstandings", []):
        if m.get("overdue"):
            overdue_items.append({"id": m["id"], "title": m.get("parties", ""), "desc": f"逾期未澄清 ｜ 目标 ch_{m.get('target_ch')}"})
    for k in gaps_data.get("knowledge", []):
        if k.get("overdue"):
            overdue_items.append({"id": k["id"], "title": str(k.get("secret", ""))[:18], "desc": f"逾期未揭示 ｜ 目标 ch_{k.get('target_ch')}"})

    # HTML 模版构建
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Novel Studio 看板 — 《{title}》</title>
    <style>
        :root {{
            --bg-main: #0f172a;
            --bg-card: #1e293b;
            --bg-sub: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-cyan: #06b6d4;
            --accent-pink: #f43f5e;
            --accent-amber: #f59e0b;
            --accent-emerald: #10b981;
            --accent-purple: #a855f7;
            --border: #334155;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Noto Sans SC", sans-serif; }}
        body {{ background-color: var(--bg-main); color: var(--text-main); line-height: 1.6; padding: 24px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }}
        .header-title {{ font-size: 24px; font-weight: 700; background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .header-badge {{ background: var(--bg-card); border: 1px solid var(--border); padding: 6px 14px; border-radius: 999px; font-size: 13px; color: var(--text-muted); }}
        
        .grid-container {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 20px; }}
        .card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
        .col-12 {{ grid-column: span 12; }}
        .col-8 {{ grid-column: span 8; }}
        .col-4 {{ grid-column: span 4; }}
        .col-6 {{ grid-column: span 6; }}
        
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 10px; }}
        .card-title {{ font-size: 16px; font-weight: 600; color: var(--accent-cyan); display: flex; align-items: center; gap: 8px; }}
        
        /* 状态面板 */
        .status-badge-group {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }}
        .status-badge {{ background: rgba(6, 182, 212, 0.12); color: var(--accent-cyan); border: 1px solid rgba(6, 182, 212, 0.3); padding: 4px 10px; border-radius: 6px; font-size: 12px; }}
        .stat-item {{ margin-bottom: 10px; font-size: 14px; display: flex; }}
        .stat-label {{ color: var(--text-muted); min-width: 80px; font-weight: 500; }}
        .stat-val {{ color: var(--text-main); flex: 1; }}
        
        /* 实体网格 */
        .entity-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }}
        .entity-card {{ background: var(--bg-sub); border-radius: 8px; padding: 12px; border-left: 4px solid var(--accent-cyan); }}
        .entity-card.place {{ border-left-color: var(--accent-emerald); }}
        .entity-card.item {{ border-left-color: var(--accent-amber); }}
        .entity-card.faction, .entity-card.force, .entity-card.org {{ border-left-color: var(--accent-purple); }}
        .entity-card.retired {{ border-left-color: var(--accent-pink); opacity: 0.65; }}
        .entity-name {{ font-weight: 600; font-size: 14px; margin-bottom: 4px; display: flex; justify-content: space-between; }}
        .entity-summary {{ font-size: 12px; color: var(--text-muted); line-height: 1.4; }}
        
        /* 看板 */
        .kanban {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }}
        .kanban-col {{ background: rgba(15, 23, 42, 0.6); border-radius: 8px; padding: 12px; border: 1px solid var(--border); }}
        .kanban-col-header {{ font-size: 13px; font-weight: 600; margin-bottom: 10px; padding-bottom: 6px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; }}
        .kanban-card {{ background: var(--bg-card); border-radius: 6px; padding: 10px; margin-bottom: 8px; border: 1px solid var(--border); font-size: 12px; }}
        .kanban-card-title {{ font-weight: 600; margin-bottom: 4px; color: var(--text-main); }}
        .kanban-card-meta {{ color: var(--text-muted); font-size: 11px; display: flex; justify-content: space-between; margin-top: 6px; }}
        
        /* 节奏与钩子 */
        .pacing-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        .pacing-table th, .pacing-table td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
        .pacing-table th {{ color: var(--text-muted); font-weight: 500; }}
        .hook-tag {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }}
        .hook-强钩 {{ background: rgba(244, 63, 94, 0.15); color: var(--accent-pink); border: 1px solid rgba(244, 63, 94, 0.3); }}
        .hook-悬置 {{ background: rgba(245, 158, 11, 0.15); color: var(--accent-amber); border: 1px solid rgba(245, 158, 11, 0.3); }}
        .hook-弱收 {{ background: rgba(16, 185, 129, 0.15); color: var(--accent-emerald); border: 1px solid rgba(16, 185, 129, 0.3); }}
        .hook-反高潮 {{ background: rgba(168, 85, 247, 0.15); color: var(--accent-purple); border: 1px solid rgba(168, 85, 247, 0.3); }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="header-title">📖 《{title}》· Novel Studio 状态与剧情全景看板</div>
            <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">题材标签：{genre} ｜ 已定稿 {len(chapters_info)} 章 ｜ 累计 {sum(c['words'] for c in chapters_info)} 字</div>
        </div>
        <div class="header-badge">
            确定性状态机：v2 SSOT 🟢
        </div>
    </div>
    
    <div class="grid-container">
        <!-- 主角实时状态面板 -->
        <div class="card col-4">
            <div class="card-header">
                <div class="card-title">⚡ 主角现场状态（{esc(str(cur.get('time', '未知时间')))}</div>
            </div>
            <div class="status-badge-group">
                {f'<div class="status-badge">🗺️ {esc(str(cur["region"]))}</div>' if cur.get('region') else ''}
                <div class="status-badge">📍 {esc(str(cur.get('location', '未知')))}</div>
                <div class="status-badge">❤️ 状态：{esc(str(cur.get('injury', '完好')))}</div>
            </div>
            <div class="stat-item"><span class="stat-label">境界修为</span><span class="stat-val" style="color: var(--accent-amber); font-weight: 600;">{esc(str(cur.get('power_level') or cur.get('realm') or '未设定'))}</span></div>
            <div class="stat-item"><span class="stat-label">掌握功法</span><span class="stat-val">{esc(str(cur.get('abilities', '无')))}</span></div>
            <div class="stat-item"><span class="stat-label">持有资产</span><span class="stat-val">{esc(str(cur.get('assets', '无')))}</span></div>
            <div class="stat-item"><span class="stat-label">关键人际</span><span class="stat-val">{esc(str(cur.get('key_relationships', '无')))}</span></div>
            <div class="stat-item"><span class="stat-label">当前目标</span><span class="stat-val" style="color: var(--accent-cyan);">{esc(str(cur.get('goal', '无')))}</span></div>
        </div>

        <!-- 伏笔与暗线看板 -->
        <div class="card col-8">
            <div class="card-header">
                <div class="card-title">📌 伏笔与暗线生命周期看板（Lines SSOT）</div>
            </div>
            <div class="kanban">
                <div class="kanban-col">
                    <div class="kanban-col-header" style="color: var(--accent-emerald);">🟢 埋设推进中 <span>{len(active_guns)}</span></div>
                    {"".join(f'''<div class="kanban-card">
                        <div class="kanban-card-title">[{g['id']}] {esc(str(g['name']))}</div>
                        <div class="kanban-card-meta"><span>权重 {g.get('weight', 1)}</span><span>目标 ch_{g.get('target_ch')}</span></div>
                    </div>''' for g in active_guns) or '<div style="color: var(--text-muted); font-size: 11px; text-align: center; padding: 12px 0;">暂无埋设伏笔</div>'}
                </div>
                <div class="kanban-col">
                    <div class="kanban-col-header" style="color: var(--accent-amber);">🟡 误会与认知差 <span>{len(active_mis)}</span></div>
                    {"".join(f'''<div class="kanban-card">
                        <div class="kanban-card-title">[{m['id']}] {esc(str(m['parties']))}</div>
                        <div class="kanban-card-meta"><span>等级 {m.get('level', 1)}</span><span>目标 ch_{m.get('target_ch')}</span></div>
                    </div>''' for m in active_mis) or '<div style="color: var(--text-muted); font-size: 11px; text-align: center; padding: 12px 0;">暂无误会线索</div>'}
                </div>
                <div class="kanban-col">
                    <div class="kanban-col-header" style="color: var(--accent-purple);">🔒 秘密信息差 <span>{len(active_kno)}</span></div>
                    {"".join(f'''<div class="kanban-card">
                        <div class="kanban-card-title">[{k['id']}] {esc(str(k.get('secret', ''))[:18])}...</div>
                        <div class="kanban-card-meta"><span>权重 {k.get('weight', 1)}</span><span>目标 ch_{k.get('target_ch')}</span></div>
                    </div>''' for k in active_kno) or '<div style="color: var(--text-muted); font-size: 11px; text-align: center; padding: 12px 0;">暂无未揭秘密</div>'}
                </div>
                <div class="kanban-col">
                    <div class="kanban-col-header" style="color: var(--accent-pink);">🔴 逾期预警 <span>{len(overdue_items)}</span></div>
                    {"".join(f'''<div class="kanban-card" style="border-color: var(--accent-pink);">
                        <div class="kanban-card-title">[{item['id']}] {esc(str(item['title']))}</div>
                        <div class="kanban-card-meta"><span style="color: var(--accent-pink);">{esc(str(item['desc']))}</span></div>
                    </div>''' for item in overdue_items) or '<div style="color: var(--text-muted); font-size: 11px; text-align: center; padding: 12px 0;">暂无逾期线索</div>'}
                </div>
            </div>
        </div>

        <!-- 章节节奏与钩子心电图 -->
        <div class="card col-6">
            <div class="card-header">
                <div class="card-title">📈 章节心电图与章尾钩子交替</div>
            </div>
            <table class="pacing-table">
                <thead>
                    <tr>
                        <th>章节</th>
                        <th>字数</th>
                        <th>章尾钩子类型</th>
                        <th>末尾张力特征</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f'''<tr>
                        <td style="font-weight: 600;">{c['chapter']}</td>
                        <td>{c['words']} 字</td>
                        <td><span class="hook-tag hook-{c['hook_type']}">{c['hook_type']}</span></td>
                        <td style="color: var(--text-muted); font-size: 12px;">{c['hook_desc'][:30]}...</td>
                    </tr>''' for c in chapters_info) or '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">暂无定稿章节</td></tr>'}
                </tbody>
            </table>
        </div>

        <!-- 人物与关键实体 -->
        <div class="card col-6">
            <div class="card-header">
                <div class="card-title">👥 出场人物与关键实体网络</div>
            </div>
            <div class="entity-grid">
                {"".join(f'''<div class="entity-card {e.get('type', 'person')} {'retired' if e.get('status') == 'retired' else ''}">
                    <div class="entity-name">
                        <span>{esc(str(e['name']))}</span>
                        <span style="font-size: 11px; color: var(--text-muted); font-weight: normal;">{esc(str(e.get('realm') or e.get('attitude') or (f"余{e['charges']}次" if e.get('charges') is not None else e.get('type', 'person'))))}{' · 已退役' if e.get('status') == 'retired' else ''}</span>
                    </div>
                    <div class="entity-summary">{esc(str(e.get('summary', ''))[:60])}</div>
                </div>''' for e in ents[:12]) or '<div style="color: var(--text-muted); font-size: 12px; grid-column: 1/-1;">暂未登记实体</div>'}
            </div>
        </div>
    </div>
</body>
</html>
"""
    return html

def export_dashboard(book: Path) -> Path:
    out_file = book / "export" / "views" / "dashboard.html"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    html = generate_dashboard_html(book)
    out_file.write_text(html, encoding="utf-8")
    return out_file
