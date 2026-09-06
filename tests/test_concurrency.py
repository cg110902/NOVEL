"""Concurrency guards: cross-process file lock and inbox merge without lost updates."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from engine import common, state

REPO = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def _sub_env():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _python_code(script: str):
    return [PYTHON, "-c", script]


def _wait_for(path: Path, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.02)
    return False


class TestFileLock:
    def test_same_thread_reentrant(self, tmp_path):
        d = tmp_path / "book"
        d.mkdir()
        with common.file_lock(d, name=".concurrency.lock"):
            with common.file_lock(d, name=".concurrency.lock"):
                assert (d / ".concurrency.lock").is_file()

    def test_cross_process_exclusive_and_release(self, tmp_path):
        d = tmp_path / "book"
        d.mkdir()
        ready = tmp_path / "ready"
        release = tmp_path / "release"
        holder = _python_code(
            "import sys,time,pathlib\n"
            "from engine import common\n"
            "d=pathlib.Path(sys.argv[1]); ready=pathlib.Path(sys.argv[2]); release=pathlib.Path(sys.argv[3])\n"
            "with common.file_lock(d, name='.concurrency.lock', timeout=5):\n"
            "    ready.write_text('ok')\n"
            "    while not release.exists(): time.sleep(0.01)\n"
        )
        proc = subprocess.Popen(holder + [str(d), str(ready), str(release)],
                                cwd=str(REPO), env=_sub_env(),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert _wait_for(ready), "holder did not acquire lock"
        entered = False
        start = time.monotonic()
        try:
            with common.file_lock(d, name=".concurrency.lock", timeout=0.3):
                entered = True
        except TimeoutError:
            entered = False
        assert not entered, "second process should not acquire while holder is active"
        assert time.monotonic() - start < 5, "timeout path did not return promptly"
        release.write_text("go", encoding="utf-8")
        proc.wait(timeout=10)
        assert proc.returncode == 0, proc.stderr
        with common.file_lock(d, name=".concurrency.lock", timeout=2):
            assert (d / ".concurrency.lock").is_file()


def _proposal(op: str, field: str, value: str):
    return {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": "ch_001",
        "operation_id": op,
        "current": {field: value},
        "entities": [],
        "lines": [],
        "ledger": {"transactions": []},
        "timeline": {"events": [], "arcs": []},
        "synopsis": {"title": "", "text": ""},
    }


def test_apply_inbox_concurrent_no_lost_update(ws, tmp_path):
    """Concurrent apply_inbox calls must be serialised by .state.lock.

    Without the lock, two processes could both read state before either writes,
    and the later writer would clobber the other process's field. With the lock,
    all fields survive regardless of scheduling.
    """
    book = ws.init("并发书", "星轨之上", "科幻", "林舟")
    fields = {"goal": "追寻真相", "mood": "警惕", "injury": "轻伤",
              "location": "废料场", "equipment": "扳手", "situation": "被跟踪"}
    inbox = book / "state" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    for i, (field, value) in enumerate(sorted(fields.items())):
        # ch_001.0.json ... ch_001.5.json — all match the inbox proposal regex.
        (inbox / f"ch_001.{i}.json").write_text(
            json.dumps(_proposal(f"op_conc_{i}", field, value), ensure_ascii=False),
            encoding="utf-8")

    worker = _python_code(
        "import sys,pathlib\n"
        "from engine import state\n"
        "book=pathlib.Path(sys.argv[1])\n"
        "state.apply_inbox(book, expect_chapter='ch_001')\n"
    )
    # Launch several workers at once. The lock must let exactly one apply all
    # proposals and then let the rest no-op safely.
    procs = [subprocess.Popen(worker + [str(book)],
                              cwd=str(REPO), env=_sub_env(),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(4)]
    for pr in procs:
        out, err = pr.communicate(timeout=60)
        assert pr.returncode == 0, f"worker failed: {err}"
    cur = state.load_state(book, "current")
    for field, value in fields.items():
        assert cur.get(field) == value, f"lost field {field}: {cur.get(field)!r} != {value!r}"
