"""proposal auto assembly correctness (beats -> proposal fields)."""
import json


def _book(ws):
    b = ws.init("auto书", "星轨之上", "科幻", "林舟")
    (b/"bible/project_bible.md").write_text("# 圣经\n## 世界与规则\n- 废料场属明港当局。\n", encoding="utf-8")
    vol = b/"outlines/vol_01"
    vol.mkdir(parents=True, exist_ok=True)
    (vol/"outline.md").write_text("# 卷纲\n## 本卷承诺与核心看点\n看点。\n## 本卷剧情节点与章回规划\n- **阶段一（ch_001—ch_002｜剧情）**\n  - ch_001：开篇。\n", encoding="utf-8")
    (vol/"beats").mkdir(exist_ok=True)
    (vol/"beats/ch_001.md").write_text(
        "---\nchapter: ch_001\nvol: vol_01\nform: 暗流汇聚\npov: 林舟·视角\nwords: 2000-3000+\n"
        "tension_curve: 平缓 → 紧张\ntension_score: 5\nstage_mode: Simmering\nstyle_notes: 通俗\n---\n\n"
        "## 本章核心戏剧目标\n- 目标：发现驾驶舱。\n\n"
        "## 场景脉络\n- **场景**：\n  - 🎬 **内容**：林舟摸进废料场。\n- **收束**：\n"
        "  - 📍 **章末物理刀口**：有人拉了缆绳。\n\n"
        "## 伏笔与线索动作\n- GUN-001（无名驾驶舱）：埋设，目标 ch_005\n\n"
        "## 交付契约\n- **核心看点**：捡到好东西。\n- **验收要点**：\n  1. 核心事件发生。\n",
        encoding="utf-8")
    (b/"manuscript/vol_01/final").mkdir(parents=True, exist_ok=True)
    (b/"manuscript/vol_01/final/ch_001.md").write_text(
        "# 第1章 无名驾驶舱\n\n林舟在废料场发现驾驶舱。\n" * 8, encoding="utf-8")
    return b


class TestAuto:
    def test_scene_labels_stripped(self, ws):
        b = _book(ws)
        p, data = ws.run_json(["proposal", "auto", "ch_001", "-w", str(b), "--json"])
        assert p.returncode == 0, data
        situ = data["current"]["situation"]
        assert "🎬" not in situ and "📍" not in situ and "内容：" not in situ
        assert "林舟摸进废料场" in situ
        assert "有人拉了缆绳" in situ
        assert "🎬" not in data["synopsis"]["text"]

    def test_explicit_target_ch_honoured(self, ws):
        b = _book(ws)
        p, data = ws.run_json(["proposal", "auto", "ch_001", "-w", str(b), "--json"])
        assert p.returncode == 0, data
        line = next(g for g in data["lines"] if g.get("id") == "GUN-001")
        assert line["target_ch"] == 5

    def test_longline_target_honoured(self, ws):
        b = _book(ws)
        beats = b/"outlines/vol_01/beats/ch_001.md"
        beats.write_text(beats.read_text(encoding="utf-8").replace(
            "目标 ch_005", "longline"), encoding="utf-8")
        p, data = ws.run_json(["proposal", "auto", "ch_001", "-w", str(b), "--json"])
        assert p.returncode == 0, data
        line = next(g for g in data["lines"] if g.get("id") == "GUN-001")
        assert line["target_ch"] == "longline"
