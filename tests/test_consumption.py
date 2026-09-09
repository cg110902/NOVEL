"""R0 还债包：v2 裸字段的真实消费回归测试。"""
import io
import json
import unittest
from contextlib import redirect_stdout

from tests._fixtures import TempBook


def _prop(ch="ch_001", op="ch_001.test.01", **kw):
    p = {"schema": "novel-studio.state-mutation/v2", "chapter": ch, "operation_id": op}
    p.update(kw)
    return p


def _seed_cast(tb):
    from engine import state
    rep = state.apply_proposal(tb.book, _prop(
        entities=[
            {"name": "林牧", "id": "p_001", "type": "person",
             "injury_level": 3, "injury_desc": "左臂骨折", "renown": 50,
             "relations": [{"target": "赵莽", "type": "宿敌", "strength": 5},
                           {"target": "孙二", "type": "旧识", "strength": 1}]},
            {"name": "赵莽", "id": "p_002", "type": "person"},
            {"name": "孙二", "id": "p_003", "type": "person"},
        ],
        current={"present_characters": ["林牧"], "time_day": 9},
    ))
    assert rep["errors"] == [], rep["errors"]


class TestPackConsumption(unittest.TestCase):
    def test_injury_and_renown_injected(self):
        from engine import pack
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧拔剑。")
            _seed_cast(tb)
            payload = pack.build_pack(tb.book, "ch_001")
            blocks = {e.get("name"): e for e in (payload["p1"] or {}).get("entities", [])}
            self.assertIn("林牧", blocks)
            self.assertEqual(blocks["林牧"]["injury"], "Lv3：左臂骨折")
            self.assertEqual(blocks["林牧"]["renown"], 50)
            # 健康实体不刷噪声键
            if "赵莽" in blocks:
                self.assertNotIn("injury", blocks["赵莽"])
                self.assertNotIn("renown", blocks["赵莽"])


class TestGraphConsumption(unittest.TestCase):
    def test_edge_weight_and_neighbor_order(self):
        from engine import graph
        with TempBook() as tb:
            _seed_cast(tb)
            G = graph.build_narrative_graph(tb.book)
            self.assertEqual(G["林牧"]["赵莽"]["weight"], 5)
            self.assertEqual(G["林牧"]["孙二"]["weight"], 1)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = graph.cmd_neighbors(G, "林牧", as_json=True)
            self.assertEqual(rc, 0)
            names = [n["name"] for n in json.loads(buf.getvalue())["neighbors"]]
            self.assertLess(names.index("赵莽"), names.index("孙二"))


class TestSimulateConsumption(unittest.TestCase):
    def test_impact_relations_sorted_by_strength(self):
        from engine.commands import simulate
        with TempBook() as tb:
            _seed_cast(tb)
            out = simulate.simulate_impact(tb.book, entity="林牧", action="kill")
            rels = out["affected_relations"]
            self.assertEqual([r["target"] for r in rels], ["赵莽", "孙二"])
            self.assertEqual(rels[0]["strength"], 5)


class TestRecallConsumption(unittest.TestCase):
    def test_story_day_and_entity_injuries(self):
        from engine.commands import recall
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧拔剑。")
            _seed_cast(tb)
            d = recall.run_recall(tb.book)
            self.assertEqual(d["story_day"], 9)
            inj = {i["name"]: i for i in d["irreversible_facts"]["entity_injuries"]}
            self.assertEqual(inj["林牧"]["injury_level"], 3)
            md = recall.render_recall_markdown(d)
            self.assertIn("故事第 9 日", md)
            self.assertIn("左臂骨折", md)


if __name__ == "__main__":
    unittest.main()
