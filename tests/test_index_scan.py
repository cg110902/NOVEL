"""R3 增量索引：memory 读 DB 缓存与文件全扫输出 bit 级等价；过期回退。"""
import unittest

from tests._fixtures import TempBook


def _seed(tb):
    from engine import state
    tb.seed_chapter("ch_001", "林牧拔出断水剑，断水剑缺口在灯下发光。" * 20)
    tb.seed_chapter("ch_002", "张彪在城门口张望，人来人往。" * 20)
    tb.seed_chapter("ch_003", "夜深了，灯铺打烊，四下无声。" * 20)
    p = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
         "operation_id": "ch_001.idx.seed",
         "entities": [{"action": "upsert", "id": "p_001", "name": "林牧",
                       "type": "person"}],
         "lines": [{"action": "plant", "kind": "foreshadow", "id": "GUN-001",
                    "name": "断水剑缺口", "target_ch": 9}],
         "locked": [{"action": "plant", "id": "LOCK-001", "fact": "林牧之刀断于江边",
                     "kind": "destruction", "note": "断刀不可复原", "quote": "咔嚓一声"}]}
    rep = state.apply_proposal(tb.book, p)
    assert rep["errors"] == [], rep["errors"]


class TestIndexScanEquivalence(unittest.TestCase):
    def test_db_cache_equals_file_scan(self):
        from engine import db, memory
        with TempBook() as tb:
            _seed(tb)
            legacy_lines = memory.line_memory_map(tb.book)
            legacy_facts = memory.key_fact_memory(tb.book)
            self.assertTrue(legacy_lines)
            gun = [r for r in legacy_lines if r["id"] == "GUN-001"][0]
            self.assertEqual(gun["last_seen_ch"], 1)
            self.assertEqual(gun["gap"], 2)

            out = db.build_or_update_index(tb.book)
            self.assertTrue(out["ok"])
            self.assertIsNotNone(db.finals_from_index(tb.book))
            self.assertEqual(memory.line_memory_map(tb.book), legacy_lines)
            self.assertEqual(memory.key_fact_memory(tb.book), legacy_facts)

    def test_stale_index_falls_back(self):
        from engine import db, memory
        with TempBook() as tb:
            _seed(tb)
            db.build_or_update_index(tb.book)
            before = memory.line_memory_map(tb.book)
            # 改 ch_003 追加提词 → 指纹失配 → 回退文件扫 → 结果更新
            p = tb.book / "manuscript/vol_01/final/ch_003.md"
            p.write_text(p.read_text(encoding="utf-8") + "\n\n断水剑缺口在月下发光。\n",
                         encoding="utf-8")
            self.assertIsNone(db.finals_from_index(tb.book))
            after = memory.line_memory_map(tb.book)
            gun = [r for r in after if r["id"] == "GUN-001"][0]
            self.assertEqual(gun["last_seen_ch"], 3)
            self.assertEqual(gun["gap"], 0)
            self.assertNotEqual(before, after)
            # 重刷索引后缓存路径给出同样新值
            db.build_or_update_index(tb.book)
            self.assertEqual(memory.line_memory_map(tb.book), after)

    def test_no_index_returns_none(self):
        from engine import db
        with TempBook() as tb:
            _seed(tb)
            self.assertIsNone(db.finals_from_index(tb.book))


if __name__ == "__main__":
    unittest.main()
