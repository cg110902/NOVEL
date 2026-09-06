"""Error-path and guard behaviour tests for the CLI surface."""
import json
from pathlib import Path

class TestInit:
    def test_requires_workspace(self, ws):
        p = ws.run(["init", "-t", "书"])
        assert p.returncode == 2

    def test_refuses_nonempty_unknown(self, ws):
        d = ws.book_dir("u")
        d.mkdir()
        (d / "x.txt").write_text("x", encoding="utf-8")
        p = ws.run(["init", "-w", str(d)])
        assert p.returncode == 1
        assert not (d / "project.json").exists()

    def test_init_inside_boundary_only(self, ws):
        outside = Path(ws.root.parent) / "b"
        p = ws.run(["init", "-w", str(outside), "-t", "书"])
        assert p.returncode == 2
        assert not (outside / "project.json").exists()


class TestStateGuard:
    def test_unknown_field_rejected(self, ws, book):
        p, data = ws.run_json(["state", "set", "current.bad", "x", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert "闸门" in data["error"]

    def test_wrong_type_rejected(self, ws, book):
        p, data = ws.run_json(["state", "set", "current.present_characters", "abc", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert "present_characters" in data["error"]

    def test_unregistered_entity_rejected(self, ws, book):
        p, data = ws.run_json(["state", "set", "current.present_characters", '["不存在"]', "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert "未登记" in data["error"]

    def test_valid_field_round_trip(self, ws, book):
        p, data = ws.run_json(["state", "set", "current.location", "明港", "-w", str(book), "--json"])
        assert p.returncode == 0, data
        assert data["ok"] is True
        p, data = ws.run_json(["state", "get", "current.location", "-w", str(book), "--json"])
        assert p.returncode == 0
        assert data["value"] == "明港"
        p, data = ws.run_json(["state", "set", "current.location", "", "-w", str(book), "--json"])
        assert p.returncode == 0
        p, data = ws.run_json(["state", "get", "current.location", "-w", str(book), "--json"])
        assert data.get("value") == "" or data.get("value") is None

    def test_unknown_entity_field_rejected(self, ws, book):
        p, data = ws.run_json(["state", "set", "entities.不存在.x", "1", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False

    def test_set_fixes_existing_bad_present(self, ws, book):
        # State already polluted with an unregistered presence (e.g. by an old
        # version before the semantic gate). The surgical command must still be
        # able to fix it, not be blocked by the pre-existing error.
        import json as _json
        cur_path = book / "state" / "current.json"
        cur = _json.loads(cur_path.read_text(encoding="utf-8"))
        cur["present_characters"] = ["不存在"]
        cur_path.write_text(_json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        p, data = ws.run_json(["state", "set", "current.present_characters", '["林舟"]', "-w", str(book), "--json"])
        assert p.returncode == 0, data
        cur = _json.loads(cur_path.read_text(encoding="utf-8"))
        assert cur["present_characters"] == ["林舟"]


class TestConfig:
    def test_set_get_unset(self, ws, book):
        p, data = ws.run_json(["config", "set", "generic_stopwords", '["明明","可能"]', "-w", str(book), "--json"])
        assert p.returncode == 0, data
        p, data = ws.run_json(["config", "get", "generic_stopwords", "-w", str(book), "--json"])
        assert p.returncode == 0
        assert data["value"] == ["明明", "可能"]
        p, data = ws.run_json(["config", "set", "generic_stopwords", '["明明"]', "--merge", "-w", str(book), "--json"])
        assert p.returncode == 0
        p, data = ws.run_json(["config", "get", "generic_stopwords", "-w", str(book), "--json"])
        assert data["value"] == ["明明", "可能"]
        p, data = ws.run_json(["config", "unset", "generic_stopwords", "-w", str(book), "--json"])
        assert p.returncode == 0
        p, data = ws.run_json(["config", "get", "generic_stopwords", "-w", str(book), "--json"])
        assert "value" not in data or data.get("value") is None

    def test_unknown_key(self, ws, book):
        p, data = ws.run_json(["config", "get", "nope", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert data["ok"] is False
        assert data["code"] == "unknown_param_key"

    def test_bad_shape(self, ws, book):
        p, data = ws.run_json(["config", "set", "words_target", '"abc"', "-w", str(book), "--json"])
        assert p.returncode == 2
        assert data["ok"] is False

    def test_guide_lists_keys(self, ws, book):
        p, data = ws.run_json(["config", "guide", "-w", str(book), "--json"])
        assert p.returncode == 0
        assert "generic_stopwords" in data["params"]


class TestMilestone:
    def test_add_duplicate(self, ws, book):
        p, data = ws.run_json(["milestone", "add", "--title", "第一段", "--target-ch", "3", "--id", "MS-001", "-w", str(book), "--json"])
        assert p.returncode == 0, data
        p, data = ws.run_json(["milestone", "add", "--title", "第二段", "--target-ch", "4", "--id", "MS-001", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert "已存在" in data["error"]

    def test_add_auto_id(self, ws, book):
        p, data = ws.run_json(["milestone", "add", "--title", "第一", "--target-ch", "3", "-w", str(book), "--json"])
        assert p.returncode == 0
        assert data["milestone"]["id"].startswith("MS-")

    def test_add_requires_target_ch(self, ws, book):
        p = ws.run(["milestone", "add", "--title", "第一", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert p.stdout == ""


class TestMilestoneJSON:
    def test_bad_target_ch_json(self, ws, book):
        p, data = ws.run_json(["milestone", "add", "--title", "第一", "--target-ch", "0", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert data["ok"] is False
        assert "≥1" in data["error"]


class TestLedger:
    def test_pool_add_duplicate(self, ws, book):
        p, data = ws.run_json(["ledger", "pool", "add", "fuel", "--name", "燃料", "--unit", "升", "--initial", "10", "-w", str(book), "--json"])
        assert p.returncode == 0, data
        p, data = ws.run_json(["ledger", "pool", "add", "fuel", "--name", "燃料", "--unit", "升", "--initial", "20", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert "已存在" in data["error"]

    def test_pool_id_validation(self, ws, book):
        p, data = ws.run_json(["ledger", "pool", "add", "1bad", "--name", "燃料", "--unit", "升", "--initial", "10", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert "非法" in data["error"]

    def test_pool_requires_initial(self, ws, book):
        # argparse marks --initial required, so missing it is a usage error with empty stdout.
        p = ws.run(["ledger", "pool", "add", "fuel", "--name", "燃料", "--unit", "升", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert p.stdout == ""


class TestWorkspaceGuards:
    def test_multiple_books(self, ws):
        ws.init("甲", "甲", "scifi", "a")
        ws.init("乙", "乙", "scifi", "b")
        for args in (["status"], ["check"], ["cockpit"], ["sync", "ch_001"]):
            p, data = ws.run_json(args + ["--json"])
            assert p.returncode == 2, f"{args}: {data}"
            assert "multiple_books" in json.dumps(data, ensure_ascii=False)

    def test_out_of_bounds(self, ws, book):
        outside = Path(ws.root.parent) / "outside"
        outside.mkdir(exist_ok=True)
        p, data = ws.run_json(["status", "-w", str(outside), "--json"])
        assert p.returncode == 1
        assert data.get("reason") == "workspace_out_of_bounds" or data.get("code") == "workspace_out_of_bounds"


class TestBadArgs:
    def test_unknown_chapter(self, ws, book):
        p, data = ws.run_json(["pack", "ch_zzz", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert data["ok"] is False

    def test_bad_evidence_kind(self, ws, book):
        # argparse rejects the choice before the command body; stdout must stay empty.
        p = ws.run(["evidence", "nope", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert p.stdout == ""

    def test_bad_calendar_span(self, ws, book):
        # Non-int span is an argparse type error.
        p = ws.run(["calendar", "abc", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert p.stdout == ""


class TestPackAccess:
    def test_drafter_reads_bible_denied(self, ws, book):
        p, data = ws.run_json(["pack", "--open", "bible/project_bible.md", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert data["code"] == "forbidden"

    def test_director_reads_bible_allowed(self, ws, book):
        p, data = ws.run_json(["pack", "--open", "bible/project_bible.md", "--as", "director", "-w", str(book), "--json"])
        assert p.returncode == 0, data
        assert data["opened"]["path"] == "bible/project_bible.md"
        assert len(data["opened"]["text"]) > 0

    def test_open_out_of_bounds_denied(self, ws, book):
        p, data = ws.run_json(["pack", "--open", "../outside.txt", "--as", "director", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert "越界" in data["error"]


class TestProposal:
    def test_new_prints_skeleton(self, ws, book):
        p, data = ws.run_json(["proposal", "new", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 0
        assert data["schema"] == "novel-studio.state-mutation/v2"
        assert data["chapter"] == "ch_001"
        assert data["operation_id"].startswith("ch_001.")

    def test_new_existing_not_overwritten(self, ws, book):
        inbox = book / "state" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "ch_001.json").write_text('{"schema":"novel-studio.state-mutation/v2","chapter":"ch_001","operation_id":"ch_001.x"}', encoding="utf-8")
        before = (inbox / "ch_001.json").read_text(encoding="utf-8")
        p, data = ws.run_json(["proposal", "new", "ch_001", "--write", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert data["code"] == "exists"
        assert (inbox / "ch_001.json").read_text(encoding="utf-8") == before

    def test_auto_no_write_missing_beats(self, ws, book):
        p, data = ws.run_json(["proposal", "auto", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
        assert "beats" in data["error"]

    def test_check_missing_inbox(self, ws, book):
        p, data = ws.run_json(["proposal", "check", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert "未找到" in data.get("error", "")


class TestSync:
    def test_missing_final(self, ws, book):
        p, data = ws.run_json(["sync", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert "未找到" in data["error"]

    def test_invalid_target(self, ws, book):
        p, data = ws.run_json(["sync", "ch_zzz", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert data["ok"] is False
        assert data["code"] == "usage"


class TestAudit:
    def test_missing_manuscript(self, ws, book):
        p, data = ws.run_json(["audit", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert "未找到" in data["error"]


class TestReadonlyMissing:
    def test_pack_no_chapter(self, ws, book):
        p, data = ws.run_json(["pack", "-w", str(book), "--json"])
        assert p.returncode == 2
        assert data["ok"] is False
        assert data["code"] == "usage"

    def test_review_needs_beats(self, ws, book):
        p, data = ws.run_json(["review", "new", "ch_001", "-w", str(book), "--json"])
        assert p.returncode == 1
        assert data["ok"] is False
