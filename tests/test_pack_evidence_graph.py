"""Direct engine tests for pack, evidence, graph, audit, simulate, recall."""
import json
from pathlib import Path

import pytest

from engine import audit, common, evidence, graph, pack, state
from engine.commands.recall import run_recall
from engine.commands.simulate import simulate_branch, simulate_impact


def _build_ready(ws):
    """A Stage-0/1-ready book with a real ch_001 final."""
    book = ws.init("就绪书", "星轨之上", "科幻", "林舟")
    (book/"bible/project_bible.md").write_text("# 圣经\n## 世界与规则\n- 废料场属明港当局。\n", encoding="utf-8")
    vol = book/"outlines/vol_01"
    vol.mkdir(parents=True, exist_ok=True)
    (vol/"outline.md").write_text("# 卷纲\n## 本卷承诺与核心看点\n看点。\n## 本卷剧情节点与章回规划\n- **阶段一（ch_001—ch_002｜剧情）**\n  - ch_001：开篇。\n", encoding="utf-8")
    (vol/"beats").mkdir(parents=True, exist_ok=True)
    (vol/"beats/ch_001.md").write_text(
        "---\nchapter: ch_001\nvol: vol_01\nform: 暗流汇聚\n---\n\n## 本章核心戏剧目标\n- 目标：开篇。\n\n## 场景脉络\n- **场景**：\n  - 🎬 **内容**：人物登场。\n- **收束**：\n  - 📍 **章末刀口**：留钩子。\n\n## 伏笔与线索动作\n- GUN-001 无名驾驶舱：埋设，目标 ch_005\n\n## 交付契约\n- **核心看点**：明确亮点。\n- **验收要点**：\n  1. 事件发生。\n", encoding="utf-8")
    (book/"manuscript/vol_01/raw").mkdir(parents=True, exist_ok=True)
    (book/"manuscript/vol_01/raw/ch_001_v1.md").write_text("# 第1章 开篇\n\n草稿。", encoding="utf-8")
    (book/"manuscript/vol_01/final").mkdir(parents=True, exist_ok=True)
    text = "# 第1章 开篇\n\n林舟推开废料场的旧门，听见牵引灯在响。温棠站在阴影里，盯着他。\n何四海从后面喊了一声。\n"
    text += "林舟握住扳手，把驾驶舱的标签揭下来。\n" * 20
    (book/"manuscript/vol_01/final/ch_001.md").write_text(text, encoding="utf-8")

    # Seed entities + lines + current to activate graph/audit/pov.
    prop = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
            "operation_id": "op_seed", "current": {}, "entities": [
                {"name": "林舟", "type": "person", "summary": "主角"},
                {"name": "温棠", "type": "person", "summary": "探员", "faction": "灯塔局"},
                {"name": "何四海", "type": "person", "summary": "头目", "faction": "铁隼会",
                 "relations": [{"target": "林舟", "type": "对头"}, {"target": "温棠", "type": "情报冲突"}]},
            ],
            "lines": [{"kind": "foreshadow", "action": "plant", "id": "GUN-001",
                       "name": "无名驾驶舱", "target_ch": 5, "quote": "q"}],
            "ledger": {"pools": {"credits": {"name": "信用点", "unit": "点", "initial": 100}},
                       "transactions": [{"chapter": "ch_001", "pool": "credits", "delta": -10,
                                         "type": "expense", "subject": "通行证", "quote": "q"}]},
            "timeline": {"events": [{"time": "第一日", "event": "发现驾驶舱", "quote": "q"}],
                         "arcs": [], "clocks": []},
            "synopsis": {"title": "", "text": ""}}
    assert not state.apply_proposal(book, prop)["errors"], state.apply_proposal(book, prop)["errors"]
    return book


@pytest.fixture
def ready(ws):
    return _build_ready(ws)


class TestPack:
    def test_build_pack_smoke(self, ready):
        payload = pack.build_pack(ready, "ch_001")
        assert payload["chapter"] == "ch_001"
        assert "p0" in payload
        assert "beats" in payload["p0"]
        assert "p1" in payload or "p2" in payload

    def test_render_pack(self, ready):
        payload = pack.build_pack(ready, "ch_001")
        text = pack.render_pack(payload)
        assert "圣经" in text or "林舟" in text

    def test_open_file_director(self, ready):
        out = pack.open_file(ready, "bible/project_bible.md", role="director")
        assert out["path"] == "bible/project_bible.md"
        with pytest.raises(PermissionError):
            pack.open_file(ready, "bible/project_bible.md", role="drafter")
        with pytest.raises(ValueError):
            pack.open_file(ready, "../outside", role="director")

    def test_export(self, ready):
        txt = pack.export_txt(ready)
        assert txt.exists()
        assert "星轨之上" in txt.read_text(encoding="utf-8")
        view = pack.export_views(ready)
        assert view.exists()
        assert "状态视图" in view.read_text(encoding="utf-8")


class TestEvidence:
    def test_words(self, ready):
        out = evidence.words(ready)
        assert out["kind"] == "words"
        assert isinstance(out.get("chapters"), list)
        assert out["chapter_count"] >= 1

    def test_mentions(self, ready):
        out = evidence.mentions(ready)
        assert out["entities"] >= 3
        assert any("ch_001" in ch.get("chapter", "") for ch in out.get("chapters", []))

    def test_gaps_unknown(self, ready):
        out = evidence.gaps(ready)
        assert out["kind"] == "gaps"
        assert isinstance(out.get("foreshadows"), list)

    def test_candidates_needs_final(self, ready):
        out = evidence.candidates(ready, "ch_001")
        assert out["kind"] == "candidates"
        assert "line_hits" in out

    def test_style(self, ready):
        out = evidence.style(ready, "ch_001")
        assert out.get("stats")

    def test_file_missing(self, ready):
        out = evidence.file_stats(ready, "nope.md")
        assert out.get("error")

    def test_ask(self, ready):
        out = evidence.ask(ready, "林舟")
        assert out["kind"] == "ask"
        assert any(e.get("name") == "林舟" for e in out.get("entities", []))

    def test_pov(self, ready):
        out = evidence.pov(ready, "林舟")
        assert out.get("name") == "林舟" or out.get("character") == "林舟"


class TestGraph:
    def test_summary(self, ready):
        G = graph.build_narrative_graph(ready)
        assert G.number_of_nodes() >= 3
        assert G.number_of_edges() >= 1

    def test_path(self, ready):
        G = graph.build_narrative_graph(ready)
        assert graph.cmd_path(G, "林舟", "林舟", as_json=True) == 0

    def test_isolated(self, ready):
        G = graph.build_narrative_graph(ready)
        payload = None
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            graph.cmd_isolated(G, as_json=True)
        payload = json.loads(buf.getvalue())
        assert "isolated" in payload


class TestAudit:
    def test_run_audit(self, ready):
        out = audit.run_audit(ready, "ch_001")
        assert out["chapter"] == "ch_001"
        assert "results" in out or "candidates" in out
        assert out.get("error") is None


class TestSimulateRecall:
    def test_simulate_impact(self, ready):
        out = simulate_impact(ready, entity="林舟", line_id=None, action="kill")
        assert out["target_entity"]["name"] == "林舟"
        assert "affected_lines" in out

    def test_simulate_branch(self, ready):
        import json as _json
        out = simulate_branch(ready, ch="ch_001", count=3, write=False)
        assert out["anchor_chapter"] in ("ch_001", "ch_002")

    def test_recall(self, ready):
        out = run_recall(ready, "ch_001")
        assert out["chapter"] == "ch_001"
        assert "next_chapter_boundaries" in out
