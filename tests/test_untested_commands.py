"""Tests for previously untested command surfaces: critic, state show, proposal verify."""
import json

from engine import state


def _mk_ready(ws):
    """A Stage-0/1-ready book with a real ch_001 final and seeded state."""
    book = ws.init("就绪书", "星轨之上", "科幻", "林舟")
    (book / "bible/project_bible.md").write_text(
        "# 圣经\n## 世界与规则\n- 废料场属明港当局。\n", encoding="utf-8")
    vol = book / "outlines/vol_01"
    vol.mkdir(parents=True, exist_ok=True)
    (vol / "outline.md").write_text(
        "# 卷纲\n## 本卷剧情节点与章回规划\n- **阶段一（ch_001—ch_002｜剧情）**\n  - ch_001：开篇。\n",
        encoding="utf-8")
    (vol / "beats").mkdir(parents=True, exist_ok=True)
    (vol / "beats/ch_001.md").write_text(
        "---\nchapter: ch_001\nvol: vol_01\nform: 暗流汇聚\n---\n\n"
        "## 本章核心戏剧目标\n- 目标：开篇。\n\n"
        "## 场景脉络\n- **场景**：\n  - 🎬 **内容**：人物登场。\n"
        "- **收束**：\n  - 📍 **章末刀口**：留钩子。\n\n"
        "## 伏笔与线索动作\n- GUN-001 无名驾驶舱：埋设，目标 ch_005\n\n"
        "## 交付契约\n- **核心看点**：明确亮点。\n", encoding="utf-8")
    (book / "manuscript/vol_01/raw").mkdir(parents=True, exist_ok=True)
    (book / "manuscript/vol_01/raw/ch_001_v1.md").write_text(
        "# 第1章 开篇\n\n草稿。", encoding="utf-8")
    (book / "manuscript/vol_01/final").mkdir(parents=True, exist_ok=True)
    text = "# 第1章 开篇\n\n林舟推开废料场的旧门，听见牵引灯在响。温棠站在阴影里，盯着他。\n"
    text += "林舟握住扳手，把驾驶舱的标签揭下来。\n" * 20
    (book / "manuscript/vol_01/final/ch_001.md").write_text(text, encoding="utf-8")

    prop = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
            "operation_id": "op_seed", "current": {}, "entities": [
                {"name": "林舟", "type": "person", "summary": "主角"},
                {"name": "温棠", "type": "person", "summary": "探员", "faction": "灯塔局"},
                {"name": "何四海", "type": "person", "summary": "头目", "faction": "铁隼会",
                 "relations": [{"target": "林舟", "type": "对头"}]},
            ],
            "lines": [{"kind": "foreshadow", "action": "plant", "id": "GUN-001",
                       "name": "无名驾驶舱", "target_ch": 5, "quote": "q"}],
            "ledger": {"pools": {"credits": {"name": "信用点", "unit": "点", "initial": 100}},
                       "transactions": [{"chapter": "ch_001", "pool": "credits", "delta": -10,
                                         "type": "expense", "subject": "通行证", "quote": "q"}]},
            "timeline": {"events": [{"time": "第一日", "event": "发现驾驶舱", "quote": "q"}],
                         "arcs": [], "clocks": []},
            "synopsis": {"title": "", "text": ""}}
    rep = state.apply_proposal(book, prop)
    assert not rep["errors"], rep["errors"]
    return book


class TestCritic:
    def test_missing_final_json_envelope(self, ws, book):
        p, data = ws.run_json(["critic", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert data["code"] == "no_final"

    def test_bad_chapter_json_envelope(self, ws, book):
        p, data = ws.run_json(["critic", "ch_zzz", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert data["ok"] is False
        assert data["code"] == "usage"

    def test_write_skeleton(self, ws):
        book = _mk_ready(ws)
        p, data = ws.run_json(["critic", "ch_001", "--write", "-w", str(book), "--json"])
        assert p.returncode == 0, data
        assert data["skeleton"] is True
        assert (book / "log/critic/ch_001.md").is_file()

    def test_existing_skeleton_reported(self, ws):
        book = _mk_ready(ws)
        critic_file = book / "log/critic/ch_001.md"
        critic_file.parent.mkdir(parents=True, exist_ok=True)
        critic_file.write_text("SKELETON\n- 待评。", encoding="utf-8")
        p, data = ws.run_json(["critic", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 0, data
        assert data["skeleton"] is True
        assert "report" in data


class TestStateShow:
    def test_show_json_roundtrip(self, ws, book):
        p, data = ws.run_json(["state", "show", "-w", str(book), "--json"])
        assert p.returncode == 0
        assert "time" in data
        assert "present_characters" in data

    def test_get_missing_entity_json_envelope(self, ws, book):
        p, data = ws.run_json(["state", "get", "entities.不存在.realm", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert data["code"] == "state_error"

    def test_set_unknown_part_json_envelope(self, ws, book):
        p, data = ws.run_json(["state", "set", "nope.x", "1", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert data["ok"] is False
        assert data["code"] == "state_error"


class TestProposalVerify:
    def test_missing_proposal_json_envelope(self, ws, book):
        p, data = ws.run_json(["proposal", "verify", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert data["code"] == "proposal_error"

    def test_with_proposal(self, ws):
        book = _mk_ready(ws)
        inbox = book / "state/inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        prop = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
                "operation_id": "op_verify", "current": {"location": "废料场"},
                "entities": [], "lines": [], "ledger": {"transactions": []},
                "timeline": {"events": [], "arcs": []}, "synopsis": {"title": "", "text": ""}}
        (inbox / "ch_001.json").write_text(json.dumps(prop, ensure_ascii=False), encoding="utf-8")
        p, data = ws.run_json(["proposal", "verify", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 0, (p.stdout, p.stderr)
        assert data["chapter"] == "ch_001"
        assert "verify" in data
        assert "quote_notes" in data

    def test_archived_chapter_hint(self, ws, book):
        # After sync archives a chapter, verify should point to processed/ not claim missing.
        syn = state.load_state(book, "synopsis")
        syn.setdefault("chapters", {})["ch_001"] = {"num": 1, "source": "manual",
                                                    "synopsis": "梗概", "title": "开篇"}
        state.save_state(book, "synopsis", syn)
        p, data = ws.run_json(["proposal", "verify", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert data["code"] == "proposal_error"
        assert "已合并归档" in data["error"]
