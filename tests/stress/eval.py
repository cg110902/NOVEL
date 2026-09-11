"""L5 判定（方案 §4.2 / §7）：强一致性断言 + L3 捕获率 + 基线对照，产出 eval.json。

判定分三类：
- 红线（错了就是引擎/harness bug）：manifest diff、ledger 逐池重放、time_day 单调、
  P1 实体零注入、pack 小票诚实、豁免字节一致、阶梯顺序、L3 捕获率（漏抓=P0）、
  未预期码必须为空（自然噪声全部要么被剧本预期、要么进白名单——白名单逐条写明理由）；
- 观察项（不判死，进报告）：无界表排行、耗时斜率、p0 挤压曲线、warnings 漂移；
- 性能回归：对 tests/stress/baseline.json 同档基线，均值/p95 劣化 >20% 挂红（首跑 --bootstrap 建档）。
"""
from __future__ import annotations

import json
from pathlib import Path

from . import faults, generator
from .common import ROOT, SCALES, ch_token, jsonl_rows, load_json, slope, write_json

BASELINE_PATH = ROOT / "tests" / "stress" / "baseline.json"

LADDER_SEQ = ["裁 P2 旧章指针", "裁 P1 间接关联", "梗概脊柱收缩至最近 5 章", "上章余温裁至 400 字"]

# 合成书自然噪声白名单（每条都是引擎对“假文本”的真实、正确反应，非缺陷）：
BENIGN = {
    "mood_dialogue_flat":      "高烈度情绪但声纹窗内无起伏——模板对白天然平，预期命中而非漏报",
    "reader_memory_stale":     "locked 事实点名后长期不重现——死线/旧约的自然记忆漂移，正是要看的行为",
    "state_watch_hit":         "守望词命中为 info 级流程提示",
    "line_never_surfaced":     "尾段 clamp 成 longline 的线可能当章未提及——生成器允许的一次性豁免",
    "plotline_starvation":     "饥饿窗对合成剧本的节奏告警（advisory）",
    "voiceprint_drift":        "模板句在声纹窗内自然波动——探测器灵敏度在书里始终在线（非缺陷）",
    "subplot_stall":           "剧本 warm/cold 线回唤-回收间隔本就 >15 章，告警语义成立"
                               "（2026-09 引擎已修 remind_ch 回填——此项不再是误报豁免，是合法提醒）"
                               "——长浸泡下停滞告警是机械读数；已记入 FINDINGS 候选（引擎口径待裁决）",
}


def run_eval(book: Path, plan: dict, *, deep: bool = True, bootstrap: bool = False,
             quiet: bool = False) -> dict:
    book = Path(book)
    d = book / "log" / "stress"
    rows = jsonl_rows(d / "metrics.jsonl")
    soak_log = jsonl_rows(d / "soak_log.jsonl")
    union = load_json(d / "codes_union.json", default={}) or {}
    out: dict = {"scale": plan["scale"], "chapters": plan["chapters"], "seed": plan["seed"],
                "redline": [], "watch": {}, "faults": {}, "perf": {}}
    fails: list[str] = []

    def redline(name: str, ok: bool, detail: str = ""):
        out["redline"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            fails.append(f"{name}: {detail}")

    # ---- 1. manifest diff（plan vs actual）----
    actual = load_json(d / "manifest_actual.json", default=None)
    if actual is None:
        redline("manifest_actual", False, "缺 manifest_actual.json（先 soak）")
    else:
        diff = generator.manifest_diff(plan, actual)
        redline("manifest_diff_empty", not diff, "; ".join(diff[:4]))

    # ---- 2. ledger 逐池重放（state 侧独立复算）----
    from engine import state as st
    led = st.load_state(book, "ledger")
    pools = led.get("pools") or {}
    bad = 0
    for pid, pool in pools.items():
        running = int(pool.get("initial", 0) or 0)
        last = None
        for t in led.get("transactions", []) or []:
            if str(t.get("pool")) != pid or not isinstance(t.get("delta"), int):
                continue
            running += t["delta"]
            if isinstance(t.get("balance_after"), int) and t["balance_after"] != running:
                bad += 1
            last = running
        if last is not None and pool.get("current") != last:
            bad += 1
    redline("ledger_replay_100pct", bad == 0, f"{bad} 处链式不闭合")

    # ---- 3. time_day 单调（soak 全程记录）----
    days = [r.get("time_day") for r in soak_log if r.get("time_day") is not None]
    redline("time_day_monotonic", all(b >= a for a, b in zip(days, days[1:])),
            f"{len(days)} 章记录，首个倒挂 idx=" +
            next((str(i) for i, (a, b) in enumerate(zip(days, days[1:])) if b < a), "-"))

    # ---- 4. pack 红线：P1 实体永不丢 / 小票诚实 / 豁免字节 / 阶梯顺序 / breach 占比 ----
    cps = [r for r in rows if r.get("pack")]
    n_entity_zero = sum(1 for r in cps if r["pack"].get("p1_entities", 1) == 0)
    redline("p1_entities_never_empty", n_entity_zero == 0, f"{n_entity_zero}/{len(cps)} 个 checkpoint P1 空")
    n_honest = sum(1 for r in cps if r["pack"].get("honest") is False)
    redline("pack_receipt_honest", n_honest == 0, f"{n_honest} 处票面与重算不符")
    n_prot = sum(1 for r in cps if (r["pack"].get("tight") or {}).get("beats_intact") is False
                 or (r["pack"].get("tight") or {}).get("current_intact") is False)
    redline("protected_intact", n_prot == 0, f"{n_prot} 处压缩后 beats/current 字节漂移")
    ladder_bad = []
    for r in cps:
        comp = list(r["pack"].get("compressed") or [])
        tight = list((r["pack"].get("tight") or {}).get("compressed") or [])
        for seq in (comp, tight):
            idx = -1
            for s2 in seq:
                j = LADDER_SEQ.index(s2) if s2 in LADDER_SEQ else -1
                if j < 0 or j <= idx:
                    ladder_bad.append((r["ch"], seq[:3]))
                    break
                idx = j   # 阶梯顺序须单调；空层允许跳档（引擎按可得性裁）
    redline("ladder_order", not ladder_bad, f"偏离既有阶梯顺序: {ladder_bad[:3]}")
    breach = sum(1 for r in cps if r["pack"].get("hard_cap_breached"))
    ratio = breach / max(1, len(cps))
    out["watch"]["hard_cap_ratio"] = round(ratio, 3)

    # ---- 5. 未预期码集合 ----
    expected = set()
    for f in plan.get("faults", []):
        if f.get("expect_code"):
            expected.add(f["expect_code"])
    gate = faults.FAULT_GATE
    expected = {c for c in expected if not _gated(plan, c, gate)}
    benign = set(BENIGN)
    # chaos 现场码（live 雷检出属预期副作用）
    unexpected = sorted(c for c in union if c not in expected | benign and not c.startswith("__"))
    redline("no_unexpected_codes", not unexpected, f"意外码: {unexpected[:8]}")

    # ---- 6. L3 捕获率（baked 从 codes_union；live 从 chaos.json，缺则 pending）----
    det = _detect_all(book, plan, union)
    out["faults"] = det
    missed = [f for f, v in det.items() if v.get("ok") is False]
    gated = [f for f, v in det.items() if v.get("ok") is None]
    redline("fault_capture_100pct", not missed, f"漏抓: {missed}（N/A: {gated}）")

    # ---- 7. 观察项：增长与曲线 ----
    last = rows[-1] if rows else {}
    first = rows[0] if rows else {}
    growth = {}
    for tbl, v in (last.get("tables") or {}).items():
        f0 = (first.get("tables") or {}).get(tbl, v)
        growth[tbl] = {"rows": v.get("rows"), "bytes": v.get("bytes"),
                       "rows_growth": (v.get("rows", 0) or 0) - (f0.get("rows", 0) or 0)}
    top = sorted(growth.items(), key=lambda kv: -kv[1]["bytes"])[:6]
    out["watch"]["table_growth_top"] = [{"table": k, **v} for k, v in top]
    chks = [r["check_sec"] for r in rows if "check_sec" in r]
    out["watch"]["check_sec"] = {"first": chks[0] if chks else None, "last": chks[-1] if chks else None,
                                  "max": max(chks) if chks else None,
                                  "per_cp_slope": round(slope(chks), 4)}
    warns = [sum(v for k, v in (r.get("counts") or {}).items() if k in ("warnings",)) for r in rows]
    out["watch"]["warnings_slope_per_10ch"] = round(slope(warns) * 10, 3)
    shares = [r["pack"].get("p0_share", 0) for r in cps if r.get("pack")]
    out["watch"]["candidate_engine_notes"] = [
        "misunderstanding 无 plant_ch 字段：plan↔actual 对照只能到 target/status 粒度",
    ]
    out["watch"]["p0_share"] = {"first": shares[0] if shares else None, "last": shares[-1] if shares else None}

    # ---- 8. 性能基线对照 ----
    perf = {"check_p95": _p95(chks),
            "sync_sec_mean": _mean([r.get("sync_sec", 0) for r in soak_log]),
            "state_bytes_last": sum(v["bytes"] for v in (last.get("tables") or {}).values()
                                    if isinstance(v.get("bytes"), int)),
            "wall_cp": round(sum(r.get("wall", 0) for r in rows), 1)}
    out["perf"] = perf
    base = load_json(BASELINE_PATH, default={}) or {}
    slot = base.get(plan["scale"])
    if bootstrap:
        base[plan["scale"]] = {"_built_at_chapters": plan["chapters"], **perf}
        write_json(BASELINE_PATH, base)
        out["perf"]["baseline"] = "bootstrap-written"
    elif isinstance(slot, dict):
        reg = []
        for k, lim in (("check_p95", 1.2), ("sync_sec_mean", 1.2)):
            old, new = slot.get(k), perf.get(k)
            if old and new and new > old * lim:
                reg.append(f"{k} {old:.3f}→{new:.3f}")
        redline("perf_vs_baseline", not reg, "; ".join(reg))
        out["perf"]["baseline"] = slot
    else:
        out["perf"]["baseline"] = "none（首跑请 --bootstrap 建基线）"

    # ---- 9. 事件溯源折叠抽查（fold 不变量：state at 能重放出末章切面）----
    from .common import engine_cli
    rc, outp = engine_cli(["state", "at", str(plan["chapters"]), "--json", "-w", str(book)])
    ok = rc == 0
    redline("changelog_fold_state_at", ok, f"rc={rc} {outp[-160:]}")

    out["verdict"] = "PASS" if not fails else "FAIL"
    out["fails"] = fails
    write_json(d / "eval.json", out)
    if not quiet:
        _print(out, fails, det)
    return out


def _gated(plan: dict, code: str, gate: dict) -> bool:
    for fid, g in gate.items():
        # code→fid 反查（baked 期望码可能多 fid 共用：任一不 gate 即算可判）
        pass
    # 按 fault 判定：任一 fault 期望该码且未被门槛挡住 → 不禁用
    fids = [f["fault_id"] for f in plan.get("faults", []) if f.get("expect_code") == code]
    if not fids:
        return False
    return all(plan["chapters"] < gate.get(f, {}).get("min_chapters", 0)
               or (plan.get("vols") and len(plan["vols"]) < gate.get(f, {}).get("min_vols", 0))
               for f in fids)


def _detect_all(book: Path, plan: dict, union: dict) -> dict:
    """baked：从 codes_union 检出；live：从 chaos.json 检出；F16 负例专项。"""
    det: dict[str, dict] = {}
    gate = faults.FAULT_GATE
    live = load_json(book / "log" / "stress" / "chaos.json", default={}) or {}

    def ok_gate(fid: str) -> bool:
        g = gate.get(fid, {})
        return plan["chapters"] >= g.get("min_chapters", 0) and len(plan["vols"]) >= g.get("min_vols", 0)

    for f in plan.get("faults", []):
        fid = f["fault_id"]
        if fid == "F03":
            det[fid] = live.get(fid, {"ok": None, "detail": "live-pending（跑 stress chaos）"})
            if fid and not ok_gate(fid):
                det[fid] = {"ok": None, "detail": "scale N/A"}
            continue
        if not ok_gate(fid):
            det[fid] = {"ok": None, "detail": "scale N/A"}
            continue
        code = f["expect_code"]
        hit = code in union
        det[fid] = {"ok": hit, "detail": f"expect={code} in_union={hit}", "target": f.get("target")}
    for fid in ("F01", "F06", "F07", "F08", "F09", "F10", "F11", "F12", "F13"):
        det.setdefault(fid, live.get(fid, {"ok": None, "detail": "live-pending（跑 stress chaos）"}))
    # F16 负例：longline_stale 的消息不得点名跨卷线
    f16 = plan.get("f16_ids") or []
    if f16 and ok_gate("F16"):
        msgs = " ".join(union.get("longline_stale", []))
        named = [lid for lid in f16 if lid in msgs]
        roll_p = book / "state" / "rollups"
        roll_ok = any(roll_p.glob("vol_*.json")) if roll_p.is_dir() else False
        det["F16"] = {"ok": not named and roll_ok,
                      "detail": f"跨卷线被点名={named}；rollup 可见={roll_ok}"}
    elif f16:
        det["F16"] = {"ok": None, "detail": "scale N/A"}
    return det


def _print(out: dict, fails: list, det: dict) -> None:
    print("=" * 74)
    print(f" STRESS EVAL · {out['scale']} · {out['chapters']} 章 · seed={out['seed']}")
    print("=" * 74)
    for r in out["redline"]:
        print(f" {'✅' if r['ok'] else '❌'} {r['name']}" + (f" — {r['detail'][:200]}" if not r['ok'] else ""))
    fired = sum(1 for v in det.values() if v.get("ok"))
    print(f"\n L3 捕获：{fired} 检出 ｜ 明细：")
    for fid, v in sorted(det.items()):
        mark = "✅" if v.get("ok") else ("➖" if v.get("ok") is None else "❌")
        print(f"   {mark} {fid}: {str(v.get('detail'))[:130]}")
    print(f"\n 观察项：{json.dumps(out['watch'], ensure_ascii=False)[:420]}")
    print(f" 性能：{json.dumps(out['perf'], ensure_ascii=False)[:300]}")
    print(f"\n VERDICT: {out['verdict']}" + (f"（{len(fails)} 处红线挂零失败）" if not fails else ""))
    for f in fails:
        print(f"  🚫 {f}")


def _mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 4) if xs else 0


def _p95(xs):
    xs = sorted(x for x in xs if isinstance(x, (int, float)))
    if not xs:
        return 0
    return round(xs[max(0, int(len(xs) * 0.95) - 1)], 3)
