"""一致性分数曲线：每次 check 追加一行指标快照（log/scorecard.jsonl）。

单次 check 是「此刻没病」的快照，分数曲线才是漂移检测——长篇的敌人是
缓慢漂移，「warning 数逐卷爬升」只有时间序列可见（PLAN_CONSISTENCY_50W D3）。

零 Token：引擎在 check 完成时自动追加，`check --trend` 消费。
文件放 log/（不属八表、不入快照、回滚不动——测量史是只增资产）。
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

SCORECARD_NAME = "scorecard.jsonl"
DEFAULT_TREND_ROWS = 20


def scorecard_path(book: Path) -> Path:
    return Path(book) / "log" / SCORECARD_NAME


def _count(report: dict, bucket: str) -> int:
    sys_h = report.get("system_health", {})
    nar_h = report.get("narrative_health", {})
    return len(sys_h.get(bucket, []) or []) + len(nar_h.get(bucket, []) or [])


def append_score(book: Path, report: dict) -> dict:
    """从 run_checks 报告提取一行指标并追加到 scorecard.jsonl。"""
    by_code: dict[str, int] = {}
    sys_h = report.get("system_health", {})
    nar_h = report.get("narrative_health", {})
    for section in (sys_h, nar_h):
        for bucket in ("errors", "warnings", "infos"):
            for item in section.get(bucket, []) or []:
                code = str(item.get("code") or "?")
                by_code[code] = by_code.get(code, 0) + 1
    row = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "latest_ch": int(report.get("stats", {}).get("final_chapters") or 0),
        "ok": bool(report.get("ok")),
        "errors": _count(report, "errors"),
        "warnings": _count(report, "warnings"),
        "infos": _count(report, "infos"),
        "by_code": by_code,
    }
    path = scorecard_path(book)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return row


def load_scores(book: Path, limit: int = DEFAULT_TREND_ROWS) -> list[dict]:
    """读最近 limit 行（坏行容忍，零行为空表）。"""
    p = scorecard_path(book)
    if not p.is_file():
        return []
    out: list[dict] = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out[-max(1, limit):]


def _top_codes(row: dict, n: int = 3) -> str:
    by_code = {k: v for k, v in (row.get("by_code") or {}).items()
               if not str(k).startswith("stage0_onboarding")}
    ranked = sorted(by_code.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return "、".join(f"{k}×{v}" for k, v in ranked) if ranked else "—"


def render_trend(book: Path, limit: int = DEFAULT_TREND_ROWS) -> str:
    """近 N 次体检的分数曲线（文本表格；趋势漂移一眼可见）。"""
    rows = load_scores(book, limit)
    if not rows:
        return "（尚无体检记录——跑一次 `python studio.py check` 即开始积累分数曲线）"
    lines = [f"📈 一致性分数曲线（最近 {len(rows)} 次体检，log/scorecard.jsonl）",
             "  时间                定稿章  E    W    I    状态  热点码",
             "  " + "-" * 66]
    prev: dict[str, int] = {}
    for row in rows:
        by_code = row.get("by_code") or {}
        movers = []
        for code, cnt in sorted(by_code.items()):
            delta = cnt - prev.get(code, 0)
            if delta > 0 and not str(code).startswith("stage0_onboarding"):
                movers.append(f"{code}+{delta}")
        flag = "↑漂移" if movers else ""
        lines.append(f"  {str(row.get('ts', ''))[:19]:<19} {str(row.get('latest_ch', 0)):>4}"
                     f"  {str(row.get('errors', 0)):>3}  {str(row.get('warnings', 0)):>3}"
                     f"  {str(row.get('infos', 0)):>3}  {'✅' if row.get('ok') else '❌'}"
                     f"  {_top_codes(row)}{' ' + flag if flag else ''}")
        prev = dict(by_code)
    first, last = rows[0], rows[-1]
    lines.append("  " + "-" * 66)
    lines.append(f"  区间变化：errors {first.get('errors', 0)}→{last.get('errors', 0)}"
                 f" ｜ warnings {first.get('warnings', 0)}→{last.get('warnings', 0)}"
                 f" ｜ infos {first.get('infos', 0)}→{last.get('infos', 0)}"
                 f" ｜ 定稿 {first.get('latest_ch', 0)}→{last.get('latest_ch', 0)} 章")
    return "\n".join(lines)
