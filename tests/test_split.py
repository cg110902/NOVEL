"""R1 拆表回归：kind 路由 / 兼容视图 / v5→v6 迁移 / legacy 折叠 / 快照往返。"""
import json
import unittest

from tests._fixtures import TempBook


def _prop(ch="ch_001", op="ch_001.test.01", **kw):
    p = {"schema": "novel-studio.state-mutation/v2", "chapter": ch, "operation_id": op}
    p.update(kw)
    return p


class TestKindRouting(unittest.TestCase):
    def test_four_tables_routed(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(entities=[
                {"name": "林牧", "id": "p_001", "type": "person"},
                {"name": "断水剑", "id": "it_001", "type": "道具"},
                {"name": "青云门", "id": "f_001", "type": "势力"},
                {"name": "临江城", "id": "loc_001", "type": "location"},
                {"name": "无名氏"},
            ]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertEqual([e["name"] for e in tb.state("persons")["entries"]],
                             ["林牧", "无名氏"])
            self.assertEqual(tb.state("items")["entries"][0]["type"], "item")
            self.assertEqual(tb.state("factions")["entries"][0]["type"], "faction")
            self.assertEqual(tb.state("places")["entries"][0]["name"], "临江城")
            # 脏检查：中文/缺省不进库
            for k in ("persons", "items", "factions", "places"):
                for e in tb.state(k)["entries"]:
                    self.assertIn(e["type"], ("person", "item", "faction",
                                              "place", "location", "other"))

    def test_unknown_type_rejected_and_move(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(entities=[
                {"name": "林牧", "id": "p_001", "type": "person"},
            ]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.02", entities=[{"name": "怪", "type": "persn"}]))
            self.assertTrue(rep["errors"])
            # type 变更 → 跨表搬迁
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.03",
                entities=[{"name": "林牧", "type": "item"}]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertEqual(tb.state("persons")["entries"], [])
            self.assertEqual(tb.state("items")["entries"][0]["name"], "林牧")
            self.assertTrue(any("搬迁" in u for u in rep["updated"]), rep["updated"])
            # retire 跨表可用
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.04",
                entities=[{"name": "林牧", "action": "retire"}]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertEqual(tb.state("items")["entries"][0]["status"], "retired")


class TestCompatView(unittest.TestCase):
    def test_merged_read_and_write_reject(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(entities=[
                {"name": "林牧", "type": "person"},
                {"name": "断水剑", "type": "item"},
            ]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            merged = state.load_state(tb.book, "entities")
            self.assertEqual(len(merged["entries"]), 2)
            with self.assertRaises(ValueError) as cm:
                state.save_state(tb.book, "entities", {"entries": []})
            self.assertIn("v6", str(cm.exception))


class TestCrossTableIdGate(unittest.TestCase):
    def test_dirty_dup_id_caught(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(entities=[
                {"name": "林牧", "id": "p_001", "type": "person"},
                {"name": "断水剑", "id": "it_001", "type": "item"},
            ]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            items = tb.state("items")
            items["entries"][0]["id"] = "p_001"
            tb.set_state("items", items)
            data = {k: state.load_state(tb.book, k) for k in state.STATE_KEYS}
            errs = state.verify_data(data)
            self.assertTrue(any("跨表重复" in e for e in errs), errs)


class TestSurgeryKindTables(unittest.TestCase):
    def test_legacy_alias_and_kind_paths(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(entities=[
                {"name": "林牧", "id": "p_001", "type": "person"},
            ]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            rc = tb.run("state", "set", "entities.林牧.realm", "金丹")
            self.assertEqual(rc.returncode, 0, rc.stdout + rc.stderr)
            self.assertEqual(tb.state("persons")["entries"][0]["realm"], "金丹")
            rc = tb.run("state", "get", "entities.林牧.realm")
            self.assertIn("金丹", rc.stdout)
            rc = tb.run("state", "set", "persons.林牧.realm", "元婴")
            self.assertEqual(rc.returncode, 0, rc.stdout + rc.stderr)
            self.assertEqual(tb.state("persons")["entries"][0]["realm"], "元婴")
            rc = tb.run("state", "set", "entities.不存在.realm", "x")
            self.assertNotEqual(rc.returncode, 0)


class TestMigrationV5V6(unittest.TestCase):
    def test_legacy_book_splits(self):
        from engine import migrations, state
        with TempBook() as tb:
            for k in ("persons", "items", "factions", "places"):
                (tb.book / "state" / f"{k}.json").unlink()
            tb.write("state/entities.json", json.dumps({"entries": [
                {"name": "林牧", "id": "p_001", "type": "person"},
                {"name": "断水剑", "type": "道具"},
                {"name": "怪", "type": "xxx"},
                {"name": "裸奔"},
            ]}))
            stamp = json.loads(tb.read("state/state_schema.json"))
            stamp["version"] = 5
            tb.write("state/state_schema.json", json.dumps(stamp))
            migrations._ENSURED.clear()
            d = state.load_state(tb.book, "persons")
            self.assertEqual([e["name"] for e in d["entries"]], ["林牧", "怪", "裸奔"])
            self.assertEqual(tb.state("items")["entries"][0]["type"], "item")
            self.assertTrue((tb.book / "state/entities.json.v5bak").is_file())
            self.assertFalse((tb.book / "state/entities.json").exists())
            self.assertEqual(json.loads(tb.read("state/state_schema.json"))["version"], 6)


class TestFoldLegacy(unittest.TestCase):
    def test_fold_splits_legacy_entities(self):
        from engine import changelog
        base = {"entities": {"entries": [
            {"name": "林牧", "type": "person"},
            {"name": "断水剑", "type": "item"},
        ]}}
        folded = changelog.fold(base, [])
        self.assertNotIn("entities", folded)
        self.assertEqual([e["name"] for e in folded["persons"]["entries"]], ["林牧"])
        self.assertEqual([e["name"] for e in folded["items"]["entries"]], ["断水剑"])

    def test_fold_drops_stale_entities_when_kinds_present(self):
        from engine import changelog
        folded = changelog.fold({
            "entities": {"entries": [{"name": " stale ", "type": "person"}]},
            "persons": {"entries": [{"name": "林牧", "type": "person"}]},
        }, [])
        self.assertNotIn("entities", folded)
        self.assertEqual([e["name"] for e in folded["persons"]["entries"]], ["林牧"])


class TestSnapshotRoundtripV6(unittest.TestCase):
    def test_create_and_rollback(self):
        from engine import state
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, _prop(entities=[
                {"name": "林牧", "id": "p_001", "type": "person"},
            ]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            rc = tb.run("snapshot", "create", "r1split")
            self.assertEqual(rc.returncode, 0, rc.stdout + rc.stderr)
            rep = state.apply_proposal(tb.book, _prop(
                op="ch_001.test.02",
                entities=[{"name": "赵莽", "id": "p_002", "type": "person"}]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            rc = tb.run("snapshot", "rollback", "r1split")
            self.assertEqual(rc.returncode, 0, rc.stdout + rc.stderr)
            self.assertEqual([e["name"] for e in tb.state("persons")["entries"]],
                             ["林牧"])


if __name__ == "__main__":
    unittest.main()
