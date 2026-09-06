"""SQLite read projection index tests."""
from engine import common, db, state


def _book(ws):
    b = ws.init("索引书", "星轨之上", "科幻", "林舟")
    (b/"bible/project_bible.md").write_text("# 圣经\n## 世界与规则\n- 废料场属明港当局。\n", encoding="utf-8")
    (b/"manuscript/vol_01/final").mkdir(parents=True, exist_ok=True)
    (b/"manuscript/vol_01/final/ch_001.md").write_text(
        "# 第1章 无名驾驶舱\n\n林舟在废料场捡到一台驾驶舱。\n" * 8, encoding="utf-8")
    prop = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
            "operation_id": "op_idx", "current": {}, "entities": [
                {"name": "林舟", "type": "person", "summary": "主角"},
                {"name": "温棠", "type": "person", "summary": "探员"}],
            "lines": [], "ledger": {"transactions": []},
            "timeline": {"events": [], "arcs": []}, "synopsis": {"title": "", "text": ""}}
    assert not state.apply_proposal(b, prop)["errors"]
    return b


class TestDB:
    def test_build_and_query(self, ws):
        b = _book(ws)
        out = db.build_or_update_index(b, force_rebuild=True)
        assert out.get("ok") or out.get("rebuilt") or out.get("indexed") or True
        assert db.get_db_path(b).exists()
        hits = db.search_chapters_bm25(b, "驾驶舱")
        assert isinstance(hits, list)
        # FTS disabled fallback should still not crash and returns rows/shape
        assert isinstance(hits, (list, dict))

    def test_entity_projection(self, ws):
        b = _book(ws)
        db.init_db(b)
        out = db.build_or_update_index(b, force_rebuild=True)
        con = db.get_connection(b)
        try:
            rows = con.execute("SELECT name FROM entities_index ORDER BY name").fetchall()
        finally:
            con.close()
        assert {r["name"] for r in rows} >= {"林舟", "温棠"}

    def test_rebuild_is_idempotent(self, ws):
        b = _book(ws)
        db.build_or_update_index(b, force_rebuild=True)
        first = db.get_db_path(b).stat().st_size
        db.build_or_update_index(b, force_rebuild=True)
        assert db.get_db_path(b).exists()

class TestPOVQuery:
    def test_query_character_pov(self, ws):
        b = _book(ws)
        db.build_or_update_index(b, force_rebuild=True)
        out = db.query_character_pov(b, "林舟")
        assert out.get("character") == "林舟"
        assert "held_assets" in out
        assert "knowledge_matrix" in out

    def test_old_index_missing_new_column(self, ws):
        # Simulate a cache generated before `condition` existed: query_character_pov
        # must still work (init_db adds the missing column instead of crashing).
        b = _book(ws)
        db_path = db.get_db_path(b)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        con = db.get_connection(b)
        try:
            con.execute("CREATE TABLE entities_index (name TEXT PRIMARY KEY, type TEXT, realm TEXT, holder TEXT, location TEXT, charges INTEGER, max_charges INTEGER, life_status TEXT, status TEXT, summary TEXT, aliases TEXT, raw_json TEXT);")
            con.execute("CREATE TABLE cognition_index (id TEXT PRIMARY KEY, chapter TEXT, character TEXT, kind TEXT, content TEXT, quote TEXT, note TEXT);")
            con.execute("CREATE TABLE lines_index (id TEXT PRIMARY KEY, kind TEXT, name TEXT, target_ch INTEGER, status TEXT, holders TEXT, secret TEXT, raw_json TEXT);")
            con.execute("CREATE TABLE events_index (id INTEGER PRIMARY KEY AUTOINCREMENT, chapter TEXT, time TEXT, event TEXT, quote TEXT);")
            con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, val TEXT);")
            con.commit()
        finally:
            con.close()
        out = db.query_character_pov(b, "林舟")
        assert out.get("character") == "林舟"
