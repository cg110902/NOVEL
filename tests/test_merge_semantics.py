"""Proposal merge semantics: ledger/timeline/prereq/cross-chapter revision."""
import pytest

from engine import state


@pytest.fixture
def book(tmp_path):
    b = tmp_path / "b"
    b.mkdir()
    state.init_state(b)
    return b


def base(op="op1", ch="ch_001"):
    return {"schema": "novel-studio.state-mutation/v2", "chapter": ch,
            "operation_id": op, "current": {}, "entities": [], "lines": [],
            "ledger": {"transactions": []}, "timeline": {"events": [], "arcs": []},
            "synopsis": {"title": "", "text": ""}}


class TestLedger:
    def test_new_pool_requires_initial(self, book):
        p = base()
        p["ledger"] = {"pools": {"gold": {"name": "金", "unit": "两"}}}
        rep = state.apply_proposal(book, p)
        assert any("initial" in e for e in rep["errors"])

    def test_new_pool_rejects_unknown_key(self, book):
        p = base()
        p["ledger"] = {"pools": {"gold": {"name": "金", "unit": "两", "initial": 5, "intial": 3}}}
        rep = state.apply_proposal(book, p)
        assert any("未知字段" in e for e in rep["errors"])

    def test_new_pool_rejects_declared_current(self, book):
        p = base()
        p["ledger"] = {"pools": {"gold": {"name": "金", "unit": "两", "initial": 5, "current": 5}}}
        rep = state.apply_proposal(book, p)
        assert any("current" in e for e in rep["errors"])

    def test_existing_pool_initial_frozen(self, book):
        p = base()
        p["ledger"] = {"pools": {"gold": {"name": "金", "unit": "两", "initial": 10}},
                       "transactions": [{"chapter": "ch_001", "pool": "gold", "delta": -3, "type": "expense", "subject": "买"}]}
        assert not state.apply_proposal(book, p)["errors"]
        p2 = base("op2")
        p2["ledger"] = {"pools": {"gold": {"name": "金", "unit": "两", "initial": 99}}}
        rep = state.apply_proposal(book, p2)
        assert any("禁止修改 initial" in e for e in rep["errors"])

    def test_undeclared_pool_transaction_rejected(self, book):
        p = base()
        p["ledger"] = {"transactions": [{"chapter": "ch_001", "pool": "nope", "delta": -1, "type": "expense", "subject": "x"}]}
        rep = state.apply_proposal(book, p)
        assert any("未声明" in e for e in rep["errors"])
        assert state.load_state(book, "ledger")["transactions"] == []

    def test_duplicate_transaction_skipped(self, book):
        tx = {"chapter": "ch_001", "pool": "gold", "delta": -10, "type": "expense", "subject": "买票"}
        p = base()
        p["ledger"] = {"pools": {"gold": {"name": "金", "unit": "两", "initial": 100}}, "transactions": [tx]}
        assert not state.apply_proposal(book, p)["errors"]
        p2 = base("op2")
        p2["ledger"] = {"transactions": [dict(tx)]}
        rep2 = state.apply_proposal(book, p2)
        assert not rep2["errors"]
        assert any("重复" in w or "幂等" in w for w in rep2["warnings"])
        assert len(state.load_state(book, "ledger")["transactions"]) == 1

    def test_balance_recomputed(self, book):
        p = base()
        p["ledger"] = {
            "pools": {"gold": {"name": "金", "unit": "两", "initial": 10}},
            "transactions": [
                {"chapter": "ch_001", "pool": "gold", "delta": 5, "type": "income", "subject": "赚"},
                {"chapter": "ch_001", "pool": "gold", "delta": -3, "type": "expense", "subject": "花"},
            ],
        }
        rep = state.apply_proposal(book, p)
        assert not rep["errors"], rep["errors"]
        led = state.load_state(book, "ledger")
        assert led["pools"]["gold"]["current"] == 12
        assert led["transactions"][-1]["balance_after"] == 12

    def test_cross_chapter_transaction_rejected(self, book):
        p = base(ch="ch_001")
        p["ledger"] = {"transactions": [{"chapter": "ch_002", "pool": "gold", "delta": -1, "type": "expense", "subject": "x"}]}
        rep = state.apply_proposal(book, p, expected_chapter="ch_001")
        assert any("≠ 提案所属章" in e for e in rep["errors"])

    def test_expense_sign_rejected(self, book):
        p = base()
        p["ledger"] = {"pools": {"gold": {"name": "金", "unit": "两", "initial": 10}},
                       "transactions": [{"chapter": "ch_001", "pool": "gold", "delta": 5, "type": "expense", "subject": "花"}]}
        rep = state.apply_proposal(book, p)
        assert any("支出必须为负数" in e for e in rep["errors"])


class TestTimeline:
    def test_event_dedup_and_add(self, book):
        p = base()
        p["timeline"] = {"events": [{"time": "第一日", "event": "下雨"}, {"time": "第一日", "event": "下雨"}]}
        rep = state.apply_proposal(book, p)
        assert not rep["errors"], rep["errors"]
        assert any("去重跳过" in w for w in rep["warnings"])
        evs = state.load_state(book, "timeline")["events"]
        assert len(evs) == 1
        assert evs[0]["chapter"] == "ch_001"

    def test_event_replace_miss_rejected(self, book):
        p = base()
        p["timeline"] = {"events": [{"time": "第九日", "event": "不存在", "replace": "改后"}]}
        rep = state.apply_proposal(book, p)
        assert any("未命中" in e for e in rep["errors"])

    def test_event_replace_hit(self, book):
        p = base()
        p["timeline"] = {"events": [{"time": "第一日", "event": "下雨"}]}
        assert not state.apply_proposal(book, p)["errors"]
        p2 = base("op2")
        p2["timeline"] = {"events": [{"time": "第一日", "event": "下雨", "replace": "暴雨"}]}
        rep2 = state.apply_proposal(book, p2)
        assert not rep2["errors"], rep2["errors"]
        assert state.load_state(book, "timeline")["events"][0]["event"] == "暴雨"

    def test_clock_duplicate_by_name_updates(self, book):
        p = base()
        p["timeline"] = {"clocks": [{"name": "追查", "target_ch": 3, "urgency": "high"}]}
        assert not state.apply_proposal(book, p)["errors"]
        p2 = base("op2")
        p2["timeline"] = {"clocks": [{"name": "追查", "target_ch": 5, "status": "Triggered"}]}
        rep2 = state.apply_proposal(book, p2)
        assert not rep2["errors"]
        clocks = state.load_state(book, "timeline")["clocks"]
        assert len(clocks) == 1
        assert clocks[0]["target_ch"] == 5

    def test_clock_requires_int_target(self, book):
        p = base()
        p["timeline"] = {"clocks": [{"name": "追查", "target_ch": "ch_003"}]}
        rep = state.apply_proposal(book, p)
        assert any("target_ch" in e for e in rep["errors"])


class TestPrereq:
    def test_resolved_line_with_unmet_requirement_rejected(self, book):
        p = base()
        p["lines"] = [
            {"kind": "foreshadow", "action": "plant", "id": "GUN-001", "name": "剑", "target_ch": 5,
             "requires": ["GUN-002"], "quote": "q"},
            {"kind": "foreshadow", "action": "plant", "id": "GUN-002", "name": "鞘", "target_ch": 9},
        ]
        assert not state.apply_proposal(book, p)["errors"]
        p2 = base("op2")
        p2["lines"] = [{"kind": "foreshadow", "action": "resolve", "id": "GUN-001", "target_ch": 5, "quote": "q"}]
        rep = state.apply_proposal(book, p2)
        assert any("前置因果冲突" in e for e in rep["errors"])

    def test_cycle_rejected(self, book):
        p = base()
        p["lines"] = [
            {"kind": "foreshadow", "action": "plant", "id": "GUN-001", "name": "a", "target_ch": 5, "requires": ["GUN-002"]},
            {"kind": "foreshadow", "action": "plant", "id": "GUN-002", "name": "b", "target_ch": 6, "requires": ["GUN-001"]},
        ]
        rep = state.apply_proposal(book, p)
        assert any("循环" in e for e in rep["errors"])


class TestSynopsisRevision:
    def test_cross_chapter_unknown_rejected(self, book):
        p = base()
        p["synopsis"] = {"chapters": {"ch_002": {"title": "新", "synopsis": "改"}}}
        rep = state.apply_proposal(book, p)
        assert any("无既有梗概" in e or "跨章修订" in e for e in rep["errors"])

    def test_cross_chapter_known_revised(self, book):
        p = base()
        p["synopsis"] = {"title": "第一章", "text": "梗概"}
        assert not state.apply_proposal(book, p)["errors"]
        p2 = base("op2")
        p2["synopsis"] = {"chapters": {"ch_001": {"title": "新名", "synopsis": "新梗"}}}
        rep2 = state.apply_proposal(book, p2)
        assert not rep2["errors"], rep2["errors"]
        chs = state.load_state(book, "synopsis")["chapters"]
        assert chs["ch_001"]["title"] == "新名"
        assert chs["ch_001"]["synopsis"] == "新梗"


class TestVerifyState:
    def test_ledger_arithmetic_flag(self, book):
        p = base()
        p["ledger"] = {"pools": {"gold": {"name": "金", "unit": "两", "initial": 10}},
                       "transactions": [{"chapter": "ch_001", "pool": "gold", "delta": -3, "type": "expense", "subject": "买"}]}
        state.apply_proposal(book, p)
        led = state.load_state(book, "ledger")
        led["pools"]["gold"]["current"] = 999
        state.save_state(book, "ledger", led)
        assert any("声明余额 999" in e for e in state.verify_state(book))
