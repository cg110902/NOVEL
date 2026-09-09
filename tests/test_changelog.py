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


class TestScorecardCurve(unittest.TestCase):
    """D3 分数曲线：check 积累 / --trend 消费 / stdout 契约。—— R1-c4"""

    def test_check_appends_and_trend_reads(self):
        with TempBook() as tb:
            r1 = tb.run_json("check")
            self.assertNotIn("error", r1)
            r2 = tb.run_json("check")
            self.assertNotIn("error", r2)
            p = tb.path("log/scorecard.jsonl")
            self.assertTrue(p.is_file())
            rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
            self.assertEqual(len(rows), 2)
            self.assertIn("errors", rows[0])
            self.assertIn("by_code", rows[0])
            # --trend --json：返回历史行，不跑体检、不新增行
            trend = tb.run_json("check", "--trend")
            self.assertEqual(len(trend.get("trend", [])), 2)
            rows2 = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
            self.assertEqual(len(rows2), 2, "trend 模式不得追加记录")
            # 文本模式
            out = tb.run("check", "--trend")
            self.assertEqual(out.returncode, 0)
            self.assertIn("分数曲线", out.stdout)


class TestLockedNoteRequired(unittest.TestCase):
    """A4：locked.note 提案层必填（存量书不动）。—— R2-c6"""

    def _locked_proposal(self, note=None):
        item = {"action": "plant", "id": "LOCK-003", "fact": "赵莽死于剑下",
                "kind": "death", "since_ch": "ch_001", "quote": "赵莽倒在血泊里。"}
        if note is not None:
            item["note"] = note
        return {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
                "operation_id": "ch_001.reader.locked", "locked": [item]}

    def test_missing_note_rejected_with_rationale(self):
        errors, _ = state.validate_proposal(self._locked_proposal())
        self.assertTrue(any("note 必填" in e and "写作红线" in e for e in errors), errors)

    def test_blank_note_rejected(self):
        errors, _ = state.validate_proposal(self._locked_proposal(note="   "))
        self.assertTrue(any("note 必填" in e for e in errors), errors)

    def test_valid_note_passes_and_persists(self):
        with TempBook() as tb:
            rep = state.apply_proposal(tb.book, self._locked_proposal(note="严禁再次出场，回忆除外"))
            self.assertEqual(rep["errors"], [], rep["errors"])
            persisted = tb.state("locked")["entries"]
            self.assertEqual(len(persisted), 1)
            self.assertEqual(persisted[0]["note"], "严禁再次出场，回忆除外")

    def test_retire_still_only_needs_reason(self):
        # 退役通道不受影响：reason 瞬态字段照旧
        prop = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
                "operation_id": "ch_001.reader.retire",
                "locked": [{"action": "retire", "id": "LOCK-009", "reason": "误登"}]}
        errors, _ = state.validate_proposal(prop)
        self.assertFalse(any("note 必填" in e for e in errors), errors)

    def test_legacy_book_without_note_unaffected(self):
        # 存量兼容：磁盘上无 note 的旧条目，load/check 不得新增错误
        with TempBook() as tb:
            tb.set_state("locked", {
                "schema_version": "novel-studio.locked/v1",
                "entries": [{"id": "LOCK-001", "fact": "灯铺被烧毁",
                             "since_ch": "ch_001", "kind": "destruction",
                             "quote": "门口站着一个人"}]})
            loaded = state.load_state(tb.book, "locked")  # 不得抛错
            self.assertEqual(len(loaded["entries"]), 1)
            out = tb.run_json("check")
            self.assertNotIn("error", out)


class TestBisectSnapshots(unittest.TestCase):
    """B4：check --bisect 快照不变量二分定位。—— R2-c8"""

    def _seal(self, tb, ch: str):
        tb.seed_chapter(ch, "林牧走进城隍庙，张彪递上一炷香。" * 60)
        tb.write(f"log/audit/{ch}.md", _AUDIT_OK)
        tb.write(f"state/inbox/{ch}.json", json.dumps({
            "schema": "novel-studio.state-mutation/v2", "chapter": ch,
            "operation_id": f"{ch}.reader.b4",
            "synopsis": {"text": "推进一章。"}}, ensure_ascii=False))
        out = tb.run_json("sync", ch)
        self.assertTrue(out.get("snapshot", {}).get("ok"), out)

    def test_bisect_locates_first_break(self):
        with TempBook() as tb:
            self._seal(tb, "ch_001")
            self._seal(tb, "ch_002")
            # 全健康 → 无破坏点
            out = tb.run_json("check", "--bisect")
            self.assertIsNone(out.get("first_break"))
            # 手工破坏账本算术并拍快照
            led = tb.state("ledger")
            led["pools"]["standard_currency"]["current"] = 999  # 与流水不一致
            tb.set_state("ledger", led)
            tb.run("snapshot", "create", "broken_point")
            out = tb.run_json("check", "--bisect")
            self.assertIn("broken_point", str(out.get("first_break")))
            self.assertIsNotNone(out.get("previous_ok"))
            rows = out.get("rows", [])
            self.assertTrue(rows, "至少包含当前 state 一站")

    def test_bisect_no_snapshots_still_scans_live(self):
        with TempBook() as tb:
            out = tb.run_json("check", "--bisect")
            names = [r["name"] for r in out.get("rows", [])]
            self.assertEqual(names, ["(当前 state)"])
            self.assertIsNone(out.get("first_break"))

    def test_bisect_text_mode(self):
        with TempBook() as tb:
            self._seal(tb, "ch_001")
            out = tb.run("check", "--bisect")
            self.assertEqual(out.returncode, 0)
            self.assertIn("快照不变量二分", out.stdout)


class TestStateAtAndBlame(unittest.TestCase):
    """B2 state at / diff + B3 blame —— R3（快照金标准交叉验证）。"""

    def _seal_two_chapters(self, tb):
        tb.seed_chapter("ch_001", "林牧走进城隍庙，张彪递上一炷香。" * 60)
        tb.write("log/audit/ch_001.md", _AUDIT_OK)
        tb.write("state/inbox/ch_001.json", json.dumps({
            "schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
            "operation_id": "ch_001.reader.a",
            "current": {"mood": "警惕"},
            "entities": [{"action": "upsert", "id": "p_002", "name": "张彪",
                          "type": "person", "summary": "庙祝"}],
            "lines": [{"kind": "foreshadow", "action": "plant", "id": "GUN-001",
                       "name": "玄铁令", "target_ch": 5}]}, ensure_ascii=False))
        self.assertTrue(tb.run_json("sync", "ch_001").get("snapshot", {}).get("ok"))
        # 封存之间做一次手术刀（属于 ch_001 与 ch_002 之间的「进行中」世界）
        tb.run_json("state", "set", "current.mood", "过渡态")
        tb.seed_chapter("ch_002", "林牧夜探后院，挖出玄铁令。" * 60)
        tb.write("log/audit/ch_002.md", _AUDIT_OK)
        tb.write("state/inbox/ch_002.json", json.dumps({
            "schema": "novel-studio.state-mutation/v2", "chapter": "ch_002",
            "operation_id": "ch_002.reader.b",
            "current": {"mood": "恍然"},
            "lines": [{"kind": "foreshadow", "action": "plant", "id": "GUN-002",
                       "name": "灯下黑", "target_ch": 9}]}, ensure_ascii=False))
        self.assertTrue(tb.run_json("sync", "ch_002").get("snapshot", {}).get("ok"))

    def test_state_at_matches_seal_snapshot_golden(self):
        with TempBook() as tb:
            self._seal_two_chapters(tb)
            at1 = tb.run_json("state", "at", "ch_001")
            tables = at1.get("tables", {})
            # 切面语义：ch_001 世界 = P1 已生效、手术刀与 P2 未发生
            self.assertEqual(tables["current"]["mood"], "警惕")
            ids = {g["id"] for g in tables["lines"]["foreshadows"]}
            self.assertEqual(ids, {"GUN-001"})
            # 快照金标准：fold(ch_001 seal) 与 ch_001_done 快照逐表等值
            snap_dir = next(d for d in (tb.path("state/snapshots")).iterdir()
                            if "ch_001_done" in d.name)
            for key in state.STATE_KEYS:
                disk = json.loads((snap_dir / f"{key}.json").read_text(encoding="utf-8"))
                self.assertEqual(common.canonical_json_hash(disk),
                                 common.canonical_json_hash(tables.get(key)),
                                 f"{key} 切面与封存快照不一致")
            # ch_002 切面 == 当前磁盘
            at2 = tb.run_json("state", "at", "ch_002")
            for key in state.STATE_KEYS:
                live = state.load_state(tb.book, key)
                self.assertEqual(common.canonical_json_hash(live),
                                 common.canonical_json_hash(at2["tables"].get(key)),
                                 f"{key} 最新切面与当前状态不一致")

    def test_state_at_beyond_latest_folds_to_latest(self):
        with TempBook() as tb:
            self._seal_two_chapters(tb)
            out = tb.run_json("state", "at", "ch_999")
            self.assertEqual(out["tables"]["current"]["mood"], "恍然")

    def test_state_at_table_filter(self):
        with TempBook() as tb:
            self._seal_two_chapters(tb)
            out = tb.run_json("state", "at", "ch_001", "--table", "current")
            self.assertEqual(out["table"], "current")
            self.assertEqual(out["state"]["mood"], "警惕")

    def test_diff_points(self):
        with TempBook() as tb:
            self._seal_two_chapters(tb)
            out = tb.run_json("state", "diff", "ch_001", "ch_002")
            diff = out.get("diff", {})
            self.assertIn("current", diff)
            paths = {o["path"] for o in diff["current"]}
            self.assertIn("mood", paths)
            self.assertIn("lines", diff)
            same = tb.run_json("state", "diff", "ch_001", "ch_001")
            self.assertEqual(same.get("diff"), {})

    def test_blame_reverse_chron_and_scoping(self):
        with TempBook() as tb:
            self._seal_two_chapters(tb)
            out = tb.run_json("state", "blame", "current.mood")
            events = out.get("events", [])
            self.assertGreaterEqual(len(events), 3, events)
            seqs = [e["seq"] for e in events]
            self.assertEqual(seqs, sorted(seqs, reverse=True), "必须新→旧")
            sources = {e["source"] for e in events}
            self.assertIn("proposal", sources)
            self.assertIn("state_set", sources)
            # 全表 blame 与路径段边界
            full = tb.run_json("state", "blame", "lines")
            self.assertGreaterEqual(full["count"], 2)
            narrow = tb.run_json("state", "blame", "lines.foreshadows[GUN-001]")
            self.assertLessEqual(narrow["count"], full["count"])
            for e in narrow["events"]:
                self.assertTrue(e["path"] == "foreshadows[GUN-001]"
                                or e["path"].startswith("foreshadows[GUN-001]."))

    def test_blame_unknown_table_rejected(self):
        with TempBook() as tb:
            out = tb.run_json("state", "blame", "not_a_table")
            self.assertFalse(out.get("ok", True))

    def test_blame_inactive_book(self):
        # 老书（无 changelog）：明确人话提示而非裸错
        with TempBook() as tb:
            for name in changelog.CHANGELOG_FILES:
                (tb.book / "state" / name).unlink()
            out = tb.run_json("state", "blame", "current")
            self.assertFalse(out.get("ok", True))
            self.assertIn("事件流", out.get("error", ""))
