"""读者记忆派生层（engine/memory.py）单测 — 2025 一致性改造 R1-c2。

验收对照 PLAN_CONSISTENCY_50W §3.A2（合并读者方案 §3.5 验收清单）。
全部跑真实函数 / 真实书工作区（TempBook 隔离），不用替身实现；
唯一例外是 finals 只读一次的计数桩（包装真实函数计数，不改变行为）。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import evidence, memory  # noqa: E402
from tests._fixtures import TempBook  # noqa: E402


def _finals(book: Path, nums: list[int], body_fn) -> None:
    """给书铺 N 章 final（正文由 body_fn(num) 生成）。"""
    for n in nums:
        p = book / "manuscript" / "vol_01" / "final" / f"ch_{n:03d}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# 第{n}章\n\n{body_fn(n)}\n", encoding="utf-8")


def _lines_state(**entries_by_arr: list) -> dict:
    st = {"foreshadows": [], "misunderstandings": [], "knowledge": []}
    for arr, items in entries_by_arr.items():
        st[arr] = items
    return st


class TestTierOfBoundaries(unittest.TestCase):
    """tier_of 边界：24/25/26、69/70/71、None。"""

    def test_boundaries(self):
        t = dict(memory.DEFAULTS)
        self.assertEqual(memory.tier_of(None, t), "never")
        for g in (0, 1, 24, 25):
            self.assertEqual(memory.tier_of(g, t), "working", f"gap={g}")
        for g in (26, 69, 70):
            self.assertEqual(memory.tier_of(g, t), "fuzzy", f"gap={g}")
        for g in (71, 120):
            self.assertEqual(memory.tier_of(g, t), "impression", f"gap={g}")


class TestColdThreshold(unittest.TestCase):
    """cold_threshold 按 weight 缩放；非法权重按 1 处理。"""

    def test_scaling(self):
        t = dict(memory.DEFAULTS)
        self.assertEqual(memory.cold_threshold(t, 1), 25)
        self.assertEqual(memory.cold_threshold(t, 2), 33)
        self.assertEqual(memory.cold_threshold(t, 3), 41)
        self.assertEqual(memory.cold_threshold(t, 5), 57)

    def test_invalid_weights_fall_back_to_base(self):
        t = dict(memory.DEFAULTS)
        for bad in (None, True, False, "3", 0, -2, 1.5):
            self.assertEqual(memory.cold_threshold(t, bad), 25, f"weight={bad!r}")


class TestScanLastSeen(unittest.TestCase):
    """_scan_last_seen：命中 / 未命中 / 多章取最大 / 空 terms / 乱序取 max（修正 2）。"""

    def test_hit_miss_and_empty(self):
        finals = [("vol_01/ch_001", 1, "林牧摸出玄铁令"), ("vol_01/ch_002", 2, "雨夜赶路"),
                  ("vol_01/ch_005", 5, "玄铁令在袖中发烫")]
        self.assertEqual(memory._scan_last_seen(finals, ["玄铁令"]), (5, 2))
        self.assertEqual(memory._scan_last_seen(finals, ["不存在"]), (None, 0))
        self.assertEqual(memory._scan_last_seen(finals, []), (None, 0))

    def test_max_over_unsorted_finals(self):
        # 乱序 finals（契约：函数取最大章号，不依赖迭代顺序）
        finals = [("vol_01/ch_007", 7, "玄铁令现世"), ("vol_01/ch_003", 3, "玄铁令初现")]
        last, hits = memory._scan_last_seen(finals, ["玄铁令"])
        self.assertEqual((last, hits), (7, 2))


class TestTiersFor(unittest.TestCase):
    """project.json 的 reader_memory 覆盖：合法生效、非法逐键回落、缺省走默认。"""

    def test_defaults_when_missing(self):
        with TempBook() as tb:
            self.assertEqual(memory.tiers_for(tb.book), dict(memory.DEFAULTS))

    def test_override_and_invalid_fallback(self):
        with TempBook() as tb:
            proj = json.loads(tb.read("project.json"))
            proj["reader_memory"] = {"working_window": 30, "fuzzy_window": "八十",
                                     "cold_line_base": 0, "cold_line_per_weight": True}
            tb.write("project.json", json.dumps(proj, ensure_ascii=False))
            got = memory.tiers_for(tb.book)
            self.assertEqual(got["working_window"], 30)          # 合法覆盖生效
            self.assertEqual(got["fuzzy_window"], memory.DEFAULTS["fuzzy_window"])      # 字符串回落
            self.assertEqual(got["cold_line_base"], memory.DEFAULTS["cold_line_base"])  # 0 回落
            self.assertEqual(got["cold_line_per_weight"], memory.DEFAULTS["cold_line_per_weight"])  # bool 回落


class TestLineMemoryMap(unittest.TestCase):
    """never / working / 已闭环排除 / 冷线判定 / 排序。"""

    def test_never_working_resolved_and_sort(self):
        with TempBook() as tb:
            _finals(tb.book, [1, 2, 3], lambda n: f"第{n}回，赤鳞蛇横在山道上。")
            tb.set_state("lines", _lines_state(
                foreshadows=[
                    {"id": "GUN-001", "name": "玄铁令", "plant_ch": 1, "status": "Planted"},
                    {"id": "GUN-002", "name": "赤鳞蛇", "plant_ch": 1, "status": "Planted"},
                    {"id": "GUN-003", "name": "旧账", "plant_ch": 1, "status": "Resolved"},
                ]))
            rows = memory.line_memory_map(tb.book)
            by_id = {r["id"]: r for r in rows}
            self.assertNotIn("GUN-003", by_id, "已闭环线必须被排除")
            self.assertEqual(by_id["GUN-001"]["tier"], "never")
            self.assertIsNone(by_id["GUN-001"]["gap"])
            self.assertIsNone(by_id["GUN-001"]["last_seen_ch"])
            self.assertEqual(by_id["GUN-002"]["tier"], "working")
            self.assertEqual(by_id["GUN-002"]["last_seen_ch"], 3)
            self.assertEqual(by_id["GUN-002"]["gap"], 0)
            self.assertFalse(by_id["GUN-002"]["is_cold"])
            # 排序：有具体 gap 者降序在前，never 殿后
            self.assertEqual(rows[-1]["id"], "GUN-001")
            self.assertEqual(memory.never_surfaced(rows), [by_id["GUN-001"]])

    def test_is_cold_with_weight_scaling(self):
        with TempBook() as tb:
            # 30 章：玄铁令只在第 2 章出现 → gap=28
            _finals(tb.book, list(range(1, 31)), lambda n: "山道无事。" if n != 2 else "玄铁令初现。")
            tb.set_state("lines", _lines_state(
                foreshadows=[
                    {"id": "GUN-001", "name": "玄铁令", "plant_ch": 1, "status": "Planted", "weight": 1},
                    {"id": "GUN-002", "name": "赤鳞蛇", "plant_ch": 1, "status": "Planted", "weight": 3},
                ]))
            rows = {r["id"]: r for r in memory.line_memory_map(tb.book)}
            # weight=1 阈值 25：gap 28 > 25 → 冷
            self.assertTrue(rows["GUN-001"]["is_cold"])
            self.assertEqual(rows["GUN-001"]["cold_threshold"], 25)
            # weight=3 阈值 41：gap 28 ≤ 41 → 不冷
            self.assertFalse(rows["GUN-002"]["is_cold"])
            self.assertEqual(rows["GUN-002"]["cold_threshold"], 41)

    def test_misunderstanding_uses_level_as_weight(self):
        with TempBook() as tb:
            _finals(tb.book, list(range(1, 31)), lambda n: "相安无事。" if n != 2 else "张彪误判了李玄。")
            # 误会双方为已注册实体（真实场景必然如此）：reg_terms 提词张彪/李玄
            tb.set_state("persons", {"entries": [
                {"name": "张彪", "type": "person", "status": "active"},
                {"name": "李玄", "type": "person", "status": "active"},
            ]})
            tb.set_state("lines", _lines_state(
                misunderstandings=[
                    {"id": "MIS-001", "parties": "张彪与李玄", "content": "张彪误判李玄隐忍多年",
                     "status": "Active", "level": 2},
                ]))
            rows = {r["id"]: r for r in memory.line_memory_map(tb.book)}
            self.assertEqual(rows["MIS-001"]["weight"], 2)
            self.assertEqual(rows["MIS-001"]["cold_threshold"], 33)
            self.assertEqual(rows["MIS-001"]["last_seen_ch"], 2)

    def test_empty_book_returns_empty(self):
        with TempBook() as tb:  # init 后无任何 final
            self.assertEqual(memory.line_memory_map(tb.book), [])
            self.assertEqual(memory.key_fact_memory(tb.book), [])


class TestKeyFactMemory(unittest.TestCase):
    """locked + 已揭示 knowledge；未揭示 knowledge 排除。"""

    def test_locked_and_revealed_knowledge(self):
        with TempBook() as tb:
            _finals(tb.book, [1, 2, 3], lambda n: "风平浪静。" if n != 2 else "赵莽倒在血泊里。")
            tb.set_state("persons", {"entries": [
                {"name": "赵莽", "type": "person", "status": "active", "life_status": "deceased"},
            ]})
            tb.set_state("locked", {
                "schema_version": "novel-studio.locked/v1",
                "entries": [{"id": "LOCK-001", "fact": "赵莽死于剑下", "since_ch": "ch_002",
                             "kind": "death", "quote": "赵莽倒在血泊里。"}],
            })
            tb.set_state("lines", _lines_state(
                knowledge=[
                    {"id": "KNO-001", "secret": "断水剑藏于后山", "plant_ch": 1, "status": "Concealed"},
                    {"id": "KNO-002", "secret": "赤鳞蛇守着断水剑", "plant_ch": 1, "status": "Revealed"},
                ],
                foreshadows=[
                    {"id": "GUN-009", "name": "赤鳞蛇", "plant_ch": 1, "status": "Planted"},
                ]))
            rows = memory.key_fact_memory(tb.book)
            by_id = {r["id"]: r for r in rows}
            self.assertNotIn("KNO-001", by_id, "未揭示 knowledge 必须排除")
            self.assertIn("LOCK-001", by_id)
            self.assertIn("KNO-002", by_id)
            self.assertEqual(by_id["LOCK-001"]["last_seen_ch"], 2)  # 命中正文专名「赵莽」
            self.assertEqual(by_id["LOCK-001"]["gap"], 1)
            self.assertEqual(by_id["LOCK-001"]["since_ch"], 2)
            # KNO-002 提词含「赤鳞蛇」，正文无 → never（模块 docstring 盲区的正例）
            self.assertEqual(by_id["KNO-002"]["tier"], "never")


class TestFinalsReadOnce(unittest.TestCase):
    """finals 只读一次（每公开函数入口）：计数桩断言读盘次数不随线数增长。"""

    def test_line_memory_map_reads_finals_once(self):
        with TempBook() as tb:
            _finals(tb.book, [1, 2], lambda n: "无事。")
            tb.set_state("lines", _lines_state(
                foreshadows=[{"id": f"GUN-{i:03d}", "name": f"线{i}", "plant_ch": 1,
                              "status": "Planted"} for i in range(1, 6)]))
            original = evidence.final_chapters
            calls = {"n": 0}

            def counted(book):
                calls["n"] += 1
                return original(book)

            evidence.final_chapters = counted
            try:
                rows = memory.line_memory_map(tb.book)
            finally:
                evidence.final_chapters = original
            self.assertEqual(len(rows), 5)
            self.assertEqual(calls["n"], 1, "line_memory_map 必须只读一遍 finals，与线数无关")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# R2-c5：三条读者记忆闸门（advisory，全部 warning 级）
# ---------------------------------------------------------------------------
from engine import checks as checks_mod  # noqa: E402

_BEATS_COLD = """---
chapter: {ch}
vol: vol_01
form: 危机逼近
pov: 主角视角
words: 2000-3000
tension_curve: 逼近 → 破局
tension_score: 6
stage_mode: Simmering
style_notes: 通俗直白大白话
---

## 本章坐标与核心戏剧目标

- **本章核心戏剧目标**：主角回收旧伏笔。

## 交付契约

- **核心看点**：旧线兑现。
- **验收要点**：
  1. 主角取得物证。

## 线索动作

- resolve GUN-001（回收玄铁令）
"""


def _warning_codes(report: dict) -> set[str]:
    out = set()
    for section in ("system_health", "narrative_health"):
        for item in report.get(section, {}).get("warnings", []) or []:
            out.add(item.get("code"))
    return out


class TestReaderMemoryGates(unittest.TestCase):

    def test_gate1_line_never_surfaced(self):
        with TempBook() as tb:
            _finals(tb.book, [1, 2, 3], lambda n: "赤鳞蛇横在山道上。")
            tb.set_state("lines", _lines_state(
                foreshadows=[{"id": "GUN-001", "name": "玄铁令", "plant_ch": 1,
                              "status": "Planted"}]))
            codes = _warning_codes(checks_mod.run_checks(tb.book))
            self.assertIn("line_never_surfaced", codes)

    def test_gate1_not_fired_when_surfaced(self):
        with TempBook() as tb:
            _finals(tb.book, [1, 2, 3], lambda n: "玄铁令在袖中发烫。")
            tb.set_state("lines", _lines_state(
                foreshadows=[{"id": "GUN-001", "name": "玄铁令", "plant_ch": 1,
                              "status": "Planted"}]))
            codes = _warning_codes(checks_mod.run_checks(tb.book))
            self.assertNotIn("line_never_surfaced", codes)

    def test_gate2_line_recall_cold(self):
        with TempBook() as tb:
            # 玄铁令只在 ch_002 出现 → gap=28 > 25（weight=1 阈值）
            _finals(tb.book, list(range(1, 31)), lambda n: "山道无事。" if n != 2 else "玄铁令初现。")
            tb.set_state("lines", _lines_state(
                foreshadows=[{"id": "GUN-001", "name": "玄铁令", "plant_ch": 1,
                              "status": "Planted"}]))
            tb.write("outlines/vol_01/beats/ch_030.md", _BEATS_COLD.format(ch="ch_030"))
            report = checks_mod.run_checks(tb.book)
            codes = _warning_codes(report)
            self.assertIn("line_recall_cold", codes)
            # 线在 ch_002 出现过一次 → 不是 never 档（闸门 1 只报零出现）
            self.assertNotIn("line_never_surfaced", codes)

    def test_gate2_not_fired_when_recent(self):
        with TempBook() as tb:
            # 最近一章仍提及 → gap=0 不冷 → 不报
            _finals(tb.book, list(range(1, 31)), lambda n: "山道无事。" if n < 30 else "玄铁令再现。")
            tb.set_state("lines", _lines_state(
                foreshadows=[{"id": "GUN-001", "name": "玄铁令", "plant_ch": 1,
                              "status": "Planted"}]))
            tb.write("outlines/vol_01/beats/ch_030.md", _BEATS_COLD.format(ch="ch_030"))
            codes = _warning_codes(checks_mod.run_checks(tb.book))
            self.assertNotIn("line_recall_cold", codes)

    def test_gate2_not_fired_for_resolved_line(self):
        with TempBook() as tb:
            _finals(tb.book, list(range(1, 31)), lambda n: "山道无事。" if n != 2 else "玄铁令初现。")
            tb.set_state("lines", _lines_state(
                foreshadows=[{"id": "GUN-001", "name": "玄铁令", "plant_ch": 1,
                              "status": "Resolved"}]))
            tb.write("outlines/vol_01/beats/ch_030.md", _BEATS_COLD.format(ch="ch_030"))
            codes = _warning_codes(checks_mod.run_checks(tb.book))
            self.assertNotIn("line_recall_cold", codes)
            self.assertNotIn("line_never_surfaced", codes)

    def test_gate3_reader_memory_stale_with_config_override(self):
        with TempBook() as tb:
            # 覆盖阈值让测试轻量化：working 3 / fuzzy 6 → gap ≥ 7 即印象区
            proj = json.loads(tb.read("project.json"))
            proj["reader_memory"] = {"working_window": 3, "fuzzy_window": 6,
                                     "cold_line_base": 3, "cold_line_per_weight": 1}
            tb.write("project.json", json.dumps(proj, ensure_ascii=False))
            _finals(tb.book, list(range(1, 21)), lambda n: "风平浪静。" if n != 2 else "赵莽倒在血泊里。")
            tb.set_state("persons", {"entries": [
                {"name": "赵莽", "type": "person", "status": "active", "life_status": "deceased"}]})
            tb.set_state("locked", {
                "schema_version": "novel-studio.locked/v1",
                "entries": [{"id": "LOCK-001", "fact": "赵莽死于剑下", "since_ch": "ch_002",
                             "kind": "death", "quote": "赵莽倒在血泊里。"}]})
            codes = _warning_codes(checks_mod.run_checks(tb.book))
            self.assertIn("reader_memory_stale", codes)

    def test_gate3_not_fired_when_recent(self):
        with TempBook() as tb:
            _finals(tb.book, [1, 2], lambda n: "赵莽倒在血泊里。")
            tb.set_state("persons", {"entries": [
                {"name": "赵莽", "type": "person", "status": "active"}]})
            tb.set_state("locked", {
                "schema_version": "novel-studio.locked/v1",
                "entries": [{"id": "LOCK-001", "fact": "赵莽死于剑下", "since_ch": "ch_001",
                             "kind": "death", "quote": "赵莽倒在血泊里。"}]})
            codes = _warning_codes(checks_mod.run_checks(tb.book))
            self.assertNotIn("reader_memory_stale", codes)

    def test_no_finals_no_reader_memory_noise(self):
        with TempBook() as tb:
            tb.set_state("lines", _lines_state(
                foreshadows=[{"id": "GUN-001", "name": "玄铁令", "plant_ch": 1,
                              "status": "Planted"}]))
            codes = _warning_codes(checks_mod.run_checks(tb.book))
            self.assertNotIn("line_never_surfaced", codes)
            self.assertNotIn("line_recall_cold", codes)
            self.assertNotIn("reader_memory_stale", codes)

    def test_param_spec_mem_map_validation(self):
        self.assertIsNone(checks_mod.validate_param_value(
            "reader_memory", {"working_window": 30}))
        self.assertIsNotNone(checks_mod.validate_param_value(
            "reader_memory", {"fuzzy_window": "八十"}))
        self.assertIsNotNone(checks_mod.validate_param_value(
            "reader_memory", {"unknown_key": 5}))
        self.assertIsNotNone(checks_mod.validate_param_value(
            "reader_memory", [25, 70]))

    def test_three_codes_registered_as_warning(self):
        from engine import errcodes
        for code in ("line_never_surfaced", "line_recall_cold", "reader_memory_stale"):
            self.assertIn(code, errcodes.REGISTRY)
            self.assertEqual(errcodes.REGISTRY[code].level, "warning", code)
            self.assertNotIn(code, checks_mod.SYSTEM_CHECK_CODES,
                             f"{code} 应入叙事核（不入 SYSTEM_CHECK_CODES）")
