"""压力 harness 自测（门禁档）：30 章 smoke 书全流程绿 = 工具链可信，才谈得上它给出的引擎结论。

覆盖：plan 确定性（同 seed 同指纹 / 异 seed 变）→ build+soak 全链 → manifest diff 空 →
L3 live 雷现场注入全部按期望被抓（含还原后清账）→ eval 红线全绿。
零 token、零 LLM、临时目录隔离（NOVEL_STUDIO_WORKSPACE_ROOT）。

跑法（仓库根）：`.venv/bin/python -m tests.test_stress_smoke`（run_all 的 stress 套件同款）。
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

passed: list[str] = []


def step(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {name}" + (f" — {detail[:220]}" if detail and not ok else ""))
    if ok:
        passed.append(name)
    else:
        raise AssertionError(f"STRESS-SMOKE FAIL [{name}] {detail}")


def main() -> int:
    import os
    tmp = Path(tempfile.mkdtemp(prefix="novel_stress_smoke_"))
    os.environ["NOVEL_STUDIO_WORKSPACE_ROOT"] = str(tmp)
    try:
        from tests.stress import faults, generator
        from tests.stress import soak as soak_mod
        from tests.stress import eval as eval_mod
        from tests.stress.cli import load_plan
        from tests.stress.common import write_json

        print("① plan 确定性")
        plan = generator.plan_book("smoke", 42)
        again = generator.plan_book("smoke", 42)
        other = generator.plan_book("smoke", 43)
        step("同 (scale,seed) 同指纹", generator.canon_manifest(plan) == generator.canon_manifest(again))
        step("异 seed 指纹必变", generator.canon_manifest(plan) != generator.canon_manifest(other))
        step("baked 雷已编入 plan", any(f["fault_id"] == "F05" for f in plan["faults"]))

        print("② build + soak（30 章全量 sync，真闸门链）")
        book = tmp / "stress_smoke"
        log = generator.build_book(book, plan, sync_through=5)
        step("build 至 ch005", log.get("synced") == 5, str(log)[-300:])
        d = book / "log" / "stress"
        write_json(d / "stress_plan.json", {**plan, "canon": generator.canon_manifest(plan)})
        r = soak_mod.run_soak(book, plan, 6, 30, cp_every=10, resume=False)
        step("soak 收尾 ch030", r["end"] == 30)
        step("plan↔actual 指纹同轨（重载后 canon 不变）",
             generator.canon_manifest(load_plan(book)) == generator.canon_manifest(plan))

        print("③ L3 live 雷现场注入（期望全抓 + 还原清账）")
        res = faults.run_chaos(book, plan, quiet=True)
        bad = {k: v for k, v in res.items() if v.get("ok") is False}
        step("live 雷按期望被抓", not bad, str(bad))
        write_json(d / "chaos.json", res)
        from tests.stress.faults import collect_codes
        codes_after, _ = collect_codes(book)
        leaked = [c for c in ("final_drift", "time_day_mismatch", "dangling_ref",
                              "alias_shadows_name", "beats_pov_missing") if c in codes_after]
        step("还原后清账（无残留码）", not leaked, f"残留 {leaked}")

        print("④ eval 红线判定")
        out = eval_mod.run_eval(book, plan, deep=True, bootstrap=False, quiet=True)
        fails_txt = "; ".join(out.get("fails", []))
        step("verdict=PASS（基线缺失不判性能，只建档数据）", out["verdict"] == "PASS", fails_txt)
        rl = {r["name"]: r["ok"] for r in out["redline"]}
        step("manifest_diff 空", rl.get("manifest_diff_empty"))
        step("ledger 逐池重放闭合", rl.get("ledger_replay_100pct"))
        step("无未预期码", rl.get("no_unexpected_codes"), str(rl))
        det = out.get("faults", {})
        step("baked F05/F15/F17 被抓", all(det.get(f, {}).get("ok") for f in ("F05", "F15", "F17")),
             str({k: v.get("ok") for k, v in det.items()}))
        print(f"\nSTRESS-SMOKE PASS ({len(passed)}): {', '.join(passed)}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
