"""度量采集（方案 §3.1）：表增长 / 耗时 / 预算挤压 / warnings 漂移 / 内存。

零裁决原则：这里只出数；判定（PASS/FAIL、曲线斜率阈值）在 eval.py。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from .common import ch_token, engine_cli, write_json


def state_table_stats(book: Path) -> dict:
    from engine import state as st
    out: dict[str, dict] = {}
    for key in st.STATE_KEYS:
        p = Path(book) / "state" / f"{key}.json"
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            out[key] = {"bytes": p.stat().st_size, "rows": -1}
            continue
        if isinstance(data, dict):
            if "entries" in data:
                rows = len(data["entries"] or [])
            elif key == "lines":
                rows = sum(len(data.get(a) or []) for a in ("foreshadows", "misunderstandings", "knowledge"))
            elif key == "ledger":
                rows = len(data.get("transactions") or [])
            elif key == "timeline":
                rows = (len(data.get("events") or []) + len(data.get("arcs") or [])
                        + len(data.get("clocks") or []))
            elif key == "synopsis":
                rows = len(data.get("chapters") or {})
            elif key == "current":
                rows = len(data.get("present_moods") or {})
            else:
                rows = len([1 for v in data.values() if isinstance(v, list)])
        else:
            rows = -1
        out[key] = {"bytes": p.stat().st_size, "rows": rows}
    for extra in ("state/changelog.jsonl", "state/inbox/processed"):
        p = Path(book) / extra
        if p.is_file():
            out[extra] = {"bytes": p.stat().st_size, "rows": sum(1 for _ in p.open(encoding="utf-8"))}
        elif p.is_dir():
            out[extra] = {"bytes": sum(f.stat().st_size for f in p.glob("*.json")), "rows": len(list(p.glob("*.json")))}
    return out


def run_check_sample(book: Path, full: bool = False) -> tuple[dict, float]:
    """跑一次 check --json（可选 --full），返回 (报告, 秒)。耗时曲线的主口径。"""
    argv = ["check", "--json", "-w", str(book)] + (["--full"] if full else [])
    t0 = time.perf_counter()
    rc, out = engine_cli(argv)
    dt = time.perf_counter() - t0
    try:
        rep = json.loads(out)
    except json.JSONDecodeError:
        rep = {"_rc": rc, "_raw": out[:400]}
    return rep, dt


def codes_of(report: dict) -> dict[str, list[str]]:
    codes: dict[str, list[str]] = {}

    def walk(node):
        if isinstance(node, dict):
            c = node.get("code")
            if isinstance(c, str) and c:
                codes.setdefault(c, []).append(str(node.get("msg", "")))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(report)
    return codes


def count_by_bucket(report: dict) -> dict:
    out = {}
    for bucket in ("errors", "warnings", "infos"):
        v = report.get(bucket)
        out[bucket] = len(v) if isinstance(v, list) else -1
    stats = report.get("stats") or {}
    for k in ("history_collapsed", "accepted_hidden"):
        if k in stats:
            out[k] = stats[k]
    return out


def pack_sample(book: Path, ch: str, tight_cap: int | None = None) -> dict:
    """一章 pack 快照：占比 / 阶梯 / 豁免字节 / 小票诚实（honest）。"""
    from engine import common as engc
    from engine import pack as pack_mod
    saved = pack_mod.PACK_TOKEN_CAP
    m: dict = {}
    try:
        rep = pack_mod.build_pack(book, ch)
        b = dict(rep.get("budget_report", {}))
        m["cap"] = b.get("cap")
        m["total"] = b.get("total")
        m["p0"] = b.get("p0")
        m["p1"] = b.get("p1")
        m["p2"] = b.get("p2")
        m["over_budget"] = bool(b.get("over_budget"))
        m["compressed"] = list(b.get("compressed") or [])
        m["hard_cap_breached"] = bool(b.get("hard_cap_breached"))
        p0, p1 = rep.get("p0", {}), rep.get("p1", {})
        m["p0_share"] = round((m["p0"] or 0) / max(1, m["total"] or 1), 3)
        m["p1_entities"] = len(p1.get("entities") or [])
        m["p1_spine"] = len(p1.get("spine") or [])
        m["protected_beats_tok"] = engc.est_tokens(p0.get("beats") or "")
        m["protected_current_tok"] = engc.est_tokens(str(p0.get("current") or ""))
        # 小票诚实（render+est_tokens 重算 == 票面）
        honest = True
        for layer in ("p0", "p1", "p2"):
            obj = rep.get(layer) or {}
            recount = engc.est_tokens(pack_mod.render_layer(layer, obj)) if obj else 0
            if (b.get(layer) or 0) != recount:
                honest = False
        m["honest"] = honest
        if tight_cap:
            pack_mod.PACK_TOKEN_CAP = tight_cap
            rep2 = pack_mod.build_pack(book, ch)
            b2 = rep2.get("budget_report", {})
            m["tight"] = {"cap": tight_cap, "total": b2.get("total"),
                          "compressed": list(b2.get("compressed") or []),
                          "hard_cap_breached": bool(b2.get("hard_cap_breached")),
                          "beats_intact": rep2.get("p0", {}).get("beats") == p0.get("beats"),
                          "current_intact": rep2.get("p0", {}).get("current") == p0.get("current")}
    finally:
        pack_mod.PACK_TOKEN_CAP = saved
    return m


def misc_timings(book: Path, plan: dict, n: int) -> dict:
    """每 50 章的重型工具计时（advisory 面：只计时与保 rc，不做语义断言）。"""
    out: dict[str, float | int] = {}
    vol = next(v["name"] for v in plan["vols"] if v["start"] <= n <= v["end"])
    ch = ch_token(n)
    for name, argv in (("audit", ["audit", ch, "-w", str(book)]),
                       ("reconcile", ["reconcile", vol, "-w", str(book)]),
                       ("simulate", ["simulate", "impact", "-e", plan["protagonist"], "-w", str(book)]),
                       ("rollup", ["state", "rollup", vol, "-w", str(book)]),
                       ("index", ["index", "-w", str(book)]),
                       ("cockpit", ["cockpit", ch, "-w", str(book)]),
                       ("ask", ["ask", plan["protagonist"], "--json", "-w", str(book)])):
        t0 = time.perf_counter()
        rc, _ = engine_cli(argv)
        out[name] = round(time.perf_counter() - t0, 3)
        out[f"{name}_rc"] = rc
    return out
