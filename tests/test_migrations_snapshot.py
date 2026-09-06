"""Migration + snapshot tests."""
from pathlib import Path

import pytest

from engine import common, migrations, snapshot, state


@pytest.fixture
def book(tmp_path):
    b = tmp_path / "book"
    b.mkdir()
    state.init_state(b)
    return b


class TestMigrations:
    def test_version_current(self, book):
        assert migrations.read_version(book) == migrations.CURRENT_STATE_VERSION

    def test_legacy_missing_version_migrates(self, tmp_path):
        import json
        b = tmp_path / "b"
        b.mkdir()
        state.init_state(b)
        # Downgrade to legacy by removing version marker and v3/v4 tables.
        (b / "state" / "state_schema.json").unlink()
        (b / "state" / "cognition.json").unlink()
        (b / "state" / "locked.json").unlink()
        # Build a current.json with an explicit null using raw IO (load_state would
        # call ensure_state_version and migrate first, defeating the legacy test).
        cur_path = b / "state" / "current.json"
        cur = json.loads(cur_path.read_text(encoding="utf-8"))
        cur["time"] = None
        cur_path.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")

        result = migrations.ensure_state_version(b)
        assert result["migrated"]
        assert result["from"] == 0
        assert migrations.read_version(b) == migrations.CURRENT_STATE_VERSION
        # explicit null was removed (treated as absent) and v3/v4 tables restored
        cur = state.load_state(b, "current")
        assert "time" not in cur
        assert (b / "state" / "cognition.json").exists()
        assert (b / "state" / "locked.json").exists()

    def test_future_version_rejected(self, book):
        common.dump_json(migrations.version_path(book), {"version": migrations.CURRENT_STATE_VERSION + 1})
        with pytest.raises(ValueError):
            migrations.ensure_state_version(book)


class TestSnapshot:
    def test_create_list(self, book):
        ok, name = snapshot.create_snapshot(book, "ch_001_done")
        assert ok
        assert name in snapshot.list_snapshots(book)

    def test_bad_name(self, book):
        with pytest.raises(ValueError):
            snapshot.create_snapshot(book, "..")
        with pytest.raises(ValueError):
            snapshot.create_snapshot(book, "")

    def test_rollback_restores(self, book):
        p = _base_proposal(op="op1")
        p["current"] = {"goal": "原目标"}
        state.apply_proposal(book, p)
        snapshot.create_snapshot(book, "pre")
        p2 = _base_proposal(op="op2")
        p2["current"] = {"goal": "新目标"}
        state.apply_proposal(book, p2)
        assert state.load_state(book, "current")["goal"] == "新目标"
        ok, msg, chosen = snapshot.rollback_snapshot(book, "pre")
        assert ok, msg
        assert state.load_state(book, "current")["goal"] == "原目标"
        # pre_rollback backup exists so we can still recover
        backups = [n for n in snapshot.list_snapshots(book) if n.startswith("pre_rollback")]
        assert backups


def _base_proposal(chapter="ch_001", op="op1"):
    return {
        "schema": "novel-studio.state-mutation/v2", "chapter": chapter,
        "operation_id": op, "current": {}, "entities": [], "lines": [],
        "ledger": {"transactions": []}, "timeline": {"events": [], "arcs": []},
        "synopsis": {"title": "", "text": ""},
    }
