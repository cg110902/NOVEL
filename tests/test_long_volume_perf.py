"""Cross-volume discovery, pack at late chapters, and medium-scale index smoke."""
from __future__ import annotations

from pathlib import Path

from engine import common, db, pack, state

VOLS = {"vol_01": range(1, 50), "vol_02": range(50, 61)}


def _seed_finals(book: Path, marker: str):
    for vol, chs in VOLS.items():
        d = book / "manuscript" / vol / "final"
        d.mkdir(parents=True, exist_ok=True)
        for n in chs:
            (d / f"ch_{n:03d}.md").write_text(
                f"# 第{n}章\n\n{marker} 林舟在 vol={vol} ch={n} 的正文。\n" * 3,
                encoding="utf-8")


def _seed_book(ws):
    book = ws.init("长卷书", "星轨之上", "科幻", "林舟")
    _seed_finals(book, "长卷标记")
    prop = {
        "schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
        "operation_id": "op_seed_long", "current": {}, "entities": [
            {"name": "林舟", "type": "person", "summary": "主角"},
            {"name": "温棠", "type": "person", "summary": "探员", "faction": "灯塔局"},
        ],
        "lines": [], "ledger": {"transactions": []},
        "timeline": {"events": [], "arcs": []},
        "synopsis": {"title": "", "text": ""},
    }
    rep = state.apply_proposal(book, prop)
    assert not rep["errors"], rep["errors"]
    return book


def _seed_beats(book: Path, ch: str):
    vol = book / "outlines" / "vol_02" / "beats"
    vol.mkdir(parents=True, exist_ok=True)
    (vol / f"{ch}.md").write_text(
        f"---\nchapter: {ch}\nvol: vol_02\nform: 暗流汇聚\n---\n\n"
        f"## 场景脉络\n- **场景**：\n  - 🎬 **内容**：林舟进入废料场。\n", encoding="utf-8")


def _seed_vol2_outline(book: Path):
    vol = book / "outlines" / "vol_02"
    vol.mkdir(parents=True, exist_ok=True)
    (vol / "outline.md").write_text(
        "# 卷二\n\n## 本卷剧情节点与章回规划\n"
        "- **第二卷阶段（ch_050—ch_060 | 主线推进）**\n"
        "  - ch_050：跨卷续接。\n", encoding="utf-8")


class TestCrossVolume:
    def test_find_chapter_target_vol(self, ws):
        book = _seed_book(ws)
        hit = common.find_chapter_files(book, "final", "ch_055")
        assert len(hit) == 1
        assert "vol_02" in hit[0].as_posix()

        hit2 = common.find_chapter_files(book, "final", "vol_02/ch_055")
        assert len(hit2) == 1
        assert hit2[0].name == "ch_055.md"

        # A bare ch_005 must not accidentally match vol_02/ch_050 or vol_02/ch_005.
        hit_005 = [p for p in common.find_chapter_files(book, "final", "ch_005")]
        assert [p.name for p in hit_005] == ["ch_005.md"]

    def test_pack_cross_volume_prev_tail(self, ws):
        book = _seed_book(ws)
        ch = "vol_02/ch_050"
        _seed_beats(book, "ch_050")
        _seed_vol2_outline(book)
        payload = pack.build_pack(book, ch)
        assert payload["chapter"] == ch
        assert payload["p0"]["volume_phase"]
        # 上一章是 vol_01/ch_049（跨卷续接），而不是空或错误地串到别的卷首章。
        assert "ch=49" in payload["p0"]["prev_tail"] or "第49章" in payload["p0"]["prev_tail"]

    def test_pack_vol_scope(self, ws):
        book = _seed_book(ws)
        ch = "vol_02/ch_050"
        _seed_beats(book, "ch_050")
        _seed_vol2_outline(book)
        payload = pack.build_pack(book, ch)
        assert payload["p0"]["volume_phase"].startswith("第二卷阶段")


class TestMediumScaleIndex:
    def test_build_and_query_30_chapters(self, ws):
        book = _seed_book(ws)
        st = state.load_state(book, "entities")
        st["entries"].append({"name": "旧货", "type": "item", "summary": "驾驶舱部件",
                              "condition": "磨损"})
        state.save_state(book, "entities", st)
        stats = db.build_or_update_index(book, force_rebuild=True)
        assert stats["indexed_chapters"] >= 60
        hits = db.search_chapters_bm25(book, "林舟", limit=5)
        assert isinstance(hits, list) and len(hits) >= 1
        pov = db.query_character_pov(book, "林舟")
        assert pov["character"] == "林舟"
        held = db.query_character_pov(book, "旧货")
        assert held["character"] == "旧货"
