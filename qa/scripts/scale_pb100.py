# -*- coding: utf-8 -*-
"""pb100 规模复核（100 章）：耗时/崩溃/JSON 契约扫描 + 写路径探针。
与 pb_book(26)/pb60(60) 可比命令保持同名同参，输出追加到 qa/evidence/scale_report.jsonl。"""
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/home/user/NOVEL")
PY = "/home/user/.venv-novel/bin/python"
STUDIO = REPO / "studio.py"
BOOK = "/tmp/qa_root/pb100"
OUT = Path("/tmp/qa_root") / "scale_pb100_rows.txt"

CMDS = [
    ("status", ["status"]),
    ("pack ch_013", ["pack", "ch_013"]),
    ("pack ch_099", ["pack", "ch_099"]),
    ("evidence all", ["evidence", "all"]),
    ("evidence style", ["evidence", "style"]),
    ("evidence mentions", ["evidence", "mentions"]),
    ("evidence gaps", ["evidence", "gaps"]),
    ("evidence names", ["evidence", "names"]),
    ("evidence dup", ["evidence", "dup"]),
    ("audit ch_013", ["audit", "ch_013"]),
    ("check", ["check"]),
    ("index", ["index"]),
    ("index --rebuild", ["index", "--rebuild"]),
    ("dashboard", ["dashboard"]),
    ("export --txt", ["export", "--txt"]),
    ("export --views", ["export", "--views"]),
    ("recall ch_013", ["recall", "ch_013"]),
    ("simulate branch ch_013", ["simulate", "branch", "ch_013", "--count", "3"]),
    ("critic ch_013", ["critic", "ch_013"]),
    ("milestone list", ["milestone", "list"]),
    ("checkpoint ch_026", ["checkpoint", "ch_026"]),
    ("pov 陆沉舟", ["pov", "陆沉舟"]),
    ("ask 黑煞宗", ["ask", "黑煞宗"]),
    ("cockpit", ["cockpit"]),
    ("graph summary", ["graph", "summary"]),
    ("graph centrality", ["graph", "centrality"]),
    ("snapshot create pb100_marker", ["snapshot", "create", "pb100_marker"]),
]
env = dict(os.environ)
env["NOVEL_STUDIO_WORKSPACE_ROOT"] = "/tmp/qa_root"
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"

lines = []
fails = 0
for name, argv in CMDS:
    t0 = time.perf_counter()
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    proc = subprocess.run([PY, str(STUDIO), *argv, "-w", BOOK, "--json"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, cwd=str(REPO), timeout=600)
    dt = time.perf_counter() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    crashed = "Traceback" in (proc.stdout + proc.stderr)
    size = len(proc.stdout or "")
    jinfo = "BADJSON"
    if not crashed:
        try:
            d = json.loads(proc.stdout)
            if isinstance(d, dict):
                jinfo = f"keys={len(d)}"
        except Exception:
            pass
    bad = (proc.returncode != 0 or crashed or jinfo == "BADJSON")
    fails += bad
    row = (f"pb100 {name:<22} rc={proc.returncode:<3} {dt:6.2f}s rssΔ={after - before:>8}KB "
           f"crash={int(crashed)} out={size}B {jinfo}")
    lines.append(row)
    print(row + ("   <<< FAIL" if bad else ""), flush=True)

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
import re as _re
secs = [float(m.group(1)) for r in lines if (m := _re.search(r"(\d+\.\d{2})s", r))]
print(f"\n== pb100 sweep: {len(lines) - fails}/{len(lines)} ok, total {sum(secs):.1f}s")
