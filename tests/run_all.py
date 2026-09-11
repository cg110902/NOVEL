"""门禁三件套统一跑批器（stdlib only，零新增依赖）。

一条命令跑全「改引擎必跑」的门禁（README 第六节口径），并给出逐项耗时与总 verdict：

    .venv/bin/python -m tests.run_all              # 全量（parity → smoke → gates）
    .venv/bin/python -m tests.run_all --only parity smoke   # 只跑快档（提交前顺手验）
    .venv/bin/python -m tests.run_all --list       # 看有哪些测试与各自的定位

设计约束（与 tests/__init__.py 一致）：
- 不引入 pytest，挂 CI 同样零依赖；各测试模块本身即 `main()` 独立进程；
- 用 subprocess 逐个跑：门禁之间不串全局状态（test_gates 会临时改 HISTORY_WINDOW /
  PACK_TOKEN_CAP 等模块级变量，必须进程隔离）；
- 任一模块非零退出 → 本跑批器非零退出（供 CI/钩子直接消费）；
- 超时兜底：默认 parity/smoke 600s、gates 1800s，防 e2e 卡死无人知。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (别名, 模块, 说明, 超时秒)
SUITES = [
    ("parity", "tests.test_docs_parity", "文档↔代码口径对账（命令数/码数/表数/字段数/schema 新鲜度）", 600),
    ("smoke", "tests.test_smoke", "冒烟：临时书整章 init→beats→成稿→提案→audit→sync→check→pack", 900),
    ("gates", "tests.test_gates", "门禁触发：判定边界 + 违规注入 e2e（临时书 × 多套）", 1800),
    ("stress", "tests.test_stress_smoke", "压力 harness 自测：30 章 smoke 书全链（plan 确定性/浸泡/雷库/判定）", 1200),
    ("crash", "tests.test_crash_recovery", "崩溃恢复：sync 写入窗 SIGKILL×10 章（含死亡章），重跑必须收敛且账闭合", 600),
]
ORDER = [a for a, *_ in SUITES]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tests.run_all", description="门禁三件套统一跑批")
    ap.add_argument("--only", nargs="+", metavar="SUITE", choices=ORDER,
                    help=f"只跑指定套件（默认全量：{' '.join(ORDER)}）")
    ap.add_argument("--list", action="store_true", help="列出套件后退出")
    ap.add_argument("--timeout-scale", type=float, default=1.0,
                    help="超时缩放系数（慢机/CI 调大，如 2.0）")
    args = ap.parse_args(argv)

    if args.list:
        for alias, mod, desc, to in SUITES:
            print(f"{alias:<7} {mod:<28} ~{to // 60}min上限  {desc}")
        return 0

    selected = args.only or ORDER
    results: list[tuple[str, str, float, int]] = []
    print("=" * 72)
    for alias in selected:
        mod, desc, to = next((m, d, t) for a, m, d, t in SUITES if a == alias)
        timeout = max(60, int(to * args.timeout_scale))
        print(f"▶ {alias}: {desc}\n  $ {sys.executable} -m {mod}（超时 {timeout}s）", flush=True)
        t0 = time.monotonic()
        try:
            cp = subprocess.run([sys.executable, "-m", mod], cwd=ROOT,
                                capture_output=True, text=True, timeout=timeout)
            rc = cp.returncode
            out = (cp.stdout or "") + (cp.stderr or "")
        except subprocess.TimeoutExpired as exc:
            rc = -1
            partial = exc.stdout or b""
            out = "❌ TIMEOUT\n" + (partial.decode("utf-8", "replace") if isinstance(partial, bytes) else str(partial))
        dt = time.monotonic() - t0
        tail = "\n".join(out.strip().splitlines()[-3:]) or "（无输出）"
        print(f"  {'✅' if rc == 0 else '❌'} rc={rc} 用时 {dt:0.1f}s\n  {tail}\n")
        results.append((alias, mod, dt, rc))

    print("=" * 72)
    bad = [r for r in results if r[3] != 0]
    for alias, mod, dt, rc in results:
        print(f"{'PASS' if rc == 0 else 'FAIL'} {alias:<7} {dt:7.1f}s  rc={rc}")
    if bad:
        print(f"\n🚫 GATES RED（{len(bad)}/{len(results)}）：失败套件 = {', '.join(b[0] for b in bad)}")
        print("   按 README 第六节：改引擎的口径挂了就回去改文档/模型，不要反过来改小数字。")
        return 1
    print(f"\n🏁 GATES GREEN（{len(results)}/{len(results)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
