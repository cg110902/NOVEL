"""压力测试 CLI（供 `python studio.py stress ...` 或 run_all 调用；不依赖 engine.cli）。

子命令流水线（各跑各的，可反复续跑；一切以 book 目录下的 log/stress/ 为状态）：
  build --scale smoke|full|chap-hell|word-hell [--seed N] [--through K] [--fresh]
  soak  [--from N] [--to N] [--cp-every 10] [--restart]
  chaos [--fault F01,F13] [--keep]
  eval  [--bootstrap]
  report
  all   --scale ...            （build→soak→chaos→eval→report 一条龙）
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from .common import SCALES, load_json, set_workspace_root, ws_root, write_json


def _book_path(args) -> Path:
    if getattr(args, "book", None):
        return Path(args.book).resolve()
    return ws_root() / f"stress_{args.scale}"


def _plan_file(book: Path) -> Path:
    return book / "log" / "stress" / "stress_plan.json"


def load_plan(book: Path) -> dict:
    """从书目录读回 plan；chapter_meta 的 JSON 字符串键回正为 int。"""
    p = _plan_file(book)
    plan = load_json(p)
    if plan is None:
        print(f"❌ 缺 {p}（先 build）", file=sys.stderr)
        raise SystemExit(2)
    if isinstance(plan.get("chapter_meta"), dict) and plan["chapter_meta"]:
        if next(iter(plan["chapter_meta"])) != int(next(iter(plan["chapter_meta"]))):
            plan["chapter_meta"] = {int(k): v for k, v in plan["chapter_meta"].items()}
    return plan


def cmd_build(args) -> int:
    from . import generator
    set_workspace_root(args.workspace_root or Path("workspace"))
    book = _book_path(args)
    if args.fresh and book.exists():
        shutil.rmtree(book)
    plan = generator.plan_book(args.scale, args.seed)
    h = generator.canon_manifest(plan)
    d = book / "log" / "stress"
    prior = load_json(_plan_file(book), default={}) or {}
    if prior and prior.get("canon") and prior["canon"] != h:
        print(f"❌ 书已存在但 plan 指纹不同（scale/seed 漂移）：{prior['canon'][:12]} ≠ {h[:12]}；"
              "请 --fresh 或换目录", file=sys.stderr)
        return 2
    print(f"plan: scale={args.scale} seed={plan['seed']} canon={h[:16]} chapters={plan['chapters']}")
    k = plan["chapters"] if args.through is None else min(args.through, plan["chapters"])
    log = generator.build_book(book, plan, sync_through=k)
    book.mkdir(parents=True, exist_ok=True)
    d.mkdir(parents=True, exist_ok=True)
    write_json(_plan_file(book), {**plan, "canon": h})
    write_json(d / "manifest_plan.json", {"schema": "novel-studio.stress-manifest/v1",
                                          "stage": "plan", "canon": h, "scale": plan["scale"],
                                          "seed": plan["seed"], "chapters": plan["chapters"]})
    print(f"build: 已 sync 至 ch_{min(k, log.get('synced', 0)):03d}（book={book}）")
    return 0 if log.get("synced") else 1


def cmd_soak(args) -> int:
    from . import soak
    book = _book_path(args)
    plan = load_plan(book)
    start, end = args.start, (args.end or plan["chapters"])
    if args.restart:
        for f in ("soak_state.json",):
            p = book / "log" / "stress" / f
            p.unlink(missing_ok=True)
    try:
        r = soak.run_soak(book, plan, start, end, cp_every=args.cp_every, resume=not args.no_resume)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    print(f"soak done: ch{r['start']:03d}..ch{r['end']:03d} in {r['sec']}s")
    return 0


def cmd_chaos(args) -> int:
    from . import faults
    book = _book_path(args)
    plan = load_plan(book)
    only = [x.strip().upper() for x in args.fault.split(",")] if args.fault else None
    res = faults.run_chaos(book, plan, only=only, keep=args.keep)
    d = book / "log" / "stress"
    d.mkdir(parents=True, exist_ok=True)
    prior = load_json(d / "chaos.json", default={}) or {}
    prior.update({k: v for k, v in res.items() if v.get("ok") is not None or k not in prior})
    write_json(d / "chaos.json", prior)
    bad = [k for k, v in res.items() if v.get("ok") is False]
    print(f"chaos: {len(res)} 条，未过 {bad if bad else '无'}{'（--keep：现场未还原）' if args.keep else ''}")
    return 1 if bad else 0


def cmd_eval(args) -> int:
    from . import eval as _eval
    book = _book_path(args)
    plan = load_plan(book)
    out = _eval.run_eval(book, plan, deep=not args.no_deep, bootstrap=args.bootstrap)
    return 0 if out["verdict"] == "PASS" else 1


def cmd_report(args) -> int:
    from . import report
    book = _book_path(args)
    print(report.render(book))
    print(f"REPORT: {book / 'log' / 'stress' / 'REPORT.md'}")
    return 0


def cmd_all(args) -> int:
    for fn in (cmd_build, cmd_soak, cmd_chaos, cmd_eval, cmd_report):
        rc = fn(args)
        if rc != 0:
            print(f"⛔ {fn.__name__} rc={rc}（§6.3：上一 Phase 不绿，下一 Phase 不开工）", file=sys.stderr)
            return rc
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="studio.py stress", description="压力/浸泡测试 harness（零 token 剧本驱动）")
    ap.add_argument("--workspace-root", default=None, type=Path,
                    help=f"书根目录（默认 {ws_root()}；引擎要求所有 -w 落在其内）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, scale_required=True):
        p.add_argument("--scale", default="smoke" if not scale_required else None,
                       choices=sorted(SCALES), required=scale_required)
        p.add_argument("--book", default=None, help="书目录（默认 <ws_root>/stress_<scale>）")

    p = sub.add_parser("build", help="规划并落盘（init+tweaks+bible+大纲+前 K 章 sync）")
    common(p); p.add_argument("--seed", type=int, default=None); p.add_argument("--through", type=int, default=None)
    p.add_argument("--fresh", action="store_true"); p.set_defaults(func=cmd_build)

    p = sub.add_parser("soak", help="L2 浸泡：逐章 sync + checkpoint 采样（可断点续跑）")
    common(p); p.add_argument("--from", dest="start", type=int, default=2)
    p.add_argument("--to", dest="end", type=int, default=None)
    p.add_argument("--cp-every", type=int, default=10); p.add_argument("--restart", action="store_true")
    p.add_argument("--no-resume", action="store_true"); p.set_defaults(func=cmd_soak)

    p = sub.add_parser("chaos", help="L3 live 雷：注入→断言→还原")
    common(p); p.add_argument("--fault", default=None, help="逗号分隔（默认全部 live）")
    p.add_argument("--keep", action="store_true", help="保留现场不还原（调试用）"); p.set_defaults(func=cmd_chaos)

    p = sub.add_parser("eval", help="L5 判定：manifest diff + 红线 + 基线对照")
    common(p, scale_required=False); p.add_argument("--bootstrap", action="store_true",
                                                    help="用本轮数据重写基线（不判回归）")
    p.add_argument("--no-deep", action="store_true"); p.set_defaults(func=cmd_eval)

    p = sub.add_parser("report", help="渲染 REPORT.md")
    common(p, scale_required=False); p.set_defaults(func=cmd_report)

    p = sub.add_parser("all", help="build→soak→chaos→eval→report 一条龙")
    common(p); p.add_argument("--seed", type=int, default=None); p.add_argument("--through", type=int, default=None)
    p.add_argument("--fresh", action="store_true"); p.add_argument("--start", type=int, default=2)
    p.add_argument("--end", type=int, default=None); p.add_argument("--cp-every", type=int, default=10)
    p.add_argument("--restart", action="store_true"); p.add_argument("--no-resume", action="store_true")
    p.add_argument("--fault", default=None); p.add_argument("--keep", action="store_true")
    p.add_argument("--bootstrap", action="store_true"); p.add_argument("--no-deep", action="store_true")
    p.set_defaults(func=cmd_all)

    args = ap.parse_args(argv)
    if getattr(args, "seed", None) is None and hasattr(args, "scale"):
        args.seed = SCALES[args.scale]["seed_default"]
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
