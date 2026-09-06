"""Checks engine rule coverage beyond the happy path."""
import json
from pathlib import Path

import pytest

from engine import checks, common, state


def _green(ws):
    """A fully Stage 0 + ch_001 ready book with no check errors/warnings."""
    book = ws.init("绿书", "星轨之上", "科幻", "林舟")
    (book/"bible/project_bible.md").write_text("# 圣经\n## 世界与规则\n- 规则一。\n", encoding="utf-8")
    vol = book/"outlines/vol_01"
    vol.mkdir(parents=True, exist_ok=True)
    (vol/"outline.md").write_text("# 卷纲\n## 本卷承诺与核心看点\n看点。\n## 本卷剧情节点与章回规划\n- **阶段一（ch_001—ch_002｜剧情）**\n  - ch_001：开篇。\n", encoding="utf-8")
    (vol/"beats").mkdir(parents=True, exist_ok=True)
    (vol/"beats/ch_001.md").write_text(
        "---\nchapter: ch_001\nvol: vol_01\nform: 暗流汇聚\n---\n\n## 本章核心戏剧目标\n- 目标：开篇。\n\n## 场景脉络\n- **场景**：\n  - 🎬 **内容**：人物登场。\n- **收束**：\n  - 📍 **章末刀口**：留钩子。\n\n## 交付契约\n- **核心看点**：明确亮点。\n- **验收要点**：\n  1. 事件发生。\n", encoding="utf-8")
    (book/"manuscript/vol_01/raw").mkdir(parents=True, exist_ok=True)
    (book/"manuscript/vol_01/raw/ch_001_v1.md").write_text("# 第1章 开篇\n\n草稿。", encoding="utf-8")
    (book/"manuscript/vol_01/final").mkdir(parents=True, exist_ok=True)
    (book/"manuscript/vol_01/final/ch_001.md").write_text(
        "# 第1章 开篇\n\n正文，人物登场，事件发生。这里写满足够字数的段落。\n" * 10, encoding="utf-8")
    report = checks.run_checks(book)
    assert report["errors"] == [], [e["msg"] for e in report["errors"]]
    assert report["warnings"] == [], [w["msg"] for w in report["warnings"]]
    return book


class TestStructuralErrors:
    def test_project_field_empty(self, ws):
        book = _green(ws)
        proj = common.load_json(book/"project.json", default={})
        proj["title"] = ""
        common.dump_json(book/"project.json", proj)
        report = checks.run_checks(book)
        assert any(e["code"] == "project_field_empty" for e in report["errors"])

    def test_param_shape_invalid(self, ws):
        book = _green(ws)
        proj = common.load_json(book/"project.json", default={})
        proj["words_target"] = [3000, 2000]
        common.dump_json(book/"project.json", proj)
        report = checks.run_checks(book)
        assert any(e["code"] == "param_shape_invalid" for e in report["errors"])

    def test_duplicate_final(self, ws):
        book = _green(ws)
        d = book/"manuscript/vol_01/final"
        # Same version as the un-versioned ch_001.md (version 0) in a different file.
        (d/"ch_001_v0.md").write_text("# 第1章 开篇\n\n同版本定稿。", encoding="utf-8")
        report = checks.run_checks(book)
        assert any(e["code"] == "duplicate_final" for e in report["errors"])

    def test_final_gap(self, ws):
        book = _green(ws)
        d = book/"manuscript/vol_01/final"
        (d/"ch_003.md").write_text("# 第3章 跳章\n\n内容。", encoding="utf-8")
        report = checks.run_checks(book)
        assert any(e["code"] == "final_gap_chapters" for e in report["errors"])

    def test_candidate_leak(self, ws):
        book = _green(ws)
        (book/"manuscript/vol_01/raw/ch_001_v1.md").write_text("candidate_foo", encoding="utf-8")
        report = checks.run_checks(book)
        assert any(e["code"] == "candidate_leak" for e in report["errors"])

    def test_latin_residue(self, ws):
        book = _green(ws)
        (book/"manuscript/vol_01/raw/ch_001_v1.md").write_text("harder 谈", encoding="utf-8")
        report = checks.run_checks(book)
        assert any(e["code"] == "latin_residue" for e in report["warnings"])


class TestLedgerChecks:
    def test_ledger_tx_order(self, ws):
        book = _green(ws)
        led = state.load_state(book, "ledger")
        led["pools"] = {"gold": {"name": "金", "unit": "两", "initial": 10, "current": 10}}
        led["transactions"] = [
            {"chapter": "ch_002", "pool": "gold", "delta": -1, "type": "expense", "subject": "后", "balance_after": 9},
            {"chapter": "ch_001", "pool": "gold", "delta": -1, "type": "expense", "subject": "先", "balance_after": 9},
            {"chapter": "ch_001", "pool": "gold", "delta": -1, "type": "expense", "subject": "先2", "balance_after": 8},
        ]
        state.save_state(book, "ledger", led)
        report = checks.run_checks(book)
        assert any(e["code"] == "ledger_tx_order" for e in report["errors"])

    def test_ledger_arith_broken(self, ws):
        book = _green(ws)
        led = state.load_state(book, "ledger")
        led["pools"] = {"gold": {"name": "金", "unit": "两", "initial": 10, "current": 10}}
        led["transactions"] = [
            {"chapter": "ch_001", "pool": "gold", "delta": -1, "type": "expense", "subject": "x", "balance_after": 5},
        ]
        state.save_state(book, "ledger", led)
        report = checks.run_checks(book)
        assert any(e["code"] == "ledger_arith_broken" for e in report["errors"])
        # current 10 vs running 9 also broken
        assert sum(1 for e in report["errors"] if e["code"] == "ledger_arith_broken") >= 1


class TestBeatRules:
    def test_beat_form_repeat_without_reason(self, ws):
        book = _green(ws)
        beats = book/"outlines/vol_01/beats"
        (beats/"ch_002.md").write_text(
            "---\nchapter: ch_002\nvol: vol_01\nform: 暗流汇聚\n---\n\n## 场景脉络\n- 场景。\n", encoding="utf-8")
        report = checks.run_checks(book)
        assert any(e["code"] == "beats_form_repeat_without_reason" for e in report["errors"])

    def test_beat_extra_front_matter(self, ws):
        book = _green(ws)
        beats = book/"outlines/vol_01/beats"
        (beats/"ch_001.md").write_text(
            "---\nchapter: ch_001\nvol: vol_01\nform: 暗流汇聚\nbad_key: x\n---\n\n## 场景脉络\n- 场景。\n", encoding="utf-8")
        report = checks.run_checks(book)
        assert any(e["code"] == "beats_fm_extra_keys" for e in report["errors"])

    def test_line_action_missing(self, ws):
        # A due line tracked in state but not mentioned in beats.
        book = _green(ws)
        prop = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
                "operation_id": "op_gun", "current": {}, "entities": [],
                "lines": [{"kind": "foreshadow", "action": "plant", "id": "GUN-001",
                           "name": "离场", "target_ch": 1, "quote": "q"}],
                "ledger": {"transactions": []},
                "timeline": {"events": [], "arcs": []}, "synopsis": {"title": "", "text": ""}}
        assert not state.apply_proposal(book, prop)["errors"]
        report = checks.run_checks(book)
        assert any(e["code"] == "line_action_missing" for e in report["warnings"])


class TestQuote:
    def test_quote_low_similarity(self, ws):
        book = _green(ws)
        proposal = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
                    "operation_id": "op1", "current": {}, "entities": [
                        {"name": "文", "type": "person", "summary": "x", "quote": "完全无关的一句话"}],
                    "lines": [], "ledger": {"transactions": []},
                    "timeline": {"events": [], "arcs": []}, "synopsis": {"title": "", "text": ""}}
        notes = checks.validate_quotes(book, "ch_001", proposal)
        assert len(notes) > 0


class TestParams:
    def test_config_suggest_empty_book(self, ws):
        out = checks.param_suggestions(_green(ws))
        assert out["final_chapters_scanned"] >= 1
