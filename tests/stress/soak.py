"""L2 浸泡循环（方案 §3）：按 manifest_plan 逐章 sync + 每 10 章 checkpoint 采样。

- 严格执行剧本（plan），零自由发挥；断点续跑（soak_state.json 记 last_synced）；
- checkpoint 采集：表行数/体积、全量 check 耗时与码集合、pack 占比/阶梯/豁免字节、
  每 50 章加测 audit/reconcile/simulate/rollup/index/cockpit 计时、RSS；
- 快照剪枝：引擎每次 sync 自动 `<ch>_done` 快照——压力书只保留最近 KEEP_SNAPS 份，
  防 1500 章量级磁盘爆炸（快照是回滚点不是真值，剪枝不触 state_offline_edit）。
"""
from __future__ import annotations

import time
from pathlib import Path

from . import generator, metrics
from .common import (ch_token, jsonl_append, jsonl_rows, load_json, rss_mb, write_json)

KEEP_SNAPS = 3


def _stress_dir(book: Path) -> Path:
    d = Path(book) / "log" / "stress"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log(d: Path, line: str) -> None:
    with (d / "soak.out").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def _prune_snapshots(book: Path, keep: int = KEEP_SNAPS) -> int:
    root = Path(book) / "state" / "snapshots"
    if not root.is_dir():
        return 0
    snaps = sorted([p for p in root.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime)
    removed = 0
    for p in snaps[:-keep] if keep < len(snaps) else []:
        import shutil
        shutil.rmtree(p, ignore_errors=True)
        removed += 1
    return removed


def run_soak(book: Path, plan: dict, start: int, end: int, cp_every: int = 10,
             resume: bool = True) -> dict:
    book = Path(book)
    d = _stress_dir(book)
    state = load_json(d / "soak_state.json", default={}) or {}
    if resume and state.get("last_synced"):
        start = max(start, int(state["last_synced"]) + 1)
    end = min(end, plan["chapters"])
    if start > end:
        _log(d, f"soak: ch{start:03d}..ch{end:03d} 无缺口（last_synced={state.get('last_synced')}），直接收尾")
    t0 = time.perf_counter()
    done = state.get("chapters_done", 0)
    for n in range(start, end + 1):
        r = generator.sync_chapter(book, plan, n)
        if not r["ok"]:
            raise RuntimeError(f"[soak] ch{n:03d} sync 失败 rc={r['rc']}\n{r['out_tail']}\n{r['stderr_tail']}")
        ch = plan["chapter_meta"][n]
        jsonl_append(d / "soak_log.jsonl", {"ch": n, "sync_sec": r["sec"], "time_day": ch["day"],
                                            "cast": len(ch["cast"]), "moods": len(ch["moods"]),
                                            "events": len(ch["events"]), "txs": len(ch["txs"])})
        done += 1
        if n % cp_every == 0 or n == end:
            _checkpoint(book, d, plan, n)
            write_json(d / "soak_state.json", {"last_synced": n, "chapters_done": done,
                                               "codes_union": sorted(
                                                   load_json(d / "codes_union.json", default={}).keys())})
    secs = round(time.perf_counter() - t0, 1)
    # 收束：actual manifest + 最终全量 check 记录（final checkpoint 已含，但补一帧干净末态）
    _checkpoint(book, d, plan, end, final=True)
    actual = generator.manifest_finalize_actual(book, plan)
    write_json(d / "manifest_actual.json", actual)
    _log(d, f"soak 完成：ch{start:03d}..ch{end:03d}（本轮 {done} 章，{secs}s）；actual manifest 已落盘")
    return {"start": start, "end": end, "sec": secs, "last": end}


def _checkpoint(book: Path, d: Path, plan: dict, n: int, final: bool = False) -> None:
    t0 = time.perf_counter()
    report, check_sec = metrics.run_check_sample(book)
    codes = metrics.codes_of(report)
    if n % 50 == 0 or final:            # 全量 sweep：免折叠遮蔽，码集更全
        rep_full, _ = metrics.run_check_sample(book, full=True)
        for c, msgs in metrics.codes_of(rep_full).items():
            codes.setdefault(c, []).extend(msgs[:2])
    buckets = metrics.count_by_bucket(report)
    union = load_json(d / "codes_union.json", default={}) or {}
    for c, msgs in codes.items():
        union.setdefault(c, []).extend(msgs[:2])
        union[c] = union[c][:4]
    write_json(d / "codes_union.json", union)
    pack_m = metrics.pack_sample(book, ch_token(n), tight_cap=200)
    tables = metrics.state_table_stats(book)
    row = {"ch": n, "final": final, "check_sec": round(check_sec, 3), "wall": round(time.perf_counter() - t0, 2),
           "codes": sorted(codes), "counts": buckets, "pack": pack_m, "rss_mb": round(rss_mb(), 1),
           "tables": {k: v for k, v in tables.items()}}
    if n % 50 == 0 or final:
        row["misc"] = metrics.misc_timings(book, plan, n)
    jsonl_append(d / "metrics.jsonl", row)
    removed = _prune_snapshots(book)
    _log(d, f"cp ch{n:03d}｜check {check_sec:0.2f}s｜E/W/I={buckets.get('errors')}/"
            f"{buckets.get('warnings')}/{buckets.get('infos')}｜pack {pack_m.get('total')}/{pack_m.get('cap')}"
            f"（p0 {pack_m.get('p0_share')}）｜codes={len(codes)}｜剪快照{removed}")
