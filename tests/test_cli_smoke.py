"""CLI smoke tests for the parser/argparse surface, help, errcodes, workspace gates."""
import json
from pathlib import Path

import pytest

from conftest import REPO  # noqa: F401  (ensures sys.path)


class TestHelp:
    def test_help_text(self, ws):
        p = ws.run(["help"])
        assert p.returncode == 0, p.stderr
        assert "Novel Studio" in p.stdout

    def test_help_json(self, ws):
        p, data = ws.run_json(["help", "--json"])
        assert p.returncode == 0
        assert data["version"]
        assert isinstance(data["commands"], list)

    def test_errcodes_json(self, ws):
        p, data = ws.run_json(["errcodes", "--json"])
        assert p.returncode == 0
        assert isinstance(data["codes"], list)
        assert len(data["codes"]) > 0


class TestWorkspaceErrors:
    def test_no_book(self, ws):
        # A workspace with no book at all (root empty)
        p, data = ws.run_json(["status", "--json"])
        assert p.returncode == 1
        assert data["exists"] is False

    def test_multiple_books(self, ws):
        ws.init("甲", "甲", "a", "A")
        ws.init("乙", "乙", "b", "B")
        p, data = ws.run_json(["status", "--json"])
        assert p.returncode == 2
        assert data["reason"] == "multiple_books"
        p, data = ws.run_json(["check", "--json"])
        assert p.returncode == 2
        assert data["code"] == "multiple_books"

    def test_out_of_bounds(self, ws):
        outside = Path(ws.root.parent) / "outside"
        outside.mkdir(exist_ok=True)
        p, data = ws.run_json(["status", "-w", str(outside), "--json"])
        assert p.returncode == 1
        assert data.get("reason") == "workspace_out_of_bounds" or "越界" in p.stderr


class TestInit:
    def test_init_creates_book(self, ws):
        b = ws.init("角色", "木偶", "悬疑", "木心")
        assert (b / "project.json").exists()
        assert (b / "state" / "current.json").exists()
        assert (b / "bible" / "project_bible.md").exists()
        p = ws.run(["status", "-w", str(b), "--json"])
        assert p.returncode == 0

    def test_init_refuses_reinit(self, ws):
        b = ws.init("角色")
        p = ws.run(["init", "-w", str(b)])
        assert p.returncode == 1

    def test_init_refuses_nonempty_unknown_dir(self, ws):
        d = ws.book_dir("非空目录")
        d.mkdir()
        (d / "junk.txt").write_text("x", encoding="utf-8")
        p = ws.run(["init", "-w", str(d)])
        assert p.returncode == 1
        assert "拒绝写入" in p.stdout
        assert not (d / "project.json").exists()

    def test_init_clean_keeps_final(self, ws):
        b = ws.init("书")
        raw = b / "manuscript/vol_01/raw"
        final = b / "manuscript/vol_01/final"
        raw.mkdir(parents=True, exist_ok=True)
        final.mkdir(parents=True, exist_ok=True)
        (raw / "ch_001_v1.md").write_text("raw", encoding="utf-8")
        (final / "ch_001.md").write_text("final", encoding="utf-8")
        p = ws.run(["init", "-w", str(b), "--clean"])
        assert p.returncode == 0
        assert not (raw / "ch_001_v1.md").exists()
        assert (final / "ch_001.md").exists()


class TestConfig:
    def test_list_guide(self, ws, book):
        p = ws.run(["config", "list", "-w", str(book), "--json"])
        assert p.returncode == 0
        p = ws.run(["config", "guide", "-w", str(book), "--json"])
        assert p.returncode == 0

    def test_set_get_unset(self, ws, book):
        p = ws.run(["config", "set", "generic_stopwords", '["废料场"]', "-w", str(book), "--json"])
        assert p.returncode == 0
        p, data = ws.run_json(["config", "get", "generic_stopwords", "-w", str(book), "--json"])
        assert p.returncode == 0
        assert data["value"] == ["废料场"]
        p = ws.run(["config", "unset", "generic_stopwords", "-w", str(book), "--json"])
        assert p.returncode == 0

    def test_invalid_shape(self, ws, book):
        p = ws.run(["config", "set", "words_target", '"hi"', "-w", str(book), "--json"])
        assert p.returncode == 2

    def test_unknown_key(self, ws, book):
        p = ws.run(["config", "get", "nope", "-w", str(book), "--json"])
        assert p.returncode == 2


class TestBadArgs:
    def test_unknown_chapter(self, ws, book):
        p = ws.run(["pack", "ch_zzz", "-w", str(book), "--json"])
        assert p.returncode == 2

    def test_bad_evidence_kind(self, ws, book):
        p = ws.run(["evidence", "nope", "-w", str(book), "--json"])
        assert p.returncode == 2

    def test_state_unknown_field(self, ws, book):
        p = ws.run(["state", "set", "current.bad", "x", "-w", str(book), "--json"])
        assert p.returncode == 1
