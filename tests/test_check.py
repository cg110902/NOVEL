"""Structural checker / review gate / parameter guard tests."""
from pathlib import Path

import pytest

from engine import checks


@pytest.fixture
def book(ws):
    b = ws.init("检查书", "标题", "科幻", "主角")
    return b


class TestBookReadiness:
    def test_empty_book_is_onboarding(self, book):
        report = checks.run_checks(book)
        assert report["ok"] is True
        assert report["onboarding"] is True
        codes = [e["code"] for e in report["infos"]]
        assert "stage0_onboarding" in codes

    def test_unfilled_slot_becomes_hard_after_writing(self, book):
        # Once there is any beats/raw/final activity, unfilled slots block.
        d = book / "outlines" / "vol_01" / "beats"
        d.mkdir(parents=True, exist_ok=True)
        (d / "ch_001.md").write_text("---\nchapter: ch_001\nvol: vol_01\nform: 暗流汇聚\n---\n\n## 场景脉络\n- 场景。\n", encoding="utf-8")
        report = checks.run_checks(book)
        assert report["ok"] is False
        codes = [e["code"] for e in report["errors"]]
        assert "unfilled_slot" in codes

    def test_full_kit_green_after_filling(self, book):
        (book / "bible" / "project_bible.md").write_text(
            "# 圣经\n\n## 世界与规则\n- 一切严格遵守虚构规则。\n", encoding="utf-8")
        vol = book / "outlines" / "vol_01"
        vol.mkdir(parents=True, exist_ok=True)
        (vol / "outline.md").write_text(
            "# 卷纲\n\n## 本卷承诺与核心看点\n看点：一个完整故事。\n\n## 本卷剧情节点与章回规划\n- **阶段一（ch_001—ch_002｜有剧情）**\n  - ch_001：开始。\n", encoding="utf-8")
        beats = vol / "beats"
        beats.mkdir(exist_ok=True)
        (beats / "ch_001.md").write_text(
            "---\nchapter: ch_001\nvol: vol_01\nform: 暗流汇聚\n---\n\n## 本章核心戏剧目标\n- 目标：完成开头。\n\n## 场景脉络\n- **场景**：\n  - 🎬 **内容**：人物登场。\n- **收束**：\n  - 📍 **章末物理刀口**：留下悬念。\n\n## 交付契约\n- **核心看点**：明确亮点。\n- **验收要点**：\n  1. 事件发生。\n", encoding="utf-8")
        final = book / "manuscript" / "vol_01" / "final"
        final.mkdir(parents=True, exist_ok=True)
        (final / "ch_001.md").write_text(
            "# 第1章 开始\n\n人物登场的正文内容。这里写满四百字，让引擎不再因为字数不足而报错。"
            "场景需要具体、有行动、有对白，还要有一些环境描写来丰富阅读。"
            "夜色从港口漫上来，主角拨开锈铁门，走进那间仓库。"
            "远处传来低沉的机器声，像是什么东西正在苏醒。\n" * 8, encoding="utf-8")
        report = checks.run_checks(book)
        # Infos about unconfigured wordlists are tolerable; any error is a failure.
        assert report["errors"] == [], [e["msg"] for e in report["errors"]]

    def test_beat_front_matter_missing_form(self, book):
        d = book / "outlines" / "vol_01" / "beats"
        d.mkdir(parents=True, exist_ok=True)
        (d / "ch_001.md").write_text("no front matter", encoding="utf-8")
        report = checks.run_checks(book)
        assert report["errors"]
        assert any(e.get("code") == "beats_missing_form" for e in report["errors"])


class TestReviewGate:
    def test_review_gate_missing(self, book):
        assert checks.review_gate(book, "ch_001")

    def test_review_gate_pass(self, book):
        rp = book / "log" / "review" / "ch_001.md"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(
            "---\nchapter: ch_001\nverdict: pass\n---\n\n## 验收\n1. ✓ 与任务书一致（“正文里有证据”）\n",
            encoding="utf-8")
        assert checks.review_gate(book, "ch_001") == []

    def test_review_gate_missing_evidence(self, book):
        rp = book / "log" / "review" / "ch_001.md"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text("---\nchapter: ch_001\nverdict: pass\n---\n\n## 验收\n1. ✓ 结论\n", encoding="utf-8")
        issues = checks.review_gate(book, "ch_001")
        assert issues
        assert any("证据" in i for i in issues)


class TestParams:
    def test_param_write_guard_state_watch_short_words(self):
        assert checks.param_write_guard("state_watch", {"injury": ["断"]})
        assert checks.param_write_guard("state_watch", {"injury": ["断骨"]}) is None
        assert checks.param_write_guard("words_target", 100) is None
        # Unknown keys are handled by validate_param_value, not the write guard.
        assert checks.param_write_guard("nope", 1) is None

    def test_validate_param_value_shapes(self):
        assert checks.validate_param_value("nope", 1)
        assert checks.validate_param_value("words_target", "bad")
        assert checks.validate_param_value("words_target", [2000, 3000]) is None
        assert checks.validate_param_value("words_target", "2000,3000") is None
        assert checks.validate_param_value("words_target", [3000, 2000])
        assert checks.validate_param_value("generic_stopwords", "word")
        assert checks.validate_param_value("generic_stopwords", ["word"]) is None

    def test_param_suggest_shape(self, book):
        out = checks.param_suggestions(book)
        assert out["kind"] == "config_suggest"
        assert out["final_chapters_scanned"] >= 0
        assert isinstance(out["suggestions"], dict)
        assert "adopt" in out
