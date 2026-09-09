"""卷级 rollup（engine/rollup.py + pack 注入）单测 — 2025 一致性改造 R4-c11。

上下文经济学：远卷只注入态势摘要（≤500 token），装配成本 O(当前卷)。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import common, pack, rollup, state  # noqa: E402
from tests._fixtures import TempBook  # noqa: E402


class TestRollup(unittest.TestCase):

    def _rich_book(self, tb):
        tb.set_state("entities", {"entries": [
            {"id": "p_001", "name": "林牧", "type": "person", "status": "active",
             "tier_rank": 5, "tier_name": "辟海境"},
            {"id": "p_002", "name": "赵莽", "type": "person", "status": "active",
             "life_status": "deceased"},
            {"id": "it_001", "name": "断水剑", "type": "item", "status": "active",
             "holder": "林牧", "charges": 3, "max_charges": 9},
        ]})
        tb.set_state("lines", {
            "foreshadows": [
                {"id": "GUN-001", "name": "玄铁令", "plant_ch": 1, "status": "Planted",
                 "target_ch": 60, "weight": 3},
                {"id": "GUN-002", "name": "旧账", "plant_ch": 2, "status": "Resolved"},
            ],
            "misunderstandings": [], "knowledge": []})
        led = tb.state("ledger")
        led["pools"]["spirit_stone"] = {"name": "灵石", "unit": "块", "initial": 10, "current": 1200}
        tb.set_state("ledger", led)
        tb.set_state("timeline", {
            "events": [], "arcs": [],
            "clocks": [{"name": "灯债滚利", "target_ch": 58, "status": "Active",
                        "urgency": "high", "desc": "逾期烧铺"}],
            "milestones": [{"id": "MS-001", "title": "夺回断水剑", "target_ch": 80,
                            "status": "pending"},
                           {"id": "MS-002", "title": "初入宗门", "target_ch": 10,
                            "status": "achieved"}]})

    def test_build_rollup_content(self):
        with TempBook() as tb:
            self._rich_book(tb)
            data = rollup.build_rollup(tb.book, "vol_01")
            self.assertEqual(data["schema"], "novel-studio.rollup/v1")
            names = {e["name"] for e in data["entities"]}
            self.assertEqual(names, {"林牧", "赵莽", "断水剑"})
            # 断水剑带 charges；赵莽 life_status 非 alive
            it = next(e for e in data["entities"] if e["name"] == "断水剑")
            self.assertEqual(it["charges"], 3)
            # 未兑线只留未闭环
            self.assertEqual([l["id"] for l in data["open_lines"]], ["GUN-001"])
            self.assertEqual(data["ledger"]["spirit_stone"]["current"], 1200)
            self.assertEqual([m["id"] for m in data["milestones_pending"]], ["MS-001"])
            self.assertEqual([c["name"] for c in data["clocks_active"]], ["灯债滚利"])
            # 泄漏面控制：不携带 summary/dossier 等重字段
            for e in data["entities"]:
                self.assertNotIn("summary", e)
                self.assertNotIn("dossier", e)

    def test_cli_save_and_invalid_vol(self):
        with TempBook() as tb:
            out = tb.run_json("state", "rollup", "vol_01")
            self.assertTrue(out.get("ok"), out)
            self.assertTrue(tb.path("state/rollups/vol_01.json").is_file())
            bad = tb.run_json("state", "rollup", "not_a_vol")
            self.assertFalse(bad.get("ok", True))

    def test_pack_injects_prior_volumes(self):
        with TempBook() as tb:
            self._rich_book(tb)
            tb.run_json("state", "rollup", "vol_01")
            # ch_055 的 beats 放 vol_02 → cur_vol 推断为 vol_02
            tb.write("outlines/vol_02/beats/ch_055.md",
                     "---\nchapter: ch_055\nvol: vol_02\nform: 危机逼近\n---\n\n## 目标\n- 测试\n")
            payload = pack.build_pack(tb.book, "ch_055")
            self.assertIn("prior_volumes", payload["p0"])
            text = pack.render_pack(payload)
            self.assertIn("前情卷末态势", text)
            self.assertIn("林牧", text)
            self.assertIn("GUN-001", text)
            # token 预算受控
            digest = "\n".join(payload["p0"]["prior_volumes"])
            self.assertLessEqual(common.est_tokens(digest),
                                 rollup.PRIOR_VOLUMES_TOKEN_CAP)

    def test_pack_no_rollup_no_block(self):
        with TempBook() as tb:
            self._rich_book(tb)
            tb.write("outlines/vol_02/beats/ch_055.md",
                     "---\nchapter: ch_055\nvol: vol_02\nform: 危机逼近\n---\n\n## 目标\n- 测试\n")
            payload = pack.build_pack(tb.book, "ch_055")
            self.assertNotIn("prior_volumes", payload["p0"])

    def test_digest_cap_trims_from_tail(self):
        with TempBook() as tb:
            tb.set_state("entities", {"entries": [
                {"id": f"p_{i:03d}", "name": f"角色{i}", "type": "person",
                 "status": "active", "tier_rank": (i % 12) + 1,
                 "tier_name": f"第{(i % 12) + 1}阶位阶名"} for i in range(1, 61)]})
            tb.run_json("state", "rollup", "vol_01")
            lines = rollup.prior_volumes_digest(tb.book, "vol_02")
            self.assertTrue(lines)
            self.assertLessEqual(common.est_tokens("\n".join(lines)),
                                 rollup.PRIOR_VOLUMES_TOKEN_CAP,
                                 "超预算必须从尾部裁剪")


if __name__ == "__main__":
    unittest.main()
