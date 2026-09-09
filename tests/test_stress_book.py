"""压力样书终局验收（PLAN_CONSISTENCY_50W.md §8 / R4 验收门）— 2025 一致性改造 c13。

200 章 × 4 卷程序化样书（tests/_stress_book.py 构建，走真实提案→封存流水线）：
五类已知吃书全部命中、未植入问题零新增 error、性能达标、D1 上下文经济学达标。
"""
from __future__ import annotations

import json
import sys
import time
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import changelog, common, memory, pack  # noqa: E402
from tests._stress_book import run_cli, stress_book  # noqa: E402

# 预期基线 warnings：植入命中码 + 样书固有 advisory（20 条线按 §8 设计必然超 8 条软配额）
_IMPLANT_CODES = {"tier_shift_without_event", "line_recall_cold", "line_never_surfaced",
                  "state_offline_edit"}
_BASELINE_CODES = {"line_quota_exceeded"}


class TestStressBook(unittest.TestCase):
    """构建一次共享（类属性懒加载），测试顺序无关。"""

    _book = None
    _manifest = None
    _check = None

    @classmethod
    def _ensure(cls):
        if cls._book is None:
            cls._book, cls._manifest = stress_book()
            r = run_cli(cls._book, "check", "--json")
            cls._check = json.loads(r.stdout)
        return cls._book

    # ---- §8.2 植入命中与无误报 ----

    def test_zero_errors_clean_baseline(self):
        """未植入问题的 190+ 章零新增 error（植入均为 warning 级，errors 必须为空）。"""
        book = self._ensure()
        self.assertEqual(self._check.get("errors", []),
                         [], f"压力样书不应有任何 error")

    def test_all_five_implants_detected(self):
        """五类已知吃书全部被指名命中。"""
        self._ensure()
        got = Counter(w["code"] for w in self._check.get("warnings", []))
        for code in _IMPLANT_CODES:
            self.assertIn(code, got, f"植入未命中: {code}")
        # 零落笔线恰为植入的 2 条（无误报）
        self.assertEqual(got.get("line_never_surfaced"), 2)
        self.assertEqual(got.get("tier_shift_without_event"), 1)
        self.assertEqual(got.get("line_recall_cold"), 1)
        self.assertEqual(got.get("state_offline_edit"), 1)

    def test_warning_codes_within_expected_baseline(self):
        """除植入码与样书固有 advisory 外，无其他噪声码（闸门族不被样书误触发）。"""
        self._ensure()
        got = {w["code"] for w in self._check.get("warnings", [])}
        extra = got - _IMPLANT_CODES - _BASELINE_CODES
        self.assertFalse(extra, f"出现计划外 warning 码: {extra}")

    def test_implant_external_edit_event(self):
        """植入④a：中途手改 → changelog 补记 external_edit 事件（事件流可追平磁盘）。"""
        book = self._ensure()
        # check 已吸收植入④b 的手改，先验证一致性
        ok, msg = changelog.verify(book)
        self.assertTrue(ok, msg)
        evs = changelog.load_events(book)
        ext = [e for e in evs if e.get("source") == "external_edit"]
        self.assertGreaterEqual(len(ext), 2, "中途手改与卷末手改均应补记 external_edit")

    def test_implant_holder_blame(self):
        """植入⑤：中途改 holder → blame 精确到章与提案 operation_id。"""
        book = self._ensure()
        evs = changelog.blame(book, "entities", "entries[it_ds].holder")
        self.assertTrue(evs, "断水剑 holder 变更必须有 changelog 记录")
        holder_evs = [e for e in evs if str(e.get("path", "")).endswith(".holder")]
        self.assertTrue(holder_evs)
        e = holder_evs[0]
        self.assertEqual(e.get("ch"), "ch_150")
        self.assertEqual(e.get("op_id"), "ch_150.reader.r")
        self.assertEqual(e.get("after"), "赵莽")

    # ---- §8.3 性能 ----

    def test_performance_check_under_10s(self):
        """200 章样书 check 全程 < 10s。"""
        book = self._ensure()
        t0 = time.time()
        r = run_cli(book, "check", "--json")
        dt = time.time() - t0
        self.assertEqual(r.returncode, 0, r.stdout[-300:])
        self.assertLess(dt, 10.0, f"check 全程 {dt:.1f}s 超预算")

    def test_performance_memory_layer_under_2s(self):
        """读者记忆层（line_memory_map 全线扫描）< 2s。"""
        book = self._ensure()
        t0 = time.time()
        rows = memory.line_memory_map(book)
        dt = time.time() - t0
        self.assertEqual(len(rows), 14)  # 7 常规开放 + 5 冷却 + 2 零落笔
        self.assertLess(dt, 2.0, f"memory 层 {dt:.1f}s 超预算")

    def test_performance_state_at_under_3s(self):
        """ch_100 世界切面重放 < 3s。"""
        book = self._ensure()
        t0 = time.time()
        folded, err = changelog.state_at(book, 100)
        dt = time.time() - t0
        self.assertIsNone(err, err)
        self.assertLess(dt, 3.0, f"state at 重放 {dt:.1f}s 超预算")
        self.assertEqual(len(folded["entities"]["entries"]), 8)

    # ---- D1 上下文经济学验收（R4 验收门） ----

    def test_rollup_matches_vol_end_state_at(self):
        """rollup 内容与 state at 卷末切面一致性抽查（实体数/开放线数对齐）。"""
        book = self._ensure()
        ru = json.loads((book / "state" / "rollups" / "vol_01.json").read_text(encoding="utf-8"))
        folded, err = changelog.state_at(book, 50)
        self.assertIsNone(err, err)
        self.assertEqual(len(ru["entities"]),
                         len(folded["entities"]["entries"]),
                         "rollup 实体数应等于 vol_01 卷末切面")
        open_at_50 = sum(1 for f in folded["lines"]["foreshadows"]
                         if f.get("status") != "Resolved")
        self.assertEqual(len(ru["open_lines"]), open_at_50,
                         "rollup 未兑线数应等于 vol_01 卷末切面")

    def test_pack_context_economy(self):
        """vol_04 任意章 pack token 与 vol_01 章节相当（±20%）：装配成本 O(当前卷)。"""
        book = self._ensure()
        # 章位对称采样：两章均为「闲置线催还已升级」的稳态章位（hard_reminders 同构），
        # 隔离掉章位性差异后，剩下的增量应当只有前情卷末态势块
        p1 = pack.build_pack(book, "ch_040")
        p4 = pack.build_pack(book, "ch_190")
        # vol_04 必须注入前情卷末态势，vol_01 没有
        self.assertNotIn("prior_volumes", p1["p0"])
        self.assertIn("prior_volumes", p4["p0"])
        t1 = common.est_tokens(pack.render_pack(p1))
        t4 = common.est_tokens(pack.render_pack(p4))
        self.assertLessEqual(abs(t4 - t1), 0.2 * t1,
                             f"vol_04 pack {t4} token vs vol_01 {t1} token，超出 ±20%")
        # 前情块本身受预算硬约束
        digest = "\n".join(p4["p0"]["prior_volumes"])
        from engine import rollup as ru_mod
        self.assertLessEqual(common.est_tokens(digest), ru_mod.PRIOR_VOLUMES_TOKEN_CAP)


if __name__ == "__main__":
    unittest.main()
