"""事件溯源层（engine/changelog.py）单测 — 2025 一致性改造 R1-c3。

核心不变量：fold(base, events) == 磁盘八表（verify 消费）。
覆盖：diff/fold 往返、genesis、提案事件流、手术刀、外部改动补录、
回滚存续、尾行自愈、无变化零事件、verify 语义。
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import changelog, common, state  # noqa: E402
from tests._fixtures import TempBook  # noqa: E402

_AUDIT_OK = """---
hard: 0
adjudicated: false
---

# 仲裁报告

机械探针零命中。
"""


def _proposal(ch: str, op_id: str) -> dict:
    return {
        "schema": "novel-studio.state-mutation/v2", "chapter": ch,
        "operation_id": op_id,
        "current": {"mood": "警惕", "location": "城隍庙"},
        "entities": [{"action": "upsert", "id": "p_002", "name": "张彪",
                      "type": "person", "summary": "庙祝，实为暗桩"}],
        "lines": [{"kind": "foreshadow", "action": "plant", "id": "GUN-001",
                   "name": "玄铁令", "target_ch": 5}],
        "ledger": {"transactions": [{"chapter": ch, "pool": "standard_currency",
                                     "delta": -30, "subject": "买香烛"}]},
    }


class TestDiffFoldRoundtrip(unittest.TestCase):
    """diff 与 fold 互为逆运算：fold(old, diff(old,new)) == new。"""

    CASES = [
        # 叶子变化 / 增删键
        ({"a": 1, "b": {"c": 2}}, {"a": 1, "b": {"c": 3, "d": 4}, "e": 5}),
        # 带键列表：改字段 / 增删条目
        ({"entries": [{"id": "p_001", "name": "甲", "holder": "x"},
                      {"id": "p_002", "name": "乙"}]},
         {"entries": [{"id": "p_001", "name": "甲", "holder": "y"},
                      {"id": "p_003", "name": "丙"}]}),
        # 无键 dict 列表：中段改 + 尾部追加
        ({"events": [{"time": "d1", "event": "a"}, {"time": "d2", "event": "b"}]},
         {"events": [{"time": "d1", "event": "a"}, {"time": "d2", "event": "b2"},
                     {"time": "d3", "event": "c"}]}),
        # 无键 dict 列表：尾部截断
        ({"tx": [{"n": 1}, {"n": 2}, {"n": 3}]}, {"tx": [{"n": 1}]}),
        # 标量列表整体替换 / 变空
        ({"aliases": ["甲", "乙"]}, {"aliases": ["乙", "丙"]}),
        ({"aliases": ["甲"]}, {"aliases": []}),
        # 嵌套：带键列表内字段的子结构
        ({"entries": [{"id": "it_001", "address_matrix": {"李玄": "道友"},
                       "aliases": ["断水剑"]}]},
         {"entries": [{"id": "it_001", "address_matrix": {"李玄": "李兄",
                                                          "张彪": "庙祝"},
                       "aliases": ["断水剑", "水剑"]}]}),
        # 整表 None → dict
        (None, {"pools": {"silver": {"initial": 0}}}),
    ]

    def test_roundtrip_all_cases(self):
        for i, (old, new) in enumerate(self.CASES):
            with self.subTest(case=i):
                ops = changelog.diff_states(old, new)
                holder = {} if old is None else copy.deepcopy(old)
                # 模拟事件应用：holder 扮演单表根
                for o in ops:
                    changelog._apply_op(holder, o["path"], o["op"], o.get("after"))
                self.assertEqual(holder, new if new is not None else {})


class TestGenesisAndNoChange(unittest.TestCase):

    def test_init_activates_changelog(self):
        with TempBook() as tb:
            self.assertTrue(changelog.active(tb.book))
            events = changelog.load_events(tb.book)
            self.assertEqual(events[0].get("kind"), "genesis")
            base = common.load_json(changelog.base_path(tb.book), default={}) or {}
            self.assertEqual(set(base), set(state.STATE_KEYS))
            ok, msg = changelog.verify(tb.book)
            self.assertTrue(ok, msg)

    def test_no_change_save_is_silent(self):
        with TempBook() as tb:
            data = state.load_state(tb.book, "current")
            n0 = len(changelog.load_events(tb.book))
            state.save_state(tb.book, "current", data, source="engine")
            self.assertEqual(len(changelog.load_events(tb.book)), n0,
                             "幂等写（无变化）不得产生事件")


class TestProposalFlow(unittest.TestCase):

    def test_sync_emits_proposal_events_and_seal(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进城隍庙，张彪递上一炷香。" * 60)
            tb.write("log/audit/ch_001.md", _AUDIT_OK)
            tb.write("state/inbox/ch_001.json",
                     json.dumps(_proposal("ch_001", "ch_001.reader.t1"), ensure_ascii=False))
            out = tb.run_json("sync", "ch_001")
            self.assertTrue(out.get("snapshot", {}).get("ok"), out)

            events = changelog.load_events(tb.book)
            data_events = [e for e in events if not e.get("kind")]
            self.assertTrue(data_events)
            self.assertTrue(all(e["source"] == "proposal" for e in data_events))
            self.assertTrue(all(e["ch"] == "ch_001" for e in data_events))
            self.assertTrue(all(e["op_id"] == "ch_001.reader.t1" for e in data_events))
            # 覆盖各分区：current/entities/lines/ledger 都有事件
            tables = {e["table"] for e in data_events}
            self.assertIn("current", tables)
            self.assertIn("entities", tables)
            self.assertIn("lines", tables)
            self.assertIn("ledger", tables)
            # 路径寻址样例：实体按 id、流水按下标
            paths = {e["path"] for e in data_events}
            self.assertTrue(any("p_002" in p for p in paths), paths)
            self.assertTrue(any(p.startswith("transactions[") for p in paths), paths)
            # 封存锚点
            seals = [e for e in events if e.get("kind") == "chapter_sealed"]
            self.assertEqual(len(seals), 1)
            self.assertEqual(seals[0]["ch"], "ch_001")
            # 核心不变量
            ok, msg = changelog.verify(tb.book)
            self.assertTrue(ok, msg)

    def test_surgery_emits_state_set_event(self):
        with TempBook() as tb:
            out = tb.run_json("state", "set", "current.mood", "紧张")
            self.assertNotIn("error", out if isinstance(out, dict) else {})
            data_events = [e for e in changelog.load_events(tb.book) if not e.get("kind")]
            self.assertEqual(len(data_events), 1)
            self.assertEqual(data_events[0]["source"], "state_set")
            self.assertEqual(data_events[0]["path"], "mood")
            self.assertEqual(data_events[0]["after"], "紧张")
            ok, msg = changelog.verify(tb.book)
            self.assertTrue(ok, msg)


class TestExternalEdit(unittest.TestCase):

    def test_offline_write_is_captured_on_next_load(self):
        with TempBook() as tb:
            cur = tb.state("current")
            cur["mood"] = "被外部篡改"
            tb.set_state("current", cur)
            # 尚未经过 load_state → verify 报不一致（检测语义）
            ok, _ = changelog.verify(tb.book)
            self.assertFalse(ok, "未补录前 verify 必须报不一致")
            # 任意一次 load_state（此处走 CLI state get）触发补录
            got = tb.run_json("state", "get", "current.mood")
            self.assertEqual(got.get("value"), "被外部篡改")
            events = [e for e in changelog.load_events(tb.book) if not e.get("kind")]
            ext = [e for e in events if e["source"] == "external_edit"]
            self.assertEqual(len(ext), 1)
            self.assertEqual(ext[0]["path"], "mood")
            self.assertEqual(ext[0]["after"], "被外部篡改")
            # 补录后 verify 通过；再次读取不重复补录
            ok, msg = changelog.verify(tb.book)
            self.assertTrue(ok, msg)
            tb.run_json("state", "get", "current.mood")
            ext2 = [e for e in changelog.load_events(tb.book)
                    if not e.get("kind") and e["source"] == "external_edit"]
            self.assertEqual(len(ext2), 1)


class TestRollbackSurvival(unittest.TestCase):

    def test_rollback_keeps_log_and_records_event(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进城隍庙。" * 60)
            tb.write("log/audit/ch_001.md", _AUDIT_OK)
            tb.write("state/inbox/ch_001.json",
                     json.dumps(_proposal("ch_001", "ch_001.reader.t2"), ensure_ascii=False))
            self.assertTrue(tb.run_json("sync", "ch_001").get("snapshot", {}).get("ok"))
            n_before = len(changelog.load_events(tb.book))
            # 封存后手术刀改一笔，再回滚到封存点（手术刀之前的快照）
            tb.run_json("state", "set", "current.mood", "临时的")
            self.assertGreater(len(changelog.load_events(tb.book)), n_before)
            out = tb.run("snapshot", "rollback", "ch_001_done")
            self.assertEqual(out.returncode, 0, out.stderr)
            # 事件流存续且回滚被记录
            events = changelog.load_events(tb.book)
            self.assertGreaterEqual(len(events), n_before, "回滚不得清空事件流")
            rb = [e for e in events if e.get("source") == "snapshot_rollback"]
            self.assertTrue(rb, "必须存在 snapshot_rollback 事件")
            # 回滚后核心不变量仍成立
            ok, msg = changelog.verify(tb.book)
            self.assertTrue(ok, msg)
            # changelog 三件套仍在
            for name in changelog.CHANGELOG_FILES:
                self.assertTrue((tb.book / "state" / name).is_file(), name)


class TestTailSelfHealing(unittest.TestCase):

    def test_truncated_tail_is_dropped_and_appending_still_works(self):
        with TempBook() as tb:
            p = changelog.changelog_path(tb.book)
            with p.open("a", encoding="utf-8") as fh:
                fh.write('{"seq": 99, "ts": "xx')  # 模拟崩溃残行
            events = changelog.load_events(tb.book)
            self.assertFalse(any(e.get("seq") == 99 for e in events))
            # 自愈截断后继续追加正常
            state.save_state(tb.book, "current", {"time": "", "mood": "重建"},
                             source="state_set")
            events = changelog.load_events(tb.book)
            self.assertTrue(any(e.get("source") == "state_set" for e in events))
            seqs = [e["seq"] for e in events]
            self.assertEqual(seqs, sorted(seqs), "seq 必须单调")


if __name__ == "__main__":
    unittest.main()
