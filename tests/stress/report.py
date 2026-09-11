"""报告渲染（方案 §5.2 口径）：REPORT.md = 结论 + 红线表 + L3 捕获表 + 曲线（ASCII）。

性能一律相对基线陈述；绝对值只作参考列，不做承诺（§约定3）。
"""
from __future__ import annotations

import json
from pathlib import Path

from .common import jsonl_rows, load_json, slope


def _sparkline(xs: list[float,], width: int = 40) -> str:
    if not xs:
        return "（无数据）"
    if len(xs) == 1:
        return f"● {xs[0]:.2f}"
    step = max(1, len(xs) // width)
    ys = xs[::step][-width:]
    lo, hi = min(ys), max(ys)
    rng = (hi - lo) or 1.0
    bar = "▁▂▃▄▅▆▇█"
    return "".join(bar[min(7, int((y - lo) / rng * 7.99))] for y in ys) + f"  [{lo:.2f}→{hi:.2f}]"


def render(book: Path) -> str:
    book = Path(book)
    d = book / "log" / "stress"
    ev = load_json(d / "eval.json", default={}) or {}
    rows = jsonl_rows(d / "metrics.jsonl")
    soak = jsonl_rows(d / "soak_log.jsonl")
    L: list[str] = []
    L.append("# 压力测试报告")
    L.append("")
    L.append(f"- 档位：`{ev.get('scale')}` ｜ 章数：{ev.get('chapters')} ｜ seed：{ev.get('seed')}")
    verdict = ev.get("verdict", "N/A")
    L.append(f"- **判定：{verdict}**（红线 {sum(1 for r in ev.get('redline', [])) } 条，"
             f"挂零 {sum(1 for r in ev.get('redline', []) if not r.get('ok'))} 条）")
    if ev.get("perf", {}).get("baseline") in (None, "none（首跑请 --bootstrap 建基线）"):
        L.append("- 性能口径：首跑基线（只建档不判优）；绝对值仅参考。")
    L.append("")
    L.append("## 红线")
    L.append("")
    L.append("| 项 | 结果 | 备注 |")
    L.append("|----|------|------|")
    for r in ev.get("redline", []):
        L.append(f"| {r['name']} | {'✅' if r.get('ok') else '❌'} | {str(r.get('detail',''))[:110]} |")
    L.append("")
    L.append("## L3 捕获（§4.1 雷库）")
    L.append("")
    L.append("| 雷 | 判定 | 明细 |")
    L.append("|----|------|------|")
    for fid, v in sorted((ev.get("faults") or {}).items()):
        mark = "✅ 抓到" if v.get("ok") else ("➖ N/A" if v.get("ok") is None else "❌ 漏抓")
        L.append(f"| {fid} | {mark} | {str(v.get('detail','')).replace('|','/ ')[:120]} |")
    L.append("")
    L.append("## 增长与曲线（观察项）")
    L.append("")
    if rows:
        chs = [r["ch"] for r in rows]
        L.append(f"- check 耗时（折叠态）：{_sparkline([r.get('check_sec', 0) for r in rows])} s")
        L.append(f"- sync 耗时：{_sparkline([r.get('sync_sec', 0) for r in soak])} s")
        L.append(f"- RSS：{_sparkline([r.get('rss_mb', 0) for r in rows])} MB")
        for tbl in ("changelog.jsonl", "derived.json", "persons.json", "lines.json", "synopsis.json",
                    "locked.json", "processed"):
            series = [((r.get("tables") or {}).get(f"state/{tbl}") or (r.get("tables") or {}).get(tbl)
                       or {}).get("bytes", 0) for r in rows]
            if any(series):
                L.append(f"- {tbl} 字节：{_sparkline(series)}（斜率 {round(slope(series), 2)} B/chip）")
        g = ev.get("watch", {}).get("table_growth_top") or []
        if g:
            L.append("")
            L.append("| 表（按末态体积排序，前 6） | rows | bytes | 增量rows |")
            L.append("|------|------|------|------|")
            for row in g:
                L.append(f"| {row['table']} | {row.get('rows')} | {row.get('bytes')} | {row.get('rows_growth')} |")
    w = ev.get("watch", {})
    L.append("")
    L.append(f"- hard_cap 占比：{w.get('hard_cap_ratio')} ｜ p0 挤压 {json.dumps(w.get('p0_share'), ensure_ascii=False)}")
    L.append(f"- warnings 漂移：{w.get('warnings_slope_per_10ch')} 条/10章 ｜ check_sec 统计 "
             f"{json.dumps(w.get('check_sec'), ensure_ascii=False)}")
    perf = ev.get("perf", {})
    L.append("")
    L.append("## 性能（相对口径，基线对照）")
    L.append("")
    L.append("```json")
    L.append(json.dumps({k: v for k, v in perf.items() if k != "baseline"}, ensure_ascii=False, indent=1))
    L.append("```")
    if isinstance(perf.get("baseline"), dict):
        L.append("```json\n" + json.dumps(perf["baseline"], ensure_ascii=False, indent=1) + "\n```")
    if ev.get("fails"):
        L.append("")
        L.append("## 挂零明细")
        L.extend(f"- 🚫 {f}" for f in ev["fails"])
    text = "\n".join(L) + "\n"
    (d / "REPORT.md").write_text(text, encoding="utf-8")
    return text
