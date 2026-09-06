"""Core state machine tests: proposal validation, merge, idempotency, verification."""
import copy
import json
from pathlib import Path

import pytest

from engine import common, state


@pytest.fixture
def hot_book(tmp_path):
    """A bare book with seeded state files (no project.json needed)."""
    book = tmp_path / "book"
    book.mkdir()
    state.init_state(book)
    return book


def _base_proposal(chapter="ch_001", op="ch_001.reader.test"):
    return {
        "schema": "novel-studio.state-mutation/v2",
        "chapter": chapter,
        "operation_id": op,
        "current": {},
        "entities": [],
        "lines": [],
        "ledger": {"transactions": []},
        "timeline": {"events": [], "arcs": []},
        "synopsis": {"title": "", "text": ""},
    }


class TestDefaultsAndIO:
    def test_init_seeds_all(self, hot_book):
        for key in state.STATE_KEYS:
            assert (hot_book / "state" / f"{key}.json").exists()
        assert state.load_state(hot_book, "current")["time"] == ""

    def test_save_state_rejects_unknown(self, hot_book):
        data = state.load_state(hot_book, "current")
        data["evil"] = 1
        with pytest.raises(ValueError):
            state.save_state(hot_book, "current", data)


class TestValidateProposal:
    def test_minimal_valid(self, hot_book):
        p = _base_proposal()
        errs, plan = state.validate_proposal(p)
        assert errs == [], errs

    def test_requires_operation_id(self, hot_book):
        p = _base_proposal()
        del p["operation_id"]
        errs, _ = state.validate_proposal(p, "ch_001")
        assert any("operation_id" in e for e in errs)

    def test_draft_rejected(self, hot_book):
        p = _base_proposal()
        p["_draft"] = True
        errs, _ = state.validate_proposal(p)
        assert any("草稿" in e for e in errs)

    def test_chapter_mismatch(self, hot_book):
        p = _base_proposal(chapter="ch_002")
        errs, _ = state.validate_proposal(p, "ch_001")
        assert any("同步目标" in e for e in errs)

    def test_entity_unknown_key(self, hot_book):
        p = _base_proposal()
        p["entities"] = [{"name": "张三", "bad": 1}]
        errs, _ = state.validate_proposal(p)
        assert any("未知字段" in e for e in errs)

    def test_status_enum(self, hot_book):
        p = _base_proposal()
        p["entities"] = [{"name": "张三", "status": "zzz"}]
        errs, _ = state.validate_proposal(p)
        assert any("status" in e for e in errs)

    def test_line_plant_requires_target(self, hot_book):
        p = _base_proposal()
        p["lines"] = [{"kind": "foreshadow", "action": "plant", "name": "伏笔"}]
        errs, _ = state.validate_proposal(p)
        assert any("target_ch" in e for e in errs)

    def test_line_illegal_target(self, hot_book):
        p = _base_proposal()
        p["lines"] = [{"kind": "foreshadow", "action": "plant", "name": "伏笔", "target_ch": "21"}]
        errs, _ = state.validate_proposal(p)
        assert any("target_ch 非法" in e or "target_ch" in e for e in errs)

    def test_line_knowledge_holders_only(self, hot_book):
        p = _base_proposal()
        p["lines"] = [{"kind": "foreshadow", "action": "plant", "name": "伏笔", "target_ch": 3, "holders": ["x"]}]
        errs, _ = state.validate_proposal(p)
        assert any("holders 仅 knowledge" in e for e in errs)


class TestApplyMerge:
    def test_apply_proposal_simple(self, hot_book):
        p = _base_proposal(op="op1")
        p["current"] = {"time": "第一日", "present_characters": ["林舟"]}
        p["entities"] = [{"name": "林舟", "type": "person", "summary": "主角"}]
        p["lines"] = [{"kind": "foreshadow", "action": "plant", "id": "GUN-001", "name": "剑", "target_ch": 5}]
        p["ledger"] = {"pools": {"gold": {"name": "金", "unit": "两", "initial": 100}},
                       "transactions": [{"chapter": "ch_001", "pool": "gold", "delta": -10, "type": "expense", "subject": "买"}]}
        p["timeline"] = {"events": [{"time": "第一日", "event": "下雨"}]}
        p["synopsis"] = {"title": "第一章", "text": "梗概"}
        p["locked"] = [{"action": "plant", "id": "LOCK-001", "fact": "不可逆事实", "kind": "rule", "quote": "这就是不可逆事实。", "since_ch": "ch_001"}]
        p["cognition"] = [{"id": "COG-001", "character": "林舟", "kind": "fact", "content": "知道下雨", "since_ch": "ch_001", "quote": "天在下雨。"}]
        rep = state.apply_proposal(hot_book, p)
        assert not rep["errors"], rep["errors"]
        assert rep["changed"]
        assert state.load_state(hot_book, "current")["time"] == "第一日"
        ent = state.load_state(hot_book, "entities")
        assert ent["entries"][0]["name"] == "林舟"
        led = state.load_state(hot_book, "ledger")
        assert led["pools"]["gold"]["current"] == 90
        assert led["transactions"][0]["balance_after"] == 90
        assert state.load_state(hot_book, "synopsis")["chapters"]["ch_001"]["title"] == "第一章"
        assert len(state.load_state(hot_book, "locked")["entries"]) == 1
        assert len(state.load_state(hot_book, "cognition")["entries"]) == 1

    def test_apply_proposal_idempotent_same(self, hot_book):
        p = _base_proposal(op="op1")
        p["current"] = {"goal": "查"}
        assert not state.apply_proposal(hot_book, p)["errors"]
        rep = state.apply_proposal(hot_book, p)
        assert rep.get("duplicate")
        assert not rep.get("changed", False)
        assert not rep.get("errors")

    def test_apply_proposal_idempotent_conflict(self, hot_book):
        p = _base_proposal(op="op1")
        p["current"] = {"goal": "查"}
        assert not state.apply_proposal(hot_book, p)["errors"]
        p2 = copy.deepcopy(p)
        p2["current"] = {"goal": "改"}
        rep = state.apply_proposal(hot_book, p2)
        assert any("operation_id" in e and "不同内容" in e for e in rep["errors"])

    def test_content_hash_dedup_diff_op(self, hot_book):
        p = _base_proposal(op="op1")
        p["current"] = {"goal": "查"}
        assert not state.apply_proposal(hot_book, p)["errors"]
        p2 = copy.deepcopy(p); p2["operation_id"] = "op2"
        rep = state.apply_proposal(hot_book, p2)
        assert rep.get("duplicate")

    def test_bad_proposal_archives_no_write(self, hot_book):
        p = _base_proposal(op="op1")
        p["lines"] = [{"kind": "foreshadow", "action": "plant", "name": "x", "target_ch": "bad"}]
        rep = state.apply_proposal(hot_book, p)
        assert rep["errors"]
        # no marker written
        assert not (hot_book / "state" / ".applied_operations.json").exists()
        assert state.load_state(hot_book, "current")["time"] == ""


class TestVerifyData:
    def test_duplicate_entity_rejected(self, hot_book):
        # Same-name upserts in one proposal would silently collapse into one entry
        # and lose data; validate_proposal now rejects them explicitly.
        p = _base_proposal(op="op1")
        p["entities"] = [{"name": "A", "summary": "一"}, {"name": "A", "summary": "二"}]
        rep = state.apply_proposal(hot_book, p)
        assert any("重名" in e for e in rep["errors"])
        assert state.load_state(hot_book, "entities")["entries"] == []

    def test_alias_collision_rejected(self, hot_book):
        p = _base_proposal(op="op1")
        p["entities"] = [{"name": "A", "aliases": ["小A"]}, {"name": "B", "aliases": ["小A"]}]
        rep = state.apply_proposal(hot_book, p)
        assert any("别名" in e for e in rep["errors"])

    def test_same_entity_across_proposals_updates(self, hot_book):
        # Upserting the same entity in a later proposal is the normal merge path.
        p = _base_proposal(op="op1")
        p["entities"] = [{"name": "A", "summary": "旧"}]
        assert not state.apply_proposal(hot_book, p)["errors"]
        p2 = _base_proposal(op="op2")
        p2["entities"] = [{"name": "A", "summary": "新"}]
        assert not state.apply_proposal(hot_book, p2)["errors"]
        assert state.load_state(hot_book, "entities")["entries"][0]["summary"] == "新"

    def test_unregistered_present(self, hot_book):
        p = _base_proposal(op="op1")
        p["current"] = {"present_characters": ["路人"]}
        rep = state.apply_proposal(hot_book, p)
        assert any("未登记实体" in e for e in rep["errors"])

    def test_deceased_present(self, hot_book):
        p = _base_proposal(op="op1")
        p["entities"] = [{"name": "A", "type": "person", "life_status": "deceased", "quote": "q"}]
        p["current"] = {"present_characters": ["A"]}
        rep = state.apply_proposal(hot_book, p)
        assert any("已离世" in e for e in rep["errors"])

    def test_ledger_balance_recompute(self, hot_book):
        p = _base_proposal(op="op1")
        p["ledger"] = {"pools": {"gold": {"name": "金", "unit": "两", "initial": 10}},
                       "transactions": [
                           {"chapter": "ch_001", "pool": "gold", "delta": 5, "type": "income", "subject": "赚5"},
                           {"chapter": "ch_001", "pool": "gold", "delta": -3, "type": "expense", "subject": "花3"},
                       ]}
        rep = state.apply_proposal(hot_book, p)
        assert not rep["errors"], rep["errors"]
        led = state.load_state(hot_book, "ledger")
        assert led["pools"]["gold"]["current"] == 12
        assert led["transactions"][-1]["balance_after"] == 12

    def test_duplicate_lines_same_content_skipped(self, hot_book):
        p = _base_proposal(op="op1")
        line = {"kind": "foreshadow", "action": "plant", "id": "GUN-001", "name": "剑", "target_ch": 5}
        p["lines"] = [line]
        rep = state.apply_proposal(hot_book, p)
        assert not rep["errors"], rep["errors"]
        # same line again plant should be blocked (id exists, not same content? it IS same content -> skipped)
        p2 = _base_proposal(op="op2")
        p2["lines"] = [line]
        rep2 = state.apply_proposal(hot_book, p2)
        assert not rep2["errors"]
        assert len(state.load_state(hot_book, "lines")["foreshadows"]) == 1


class TestInboxPipeline:
    def test_apply_inbox_archives(self, hot_book):
        p = _base_proposal(op="op1")
        p["current"] = {"goal": "目标"}
        inbox = state.inbox_dir(hot_book)
        inbox.mkdir(parents=True, exist_ok=True)
        common.dump_json(inbox / "ch_001.json", p)
        overall = state.apply_inbox(hot_book, expect_chapter="ch_001")
        assert overall["applied"] == 1
        assert not overall["failed_target"]
        assert (inbox / "processed" / "ch_001.json").exists()
        # non-named stray stays and is reported but not blocking
        (inbox / "sweep_ch_001.json").write_text("{}", encoding="utf-8")
        overall2 = state.apply_inbox(hot_book, expect_chapter="ch_001")
        assert overall2["applied"] == 0
        assert "sweep_ch_001.json" in overall2["stray_files"]
