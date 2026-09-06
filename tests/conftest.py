"""Shared pytest fixtures for novel-studio test suite.

All tests run against an isolated workspace root (NOVEL_STUDIO_WORKSPACE_ROOT), so the
real `workspace/` directory is never touched.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
STUDIO = REPO / "studio.py"
PYTHON = sys.executable

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def run_studio(args, workspace_root=None, cwd=REPO, env_extra=None, check_main=True):
    """Run `studio.py args` in a subprocess and return CompletedProcess."""
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if workspace_root is not None:
        env["NOVEL_STUDIO_WORKSPACE_ROOT"] = str(workspace_root)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [PYTHON, str(STUDIO), *[str(a) for a in args]],
        cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    return proc


def run_json(args, workspace_root=None, cwd=REPO, env_extra=None):
    """Run studio with --json and parse stdout."""
    proc = run_studio(args, workspace_root=workspace_root, cwd=cwd, env_extra=env_extra)
    # _fail/_err functions sometimes emit a JSON error envelope on stderr; stdout is
    # contractually pure JSON for --json commands.
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"_raw_stdout": proc.stdout, "_raw_stderr": proc.stderr}
    return proc, data


class TestWorkspace:
    def __init__(self, root: Path):
        self.root = root
        self.env = {"NOVEL_STUDIO_WORKSPACE_ROOT": str(root)}

    def run(self, args, **kw):
        return run_studio(args, workspace_root=self.root, **kw)

    def run_json(self, args, **kw):
        return run_json(args, workspace_root=self.root, **kw)

    def book_dir(self, name):
        return self.root / name

    def init(self, name="测试书", title="星轨之上", genre="科幻", protagonist="林舟"):
        book = self.book_dir(name)
        proc = self.run(["init", "-w", str(book), "-t", title, "-g", genre, "-p", protagonist])
        assert proc.returncode == 0, (proc.stdout, proc.stderr)
        return book


@pytest.fixture
def ws(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return TestWorkspace(root)


@pytest.fixture
def book(ws):
    """A freshly initialised test book."""
    return ws.init()
