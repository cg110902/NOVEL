"""崩溃恢复门禁：sync 写到一半被 kill -9 → 重跑落账 → 书必须干净。

stress 套件的 chaos 雷都是「语义坏」（坏数据走闸门），本套件测「物理坏」（进程被腰斩）——
chap-hell 量级的长跑必然遇到中断，这是入场券。做法：smoke 书建到 ch005 后，ch6..15 每章
spawn 真子进程 sync，盯到第一张 state 表 mtime 变化的瞬间（写入窗打开）随机延迟 0-30ms
SIGKILL；随后父进程按常规通道重跑该章 sync 落账。全部跑完后断言：

① 引擎视角零错误（check --json errors 为空）；
② changelog.jsonl 每一行可解析（append 被截尾行 = 撕裂，直接红）；
③ plan↔actual manifest 对账为空（ledger 逐池重放闭合、lines/clock/locked/synopsis
   全账无重复无缺失——崩溃半程最常见的伤正是「半应用」，这一条把它钉死）。

窗口以 seed=42 的 rng 决定，可复现；每章最多观察 60s（防 sync 悬挂）。
跑法（仓库根）：`.venv/bin/python -m tests.test_crash_recovery`
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.stress import generator as G  # noqa: E402
from tests.stress import common as C  # noqa: E402
from tests.stress.common import ch_token, engine_cli  # noqa: E402

CH_LO, CH_HI = 6, 15          # 崩杀试验窗（含）
KILL_DELAY_MS = (0.0, 30.0)   # 首表变动后再给的「半程写作时间」
SNAPSHOT_GRACE_S = 60.0

PASS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    assert cond, f"CRASH-RECOVERY FAIL [{name}] {detail}"
    PASS.append(name)


def _state_mt(dirp: Path) -> dict[str, int]:
    return {p.name: p.stat().st_mtime_ns for p in dirp.glob("*.json") if p.is_file()}


def _spawn_sync(book: Path, tok: str) -> subprocess.Popen:
    code = (f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
            f"from engine.cli import main; sys.exit(main(['sync','{tok}','-w',{str(book)!r},'--json']))")
    return subprocess.Popen([sys.executable, "-c", code],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            cwd=str(ROOT), env=os.environ.copy())


def _crash_one_sync(book: Path, n: int, rng: random.Random) -> str:
    """在 sync 的写入窗中段 SIGKILL。返回观察结果标记（供打印）。"""
    tok = ch_token(n)
    before = _state_mt(book / "state")
    p = _spawn_sync(book, tok)
    t0 = time.monotonic()
    killed = "no-write"
    while p.poll() is None:
        if time.monotonic() - t0 > SNAPSHOT_GRACE_S:
            p.kill(); p.wait()
            killed = "watchdog"
            break
        cur = _state_mt(book / "state")
        if cur != before:
            time.sleep(rng.uniform(*KILL_DELAY_MS) / 1000.0)
            if p.poll() is None:
                p.kill()
                p.wait()
                killed = "killed"
            else:
                killed = "won-race"
            break
        time.sleep(0.002)
    else:
        killed = "clean" if p.returncode == 0 else f"rc{p.returncode}"
    return killed


def main() -> int:
    C.set_workspace_root(Path(tempfile.mkdtemp(prefix="novel_crash_")))
    book = C.ws_root() / "crashbook"
    plan = G.plan_book("smoke", 42)
    G.build_book(book, plan, sync_through=5)
    rng = random.Random(42)
    trail = []
    for n in range(CH_LO, CH_HI + 1):
        G.materialize_chapter(book, plan, n)
        tag = _crash_one_sync(book, n, rng)
        # 收敛判据：崩溃可能留下「表已建、实体未迁」类中间态——引擎正确地拒绝对
        # 错位表寻址落账并把提案归档 failed/（ch_013.N.json 递增即重放证据）。
        # 恢复契约 = 重放最终成功（锁修复后每轮秒级），而不是「第一次就成功」。
        # 上限轮数卡死：超过它，孤儿锁 120s 陈旧抢占必然已生效——不是「不可恢复」。
        attempts, landed, r = 0, False, None
        while attempts < 4 and not landed:
            attempts += 1
            G.materialize_chapter(book, plan, n)
            r = G.sync_chapter(book, plan, n)
            # no-op 拒绝也算 landed：语义是「提案已无实际变更可合」＝崩溃前已全部应用
            landed = r["ok"] or "no-op" in r.get("out_tail", "")
        trail.append(f"ch{n:03d}:{tag}{'+' + str(attempts) + 'x-ok' if landed else '+UNRECOVERED'}")
        check(f"resync_landed_ch{n:02d}", landed, json.dumps(r, ensure_ascii=False)[:900])
    print("  trail: " + " ".join(trail))

    # ① 引擎视角干净
    rc, out = engine_cli(["check", "--json", "-w", str(book)])
    rep, _ = json.JSONDecoder().raw_decode(out.strip())
    errs = rep.get("errors", [])
    check("check_zero_errors", not errs, json.dumps(errs[:3], ensure_ascii=False)[:400])

    # ② changelog 行行可解析（截尾行=撕裂）
    cl = book / "state" / "changelog.jsonl"
    bad = 0
    for line in cl.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except ValueError:
            bad += 1
    check("changelog_no_torn_line", bad == 0, f"{bad} 行坏尾")

    # ③ 全账闭合（对账到「已同步章」截断：manifest_diff 是 soak 终局语义，
    # 中段跑必须只比对已推进范围内的线回收/末时/期末余额/locked 集/synopsis 数）
    upto = CH_HI  # 全部章节已断言 landed：对账窗 = build(CH_LO-1) + suite(CH_LO..CH_HI)
    p15 = {**plan, "chapters": upto}
    p15["lines"] = {k: {**v, **({"recall_ch": None} if v.get("recall_ch") and v["recall_ch"] > upto else {})}
                    for k, v in plan["lines"].items() if v["plant_ch"] <= upto}
    p15["clock_trace"] = [c for c in plan["clock_trace"] if c.get("ch", 0) <= upto]
    p15["ledger_replay"] = {pid: [r for r in rows if r["ch"] <= upto]
                            for pid, rows in plan["ledger_replay"].items()}
    p15["chapter_meta"] = {n: ch for n, ch in plan["chapter_meta"].items() if n <= upto}
    actual = G.manifest_finalize_actual(book, plan)
    diffs = G.manifest_diff(p15, actual)
    check("manifest_diff_empty", not diffs, str(diffs[:4])[:400])

    # 收尾卫生：崩溃不该留下 inbox 残卷（sync 归档被打断则重跑已处理，留了就说明落账半途）
    left = [p.name for p in (book / "state" / "inbox").glob("ch_*.json")]
    check("inbox_drained", not left, str(left))

    print(f"CRASH-RECOVERY PASS ({len(PASS)}): 窗口 ch{CH_LO}..{CH_HI}，"
          f"killed={sum(1 for t in trail if ':killed' in t)}/{CH_HI-CH_LO+1}，"
          f"重跑后 E=0 / 账闭合 / 无坏尾行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
