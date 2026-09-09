"""位阶单调性探针（checks._tier_probe / C1）单测 — 2025 一致性改造 R2-c7。

战力通胀/通缩是长篇吃书第一重灾区：tier_rank/tier_name 的实际变更
必须有剧情事件支撑。processed/ 重放口径（对无 changelog 老书可用）。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import checks, errcodes, state  # noqa: E402
from tests._fixtures import TempBook  # noqa: E402


def _seed_processed(tb, entities_by_ch: dict[str, list[dict]]) -> None:
    """把各章提案直接放入 processed/（模拟 sync 归档后的形态）。"""
    for ch, ents in entities_by_ch.items():
        tb.write(f"state/inbox/processed/{ch}.json", json.dumps({
            "schema": "novel-studio.state-mutation/v2", "chapter": ch,
            "operation_id": f"{ch}.reader.t", "entities": ents}, ensure_ascii=False))


def _warns(book) -> list[str]:
    out: list[str] = []
    checks._tier_probe(book, out)
    return out


class TestTierProbe(unittest.TestCase):

    def test_shift_without_event_warns(self):
        with TempBook() as tb:
            _seed_processed(tb, {
                "ch_001": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "type": "person", "tier_rank": 3, "tier_name": "炼气三层"}],
                "ch_005": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "tier_rank": 6, "tier_name": "金丹境"}],
            })
            warns = _warns(tb.book)
            self.assertEqual(len(warns), 1)
            self.assertEqual(warns[0]["code"], "tier_shift_without_event")
            self.assertIn("张彪", warns[0]["msg"])
            self.assertIn("ch_005", warns[0]["msg"])

    def test_shift_with_event_passes(self):
        with TempBook() as tb:
            _seed_processed(tb, {
                "ch_001": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "type": "person", "tier_rank": 3, "tier_name": "炼气三层"}],
                "ch_005": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "tier_rank": 6, "tier_name": "金丹境"}],
            })
            tb.set_state("timeline", {"events": [
                {"time": "第三日", "event": "张彪在洞府中突破至金丹境", "chapter": "ch_005"},
            ], "arcs": []})
            self.assertEqual(_warns(tb.book), [])

    def test_event_by_alias_or_tier_name_alone_does_not_excuse(self):
        # 事件不含实体名 → 不能洗白（防任意突破事件洗白任意实体）
        with TempBook() as tb:
            _seed_processed(tb, {
                "ch_001": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "type": "person", "tier_rank": 3}],
                "ch_005": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "tier_rank": 6}],
            })
            tb.set_state("timeline", {"events": [
                {"time": "第三日", "event": "宗门大比上有人突破至金丹境", "chapter": "ch_005"},
            ], "arcs": []})
            self.assertEqual(len(_warns(tb.book)), 1)

    def test_grace_window_and_config(self):
        with TempBook() as tb:
            _seed_processed(tb, {
                "ch_001": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "type": "person", "tier_rank": 3}],
                "ch_005": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "tier_rank": 6}],
            })
            # 事件在 ch_006（grace=1 窗口内）→ 通过
            tb.set_state("timeline", {"events": [
                {"time": "第四日", "event": "张彪突破", "chapter": "ch_006"},
            ], "arcs": []})
            self.assertEqual(_warns(tb.book), [])
            # 收紧 grace=0 → 窗口外 → 报
            proj = json.loads(tb.read("project.json"))
            proj["tier_shift_grace"] = 0
            tb.write("project.json", json.dumps(proj, ensure_ascii=False))
            self.assertEqual(len(_warns(tb.book)), 1)

    def test_first_sighting_is_baseline(self):
        # 首次出现只建基线（Stage 0 播种语义），不变更不要求事件
        with TempBook() as tb:
            _seed_processed(tb, {
                "ch_001": [{"action": "upsert", "id": "p_001", "name": "林牧",
                            "type": "person", "tier_rank": 9, "tier_name": "化神境"}],
            })
            self.assertEqual(_warns(tb.book), [])

    def test_restatement_is_not_shift(self):
        # 同值重述（Reader 刷新 summary 顺带重写 tier）不算变更
        with TempBook() as tb:
            _seed_processed(tb, {
                "ch_001": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "type": "person", "tier_rank": 3, "tier_name": "炼气三层"}],
                "ch_002": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "tier_rank": 3, "tier_name": "炼气三层",
                            "summary": "刷新近况"}],
            })
            self.assertEqual(_warns(tb.book), [])

    def test_tier_name_only_shift_also_probed(self):
        # 只改 tier_name 不改 rank 同样要事件
        with TempBook() as tb:
            _seed_processed(tb, {
                "ch_001": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "type": "person", "tier_rank": 3, "tier_name": "炼气三层"}],
                "ch_004": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "tier_name": "炼气九层"}],
            })
            self.assertEqual(len(_warns(tb.book)), 1)

    def test_run_checks_integration_and_registry(self):
        with TempBook() as tb:
            _seed_processed(tb, {
                "ch_001": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "type": "person", "tier_rank": 3}],
                "ch_005": [{"action": "upsert", "id": "p_002", "name": "张彪",
                            "tier_rank": 6}],
            })
            report = checks.run_checks(tb.book)
            codes = {w.get("code") for w in report.get("narrative_health", {}).get("warnings", [])}
            self.assertIn("tier_shift_without_event", codes)
            # 注册表完备性：warning 级、入叙事核
            self.assertEqual(errcodes.REGISTRY["tier_shift_without_event"].level, "warning")
            self.assertNotIn("tier_shift_without_event", checks.SYSTEM_CHECK_CODES)

    def test_param_validation(self):
        self.assertIsNone(checks.validate_param_value("tier_shift_grace", 0))
        self.assertIsNone(checks.validate_param_value("tier_shift_grace", 2))
        self.assertIsNotNone(checks.validate_param_value("tier_shift_grace", -1))
        self.assertIsNotNone(checks.validate_param_value("tier_shift_grace", "1"))
        self.assertIsNotNone(checks.validate_param_value("tier_shift_grace", True))


if __name__ == "__main__":
    unittest.main()
