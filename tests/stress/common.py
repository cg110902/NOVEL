"""harness 公共件：进程内引擎调用、JSONL、规范哈希、规模常量。"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent   # 仓库根（tests/stress/ 上两级）
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# 规模档位（方案 §1，"50~100 万字"翻译成工程数字；chapters 为 soak 终点）
# ---------------------------------------------------------------------------
SCALES: dict[str, dict] = {
    # 回归档：smoke-scale，30 章 ≈ 10 万字，1 卷。PR 必跑（test_stress_smoke）。
    "smoke": dict(chapters=30, vols=1, entities=30, lines_total=45,
                  words_mu=3500, words_sd=800, words_min=1500, words_max=6000,
                  ev_per_ch=4, tx_per_ch=6, bible_chars=0,   # 0 = 保持模板默认
                  band=[1500, 6500], seed_default=42),
    # 夜跑档：full-scale，300 章 ≈ 105 万字，3 卷。首跑只建基线。
    "full": dict(chapters=300, vols=3, entities=250, lines_total=600,
                 words_mu=3500, words_sd=800, words_min=1500, words_max=6000,
                 ev_per_ch=8, tx_per_ch=20, bible_chars=8000,
                 band=[1500, 6500], seed_default=42),
    # 章数地狱：1500 章 × 200~600 字，5 卷。单轴压章数（表行数/扫描/窗口/文件数）。
    "chap-hell": dict(chapters=1500, vols=5, entities=250, lines_total=600,
                      words_mu=420, words_sd=90, words_min=220, words_max=800,
                      ev_per_ch=2, tx_per_ch=3, bible_chars=1500,
                      band=[150, 2000], seed_default=42),
    # 字数地狱：200 章 × 5000 字，2 卷。单轴压字数（单文件体积/正则回溯/内存/pack 预算）。
    "word-hell": dict(chapters=200, vols=2, entities=120, lines_total=300,
                      words_mu=5000, words_sd=500, words_min=4000, words_max=6400,
                      ev_per_ch=6, tx_per_ch=15, bible_chars=8000,
                      band=[3500, 6500], seed_default=42),
}

# ---------------------------------------------------------------------------
# 引擎进程内调用（避免每章 python 冷启动；完整走 CLI→命令层，保真门禁链）
# ---------------------------------------------------------------------------

def engine_cli(argv: list[str]) -> tuple[int, str]:
    """进程内调用 engine.cli.main(argv)。返回 (rc, 捕获的 stdout)。

    注意：main 的异常出口在引擎侧（rc=1 + stderr 提示），这里只收 stdout；
    rc != 0 由调用方决定 fail-fast 还是记录。workspace 根由环境变量控制，
    调用方在 stress 入口统一 setenv（NOVEL_STUDIO_WORKSPACE_ROOT）。
    """
    from engine import cli as engine_cli_mod
    buf = io.StringIO()
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        try:
            rc = engine_cli_mod.main(list(argv)) or 0
        except SystemExit as exc:      # argparse 用法错走 SystemExit(2)
            rc = int(exc.code or 2)
        except Exception as exc:       # noqa: BLE001 —— harness 层兜底，转成 rc=99 带原文
            return 99, buf.getvalue() + f"\n[harness] engine raised {type(exc).__name__}: {exc}"
    return int(rc), buf.getvalue()


def timed_engine_cli(argv: list[str]) -> tuple[int, str, float]:
    from engine import cli as engine_cli_mod
    buf = io.StringIO()
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        try:
            rc = engine_cli_mod.main(list(argv)) or 0
        except SystemExit as exc:
            rc = int(exc.code or 2)
    return int(rc), buf.getvalue(), time.perf_counter() - t0


# ---------------------------------------------------------------------------
# 路径与 IO
# ---------------------------------------------------------------------------

def ws_root() -> Path:
    """压力书的工作区根：NOVEL_STUDIO_WORKSPACE_ROOT（沙箱内一般注入）。"""
    v = os.environ.get("NOVEL_STUDIO_WORKSPACE_ROOT", "").strip()
    return Path(v).expanduser().resolve() if v else ROOT / "workspace"


def ch_token(n: int) -> str:
    return f"ch_{n:03d}"


def vol_token(i: int) -> str:
    return f"vol_{i:02d}"


def jsonl_append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def jsonl_rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue          # 断点续跑容忍尾行残缺（与 changelog 同口径）
    return out


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:
            return default
        raise


# ---------------------------------------------------------------------------
# 确定性哈希（manifest 复现校验用）
# ---------------------------------------------------------------------------
VOLATILE_KEYS = {"created_at", "updated_at", "sealed_at", "sealed_at_ts", "ts", "timestamp"}


def canon_hash(obj) -> str:
    import hashlib
    stripped = _strip_volatile(obj)
    blob = json.dumps(stripped, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _strip_volatile(node):
    if isinstance(node, dict):
        return {k: _strip_volatile(v) for k, v in sorted(node.items()) if k not in VOLATILE_KEYS}
    if isinstance(node, list):
        return [_strip_volatile(x) for x in node]
    return node


def rss_mb() -> float:
    """当前进程峰值 RSS（MB，Linux/macOS）。psutil 不在栈内，用 stdlib resource。"""
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux 为 KB，macOS 为字节
    return (peak / 1024.0) if peak > 10 ** 7 else (peak / 1024.0 if sys.platform == "linux" else peak / 1024 ** 2)


def set_workspace_root(path: Path | str) -> None:
    os.environ["NOVEL_STUDIO_WORKSPACE_ROOT"] = str(Path(path).expanduser().resolve())


def slope(y: list[float]) -> float:
    """最小二乘斜率（按序号 x=0..n-1）；n<2 → 0。"""
    n = len(y)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(y) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (yy - my) for x, yy in zip(xs, y)) / den if den else 0.0
