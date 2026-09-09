"""R2 问书 2.0：每条命中自带 cite{table, key, chapters[]} 引用链。"""
import json
import unittest

from tests._fixtures import TempBook


def _apply(tb, ch, op, **sections):
    from engine import state
    p = {"schema": "novel-studio.state-mutation/v2", "chapter": ch,
         "operation_id": op}
    p.update(sections)
    rep = state.apply_proposal(tb.book, p)
    assert rep["errors"] == [], rep["errors"]
    return rep


def _seed_two_chapters(tb):
    _apply(tb, "ch_001", "ch_001.ask2.seed",
           current={"location": "林牧的灯铺"},
           entities=[{"action": "upsert", "id": "p_001", "name": "林牧",
                      "type": "person", "summary": "灯铺少主"}],
           lines=[{"action": "plant", "kind": "foreshadow", "id": "GUN-001",
                   "name": "林牧的刀", "target_ch": 9}],
           timeline={"events": [{"time": "正午", "event": "林牧拔刀"}]},
           ledger={"pools": {"stone": {"name": "灵石", "unit": "块", "initial": 100}},
                   "transactions": [{"chapter": "ch_001", "pool": "stone",
                                     "delta": -30, "type": "expense",
                                     "subject": "林牧买刀"}]},
           locked=[{"action": "plant", "id": "LOCK-001", "fact": "林牧之刀断于江边",
                    "kind": "destruction", "note": "断刀不可复原", "quote": "咔嚓一声"}],
           cognition=[{"action": "plant", "character": "林牧",
                       "content": "他知道刀已断裂", "kind": "fact", "quote": "刀断了"}],
           synopsis={"title": "第一章", "text": "林牧拔刀。"})
    _apply(tb, "ch_002", "ch_002.ask2.seed",
           entities=[{"action": "upsert", "id": "p_001", "name": "林牧",
                      "type": "person", "summary": "灯铺少主，刀断"}])
    tb.seed_chapter("ch_001", "林牧推门进屋，屋里点着一盏灯。" * 30)


class TestAsk2Citations(unittest.TestCase):
    def test_every_hit_cited(self):
        from engine import evidence
        with TempBook() as tb:
            _seed_two_chapters(tb)
            out = evidence.ask(tb.book, "林牧")
            self.assertEqual(out.get("ask_version"), "2.0")
            self.assertTrue(any("2.0" in n for n in out.get("notes", [])))

            ent = out["entities"][0]
            self.assertEqual(ent["id"], "p_001")
            self.assertEqual(ent["_table"], "persons")
            self.assertEqual(ent["cite"]["table"], "persons")
            self.assertEqual(ent["cite"]["chapters"][0], "ch_002")  # blame 指最新
            self.assertIn("ch_001", ent["cite"]["chapters"])

            for hit in out["lines"]:
                self.assertIn("cite", hit)
                self.assertEqual(hit["cite"]["table"], "lines")
            gun = [h for h in out["lines"] if h["id"] == "GUN-001"][0]
            self.assertIn("ch_001", gun["cite"]["chapters"])  # plant 章
            self.assertIn("ch_009", gun["cite"]["chapters"])  # target 章

            for hit in out["ledger"]:
                self.assertEqual(hit["cite"]["chapters"], [hit["chapter"]])
            self.assertEqual(out["pools_now"]["stone"]["cite"]["chapters"], ["ch_001"])

            for hit in out["events"]:
                self.assertEqual(hit["cite"]["table"], "timeline")
            self.assertEqual(out["current"]["_cite"]["table"], "current")
            self.assertTrue(out["current"]["_cite"]["chapters"])  # blame 有章

            for hit in out["locked"]:
                self.assertEqual(hit["cite"]["table"], "locked")
                self.assertIn("ch_001", hit["cite"]["chapters"])
            for hit in out["cognition"]:
                self.assertEqual(hit["cite"]["table"], "cognition")

            for hit in out["synopsis"]:
                self.assertEqual(hit["cite"]["chapters"], [hit["chapter"]])
            self.assertTrue(out["text_hits"])
            for hit in out["text_hits"]:
                self.assertEqual(hit["cite"]["table"], "final")
                self.assertIn("林牧", hit["quote"])

    def test_miss_stays_honest(self):
        from engine import evidence
        with TempBook() as tb:
            _seed_two_chapters(tb)
            out = evidence.ask(tb.book, "不存在的词XYZ")
            self.assertEqual(out.get("ask_version"), "2.0")
            for k in ("entities", "lines", "ledger", "events", "current",
                      "locked", "cognition", "synopsis", "text_hits"):
                self.assertNotIn(k, out)

    def test_cli_ask_json(self):
        with TempBook() as tb:
            _seed_two_chapters(tb)
            proc = tb.run("ask", "林牧")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            self.assertEqual(out["entities"][0]["cite"]["chapters"][0], "ch_002")


if __name__ == "__main__":
    unittest.main()
