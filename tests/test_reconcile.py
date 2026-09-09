"""卷末对账大修（engine/commands/reconcile.py）单测 — 2025 一致性改造 R4-c12。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.commands import reconcile as rc  # noqa: E402
from tests._fixtures import TempBook  # noqa: E402

_AUDIT_OK = "---\nhard: 0\nadjudicated: false\n---\n\n# 仲裁\n"


class TestReconcile(unittest.TestCase):

    def _book_with_projections(self, tb):
        """一章定稿：含未登记专名「宋青书」×3、登记实体「林牧」出现、
        「赵莽」登记但正文零出现。"""
        tb.seed_chapter("ch_001",
                        "林牧走进城隍庙。宋青书拦住去路，宋青书冷笑，宋青书拔刀。" * 8)
        tb.write("log/audit/ch_001.md", _AUDIT_OK)
        tb.write("state/inbox/ch_001.json", json.dumps({
            "schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
            "operation_id": "ch_001.reader.r",
            "synopsis": {"text": "主角进城隍庙。"},
            "entities": [{"action": "upsert", "id": "p_001", "name": "林牧",
                          "type": "person", "summary": "主角"},
                         {"action": "upsert", "id": "p_002", "name": "赵莽",
                          "type": "person", "summary": "零出现实体"}]}, ensure_ascii=False))
        out = tb.run_json("sync", "ch_001")
        self.assertTrue(out.get("snapshot", {}).get("ok"), out)

    def test_projection_diff_sections(self):
        with TempBook() as tb:
            self._book_with_projections(tb)
            payload = rc._gather(tb.book, "vol_01")
            self.assertEqual(payload["vol"], "vol_01")
            self.assertEqual(payload["verify_error_count"], 0)
            # 4a：未登记专名宋青书被点名（≥2 次）
            names = {u["name"] for u in payload["unregistered"]}
            self.assertIn("宋青书", names)
            self.assertNotIn("林牧", names)  # 主角已注册
            # 4b：赵莽（active、零出现）被点名；林牧不在
            absent = {a["name"] for a in payload["absent_entities"]}
            self.assertIn("赵莽", absent)
            self.assertNotIn("林牧", absent)

    def test_write_refuses_overwrite(self):
        with TempBook() as tb:
            self._book_with_projections(tb)
            out = tb.run("reconcile", "vol_01", "--write")
            self.assertEqual(out.returncode, 0, out.stderr)
            p = tb.path("log/review/reconcile_vol_01.md")
            self.assertTrue(p.is_file())
            text = p.read_text(encoding="utf-8")
            for section in ("一、全书不变量复扫", "二、本卷机械探针复扫",
                            "三、本卷高危字段变更史", "四、投影 diff 工位",
                            "五、LLM 对账仪式"):
                self.assertIn(section, text)
            self.assertIn("宋青书", text)
            self.assertIn("赵莽", text)
            # 工作单不覆盖
            again = tb.run("reconcile", "vol_01", "--write")
            self.assertEqual(again.returncode, 1)

    def test_high_risk_blame_from_changelog(self):
        with TempBook() as tb:
            self._book_with_projections(tb)
            # 章间手术刀改高危字段（ch_001 封存后、ch_002 封存前 → 落在 vol_01 窗口）
            tb.run_json("state", "set", "entities.赵莽.tier_rank", "7")
            tb.seed_chapter("ch_002", "林牧与赵莽在城隍庙后院对峙。" * 40)
            tb.write("log/audit/ch_002.md", _AUDIT_OK)
            tb.write("state/inbox/ch_002.json", json.dumps({
                "schema": "novel-studio.state-mutation/v2", "chapter": "ch_002",
                "operation_id": "ch_002.reader.r",
                "synopsis": {"text": "对峙。"}}, ensure_ascii=False))
            self.assertTrue(tb.run_json("sync", "ch_002").get("snapshot", {}).get("ok"))
            payload = rc._gather(tb.book, "vol_01")
            self.assertGreaterEqual(payload["high_risk_count"], 1)
            paths = {h["path"] for h in payload["high_risk"]}
            self.assertTrue(any("tier_rank" in p for p in paths), paths)

    def test_invalid_vol_usage_error(self):
        with TempBook() as tb:
            self._book_with_projections(tb)
            out = tb.run("reconcile", "vol_99")
            self.assertEqual(out.returncode, 2)
            js = tb.run_json("reconcile", "vol_99")
            self.assertFalse(js.get("ok", True))

    def test_json_payload_pure(self):
        with TempBook() as tb:
            self._book_with_projections(tb)
            payload = tb.run_json("reconcile", "vol_01")
            self.assertIn("audit_hits", payload)
            self.assertIn("chapters", payload)


if __name__ == "__main__":
    unittest.main()
