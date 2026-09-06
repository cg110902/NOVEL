# -*- coding: utf-8 -*-
"""CLI 回归补测：recall/simulate/export/dashboard/critic/checkpoint/index。
用法: python cli_regress.py [-w BOOK] [--write]   （--write 允许 branch/critic 落盘）
每条命令校验: rc==0、stdout 可解析为 JSON、envelope 契约字段、产物文件存在。
结果落盘 cli_regress_report.jsonl，stdout 只回显摘要行。"""
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path("/home/user/NOVEL")
PY = "/home/user/.venv-novel/bin/python"
BOOK = "/tmp/qa_root/pb_book"
ALLOW_WRITE = "--write" in sys.argv

CASES = [
    ("recall.default",        ["recall", "--json"], {}),
    ("recall.ch_013",         ["recall", "ch_013", "--json"], {}),
    ("recall.err_epoch",      ["recall", "ch_999", "--json"], {"rc_any": True}),
    ("simulate.impact.kill",  ["simulate", "impact", "-e", "苏九娘", "-a", "kill", "--json"], {}),
    ("simulate.impact.line",  ["simulate", "impact", "-l", "KNO-001", "-a", "reveal", "--json"], {}),
    ("simulate.impact.bad",   ["simulate", "impact", "-e", "查无此人", "-a", "kill", "--json"], {"rc_any": True}),
    ("simulate.branch",       ["simulate", "branch", "--count", "3", "--json"] + (["--write"] if ALLOW_WRITE else []), {}),
    ("export.txt",            ["export", "--txt", "--json"], {"files": ["export/压力测试书pb.txt"]}),
    ("export.views",          ["export", "--views", "--json"], {"files": ["export/views/state_view.md"]}),
    ("dashboard",             ["dashboard", "--json"], {"files": ["export/views/dashboard.html"]}),
    ("critic.default",        ["critic", "--json"], {}),
    ("critic.ch_010",         ["critic", "ch_010", "--json"], {}),
    ("critic.write",          ["critic", "ch_010", "--write", "--json"], {"files": ["log/critic/ch_010.md"]}),
    ("critic.err_badch",      ["critic", "ch_ABC", "--json"], {"rc_any": True}),
    ("checkpoint.default",    ["checkpoint", "--json"], {}),
    ("checkpoint.ch_010",     ["checkpoint", "ch_010", "--json"], {}),
    ("checkpoint.err",        ["checkpoint", "ch_999", "--json"], {"rc_any": True}),
    ("index.sync",            ["index", "--json"], {}),
    ("index.rebuild",         ["index", "--rebuild", "--json"], {}),
    ("errcodes",              ["errcodes", "--json"], {}),
    ("help.list",             ["help", "--json"], {}),
]

def main():
    env = {"PYTHONUTF8": "1", "NOVEL_STUDIO_WORKSPACE_ROOT": pathlib.Path(BOOK).parent.as_posix(),
           "PATH": "/usr/bin:/bin"}
    rows = []
    for name, args, opts in CASES:
        t0 = time.time()
        cp = subprocess.run([PY, "studio.py", *args, "-w", BOOK],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        dt = round(time.time() - t0, 2)
        out = cp.stdout.strip()
        parsed = None
        json_ok = False
        try:
            parsed = json.loads(out)
            json_ok = True
        except Exception:
            pass
        row = {"case": name, "rc": cp.returncode, "secs": dt, "json_ok": json_ok}
        if parsed is not None:
            row["keys"] = sorted(parsed.keys())[:12]
            err = parsed.get("error") or (parsed.get("payload") or {}).get("error")
            if err:
                row["err"] = str(err)[:80]
            if parsed.get("crashed") is not None:
                row["crashed"] = parsed["crashed"]
            if parsed.get("ok") is not None:
                row["ok"] = parsed["ok"]
            if parsed.get("code") is not None:
                row["code"] = parsed["code"]
        # rc 契约：非 rc_any 用例必须 rc==0
        if not opts.get("rc_any") and cp.returncode != 0:
            row["FAIL"] = f"rc={cp.returncode}"
        if opts.get("rc_any") and cp.returncode == 0 and not json_ok:
            row["note"] = "rc0 但输出非 JSON"
        # 产物文件
        for rel in opts.get("files", []):
            f = pathlib.Path(BOOK) / rel
            if not f.is_file() or f.stat().st_size == 0:
                row["FAIL"] = row.get("FAIL", "") + f" 缺产物 {rel}"
        # stderr 摘要
        if cp.stderr.strip():
            row["stderr"] = cp.stderr.strip()[:120]
        rows.append(row)
    (pathlib.Path("/tmp/qa_root") / "cli_regress_report.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    nf = sum(1 for r in rows if "FAIL" in r)
    for r in rows:
        flag = "FAIL" if "FAIL" in r else ("note" if r.get("note") else "ok")
        print(f"[{flag}] {r['case']:<22} rc={r['rc']} json={r['json_ok']} "
              f"{r.get('secs', '')}s keys={r.get('keys', [])[:6]}")
        for k in ("FAIL", "err", "stderr", "note"):
            if r.get(k):
                print(f"        {k}: {r[k]}")
    print(f"\n== {len(rows) - nf}/{len(rows)} ok; report: /tmp/qa_root/cli_regress_report.jsonl")

if __name__ == "__main__":
    main()
