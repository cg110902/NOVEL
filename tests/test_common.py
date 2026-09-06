"""Unit tests for engine.common deterministic helpers and workspace guards."""
from pathlib import Path
import hashlib
import tempfile

import pytest

from engine import common


class TestChapterParsing:
    def test_digits(self):
        assert common.chapter_token_to_num("7") == 7
        assert common.chapter_token_to_num(7) == 7
        assert common.chapter_token_to_num("ch_007") == 7
        assert common.chapter_token_to_num("CH_007") == 7
        assert common.chapter_token_to_num("第3章") == 3
        assert common.chapter_token_to_num("第三章") == 3
        assert common.chapter_token_to_num("chapter7") == 7

    def test_invalid(self):
        assert common.chapter_token_to_num("ch_abc") is None
        assert common.chapter_token_to_num("") is None
        assert common.chapter_token_to_num("0") is None
        assert common.chapter_token_to_num(None) is None
        assert common.chapter_token_to_num(True) is None

    def test_chinese_compound(self):
        assert common.chapter_token_to_num("第十章") == 10
        assert common.chapter_token_to_num("第十二章") == 12
        assert common.chapter_token_to_num("第二十章") == 20
        assert common.chapter_token_to_num("第二十二章") == 22

    def test_normalize_chapter_arg(self):
        assert common.normalize_chapter_arg("ch_7") == ("ch_007", True)
        assert common.normalize_chapter_arg("ch_007") == ("ch_007", False)
        assert common.normalize_chapter_arg("10") == ("ch_010", True)
        assert common.normalize_chapter_arg("x") == (None, False)

    def test_chapter_number_from_name(self):
        assert common.chapter_number_from_name("ch_001.md") == 1
        assert common.chapter_number_from_name("ch_001_v2.md") == 1
        assert common.chapter_number_from_name("chapter12.md") == 12
        assert common.chapter_number_from_name("no-ch.md") is None


class TestWorkspace:
    def test_ensure_inside(self, tmp_path, monkeypatch):
        # workspace_root(parent) == parent/"workspace"
        root = tmp_path / "workspace"
        root.mkdir()
        book = root / "书"
        book.mkdir()
        monkeypatch.setenv("NOVEL_STUDIO_WORKSPACE_ROOT", str(root))
        assert common.ensure_workspace_inside(book) == book.resolve()
        assert common.ensure_workspace_inside(book, tmp_path) == book.resolve()
        outside = tmp_path / "outside"
        outside.mkdir()
        with pytest.raises(ValueError):
            common.ensure_workspace_inside(outside, tmp_path)

    def test_ensure_inside_requires_book(self, tmp_path):
        with pytest.raises(ValueError):
            common.ensure_workspace_inside(None)
        with pytest.raises(ValueError):
            common.ensure_workspace_inside(None, tmp_path)

    def test_list_books_only_project(self, tmp_path, monkeypatch):
        root = tmp_path / "workspace"
        root.mkdir()
        monkeypatch.setenv("NOVEL_STUDIO_WORKSPACE_ROOT", str(root))
        (root / "a").mkdir(); (root / "a" / "project.json").write_text("{}")
        (root / "b").mkdir()
        assert [p.name for p in common.list_books()] == ["a"]

    def test_workspace_root_override(self, tmp_path, monkeypatch):
        root = tmp_path / "ws"
        root.mkdir()
        monkeypatch.setenv("NOVEL_STUDIO_WORKSPACE_ROOT", str(root))
        assert common.workspace_root() == root.resolve()
        assert common.workspace_root(tmp_path) == (tmp_path / "workspace").resolve()


class TestIO:
    def test_atomic_write_and_json_roundtrip(self, tmp_path):
        p = tmp_path / "x" / "y.json"
        common.dump_json(p, {"a": 1, "b": ["x", "y"]})
        assert common.load_json(p) == {"a": 1, "b": ["x", "y"]}
        assert p.read_bytes().endswith(b"\n")

    def test_load_missing_default(self, tmp_path):
        assert common.load_json(tmp_path / "no.json", default=5) == 5
        with pytest.raises(ValueError):
            common.load_json(tmp_path / "no.json")

    def test_load_corrupt(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError):
            common.load_json(p)

    def test_safe_child_path(self, tmp_path):
        root = tmp_path / "r"; root.mkdir()
        (root / "a.txt").write_text("ok")
        assert common.safe_child_path(root, "a.txt") == (root / "a.txt")
        with pytest.raises(ValueError):
            common.safe_child_path(root, "../outside.txt")


class TestText:
    def test_cjk_count(self):
        assert common.cjk_count("你好abc") == 2
        assert common.cjk_count("") == 0

    def test_est_tokens(self):
        assert common.est_tokens("abcd") == 1
        assert common.est_tokens("你好") == 2

    def test_front_matter(self):
        text = "---\nchapter: ch_001\nform: 暗流汇聚\n---\nbody"
        fm = common.parse_front_matter(text)
        assert fm["chapter"] == "ch_001"
        assert fm["form"] == "暗流汇聚"
        assert "body" not in fm

    def test_md_section(self):
        text = "## 本章一致性\n- a\n- b\n## next\n- c\n"
        assert common.md_section(text, r"^##\s*.*一致性") == ["- a", "- b"]


class TestLock:
    def test_file_lock_acquire_release(self, tmp_path):
        p = tmp_path / "state"
        p.mkdir()
        with common.file_lock(p, name=".state.lock"):
            assert (p / ".state.lock").exists()
        assert not (p / ".state.lock").exists()

    def test_file_lock_reentrant(self, tmp_path):
        p = tmp_path / "state"; p.mkdir()
        with common.file_lock(p, name=".state.lock"):
            with common.file_lock(p, name=".state.lock"):
                pass
        assert not (p / ".state.lock").exists()


class TestHash:
    def test_canonical_hash_deterministic(self):
        a = {"b": 1, "a": [3, 2, 1]}
        b = {"a": [3, 2, 1], "b": 1}
        assert common.canonical_json_hash(a) == common.canonical_json_hash(b)
        assert len(common.canonical_json_hash(a)) == 64
