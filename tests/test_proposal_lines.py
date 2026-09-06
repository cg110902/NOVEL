"""Proposal line schema state machine tests (plant/resolve consistency)."""
import pytest

from engine import state


@pytest.fixture
def book(tmp_path):
    b = tmp_path / "b"
    b.mkdir()
    state.init_state(b)
    return b


def base(op="op1"):
    return {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
            "operation_id": op, "current": {}, "entities": [],
            "lines": [], "ledger": {"transactions": []},
            "timeline": {"events": [], "arcs": []}, "synopsis": {"title": "", "text": ""}}


def plant_line(**kw):
    line = {"kind": "foreshadow", "action": "plant", "id": "GUN-001",
            "name": "无名驾驶舱", "target_ch": "longline"}
    line.update(kw)
    return line


class TestForeshadow:
    def test_longline_plant(self, book):
        p = base(); p["lines"] = [plant_line()]
        rep = state.apply_proposal(book, p)
        assert not rep["errors"], rep["errors"]
        assert state.load_state(book, "lines")["foreshadows"][0]["id"] == "GUN-001"

    def test_resolve_exact_ch(self, book):
        p = base(); p["lines"] = [plant_line()]
        assert not state.apply_proposal(book, p)["errors"]
        p2 = base("op2")
        p2["lines"] = [{"kind": "foreshadow", "action": "resolve", "id": "GUN-001",
                        "target_ch": 5, "quote": "揭晓句"}]
        rep2 = state.apply_proposal(book, p2)
        assert not rep2["errors"], rep2["errors"]
        f = state.load_state(book, "lines")["foreshadows"][0]
        assert f["status"] == "Resolved"

    def test_resolve_unknown_id(self, book):
        p = base(); p["lines"] = [plant_line()]
        assert not state.apply_proposal(book, p)["errors"]
        p2 = base("op2")
        p2["lines"] = [{"kind": "foreshadow", "action": "resolve", "id": "NOPE", "target_ch": 5}]
        rep = state.apply_proposal(book, p2)
        assert any("不存在" in e for e in rep["errors"])

    def test_duplicate_id_plant_conflict(self, book):
        p = base(); p["lines"] = [plant_line()]
        assert not state.apply_proposal(book, p)["errors"]
        p2 = base("op2")
        p2["lines"] = [plant_line(id="GUN-001", name="改名")]
        rep = state.apply_proposal(book, p2)
        assert any("重复 plant" in e for e in rep["errors"])

    def test_resolve_before_plant_rejected(self, book):
        p = base()
        p["lines"] = [{"kind": "foreshadow", "action": "resolve", "id": "GUN-001", "target_ch": 5}]
        rep = state.apply_proposal(book, p)
        assert rep["errors"]

    def test_plant_duplicate_content_same_id_skips(self, book):
        p = base(); p["lines"] = [plant_line()]
        assert not state.apply_proposal(book, p)["errors"]
        p2 = base("op2"); p2["lines"] = [plant_line()]
        rep2 = state.apply_proposal(book, p2)
        assert not rep2["errors"]
        assert len(state.load_state(book, "lines")["foreshadows"]) == 1

    def test_auto_id_when_missing(self, book):
        p = base()
        p["lines"] = [{"kind": "foreshadow", "action": "plant", "name": "无 ID 伏笔", "target_ch": 5}]
        rep = state.apply_proposal(book, p)
        assert not rep["errors"], rep["errors"]
        assert state.load_state(book, "lines")["foreshadows"][0]["id"].startswith("GUN-")


class TestKnowledge:
    def test_plant_holders_optional(self, book):
        p = base()
        p["lines"] = [{"kind": "knowledge", "action": "plant", "id": "KNO-001",
                       "secret": "驾驶舱是密探装备", "target_ch": 5, "weight": 3}]
        rep = state.apply_proposal(book, p)
        assert not rep["errors"], rep["errors"]
        assert state.load_state(book, "lines")["knowledge"][0]["id"] == "KNO-001"

    def test_plant_holders_accepted(self, book):
        p = base()
        p["lines"] = [{"kind": "knowledge", "action": "plant", "id": "KNO-001",
                       "secret": "驾驶舱是密探装备", "target_ch": 5, "weight": 3,
                       "holders": ["温棠"], "quote": "登记码"}]
        rep = state.apply_proposal(book, p)
        assert not rep["errors"], rep["errors"]
        assert state.load_state(book, "lines")["knowledge"][0]["holders"] == ["温棠"]

    def test_holders_only_knowledge(self, book):
        p = base()
        p["lines"] = [plant_line(holders=["林舟"])]
        rep = state.apply_proposal(book, p)
        assert any("holders 仅 knowledge" in e for e in rep["errors"])

    def test_holders_type_rejected(self, book):
        p = base()
        p["lines"] = [{"kind": "knowledge", "action": "plant", "id": "KNO-001",
                       "secret": "s", "target_ch": 5, "holders": "林舟"}]
        rep = state.apply_proposal(book, p)
        assert any("holders" in e for e in rep["errors"])


class TestMisunderstanding:
    def test_parties_required(self, book):
        p = base()
        p["lines"] = [{"kind": "misunderstanding", "action": "plant", "id": "MIS-001",
                       "content": "x", "truth": "y", "target_ch": 3}]
        rep = state.apply_proposal(book, p)
        assert any("parties" in e for e in rep["errors"])

    def test_plant_and_resolve(self, book):
        p = base()
        p["lines"] = [{"kind": "misunderstanding", "action": "plant", "id": "MIS-001",
                       "parties": "林舟与何四海", "content": "误以为结盟", "truth": "只是捡到",
                       "target_ch": 3, "quote": "q"}]
        rep = state.apply_proposal(book, p)
        assert not rep["errors"], rep["errors"]
        p2 = base("op2")
        p2["lines"] = [{"kind": "misunderstanding", "action": "resolve", "id": "MIS-001",
                        "quote": "澄清句"}]
        rep2 = state.apply_proposal(book, p2)
        assert not rep2["errors"], rep2["errors"]
        assert state.load_state(book, "lines")["misunderstandings"][0]["status"] == "Resolved"

    def test_escalate_only_misunderstanding(self, book):
        p = base()
        p["lines"] = [{"kind": "foreshadow", "action": "escalate", "id": "GUN-001"}]
        rep = state.apply_proposal(book, p)
        assert any("escalate" in e for e in rep["errors"])

    def test_bad_id_rejected(self, book):
        p = base()
        p["lines"] = [{"kind": "misunderstanding", "action": "plant", "id": "MIS-1",
                       "parties": "甲乙", "content": "x", "target_ch": 3}]
        rep = state.apply_proposal(book, p)
        assert any("id" in e for e in rep["errors"])
