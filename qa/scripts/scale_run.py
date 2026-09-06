"""Time + peak-RSS battery over CLI commands on the pressure book."""
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
BOOK = "/tmp/qa_root/pb_book"

CMDS = [
    ("status", ["status"]),
    ("pack ch_013", ["pack", "ch_013"]),
    ("evidence all", ["evidence", "all"]),
    ("evidence mentions", ["evidence", "mentions"]),
    ("evidence gaps", ["evidence", "gaps"]),
    ("audit ch_013", ["audit", "ch_013"]),
    ("graph summary", ["graph", "summary"]),
    ("graph centrality", ["graph", "centrality"]),
    ("check", ["check"]),
    ("index", ["index"]),
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
    ("proposal auto ch_013", ["proposal", "auto", "ch_013"]),
    ("cockpit", ["cockpit"]),
]
env = dict(os.environ)
env["NOVEL_STUDIO_WORKSPACE_ROOT"] = "/tmp/qa_root"
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"

rows = []
for name, argv in CMDS:
    t0 = time.perf_counter()
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    proc = subprocess.run([PY, str(STUDIO), *argv, "-w", BOOK, "--json"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, cwd=str(REPO))
    dt = time.perf_counter() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    crashed = "Traceback" in (proc.stdout + proc.stderr)
    out_head = (proc.stdout or "").strip().splitlines()
    size = len(proc.stdout or "")
    jinfo = ""
    if not crashed:
        try:
            d = json.loads(proc.stdout)
            if isinstance(d, dict):
                jinfo = f"keys={len(d)}"
        except Exception:
            jinfo = "BADJSON"
    rows.append((name, proc.returncode, dt, after - before, crashed, size, jinfo))
    print(f"{name:<26} rc={proc.returncode:<3} {dt:6.2f}s rssΔ={after - before:>8}KB "
          f"crash={int(crashed)} out={size}B {jinfo}", flush=True)

print("\n=== JSON ===")
print(json.dumps([{"cmd": r[0], "rc": r[1], "sec": round(r[2], 3),
                   "rss_delta_kb": r[3], "crashed": r[4], "out_bytes": r[5],
                   "json": r[6]} for r in rows], ensure_ascii=False, indent=1))
