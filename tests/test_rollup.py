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


class TestWorldAnchorBudget(unittest.TestCase):
    """world_anchors 预算帽（pack 上下文经济学）。

    实测依据：bible 合计 14.8k tok 时，world_anchors 曾高达 13 330 tok，
    占 pack 总预算（18 000）的 74%，且**逐章完全相同**——既重复烧 token，
    又用恒定内容稀释注意力。而 pack 超预算硬裁只裁 P2（P0/P1 保留），
    bible 再厚一点就会单枪匹马撑破预算且无法裁剪。
    """

    _FAT = "### 境界细分补充\n" + "五行灵根各有偏重，修炼速度差异显著。" * 60 + "\n"

    def _thicken_bible(self, tb):
        for f in sorted((tb.book / "bible").glob("0[1-5]*.md")):
            f.write_text(f.read_text(encoding="utf-8") + "\n\n" + self._FAT * 3,
                         encoding="utf-8")

    def test_thick_bible_is_capped(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进大殿。")
            self._thicken_bible(tb)
            p = pack.build_pack(tb.book, "ch_001")
            wa = p["budget_report"]["world_anchor_tokens"]
            self.assertLessEqual(wa, pack.MAX_WORLD_ANCHOR_TOKENS,
                                 f"世界锚点未受预算约束: {wa} tok")
            # 截断必须给出「去哪取完整内容」的出口，不能静默丢失
            self.assertIn("按需取", p["p0"].get("world_anchors", ""),
                          "截断后未提示按需取完整世界公理")

    def test_budget_report_exposes_world_anchor(self):
        """可观测：此开销曾长期混在 p0 总数里，完全不可见。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进大殿。")
            r = pack.build_pack(tb.book, "ch_001")["budget_report"]
            self.assertIn("world_anchor_tokens", r)
            self.assertIsInstance(r["world_anchor_tokens"], int)

    def test_project_json_overrides_budget(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进大殿。")
            self._thicken_bible(tb)
            proj = tb.read("project.json")
            import json as _j
            d = _j.loads(proj)
            for want in (0, 5000):
                d["world_anchor_tokens"] = want
                tb.write("project.json", _j.dumps(d, ensure_ascii=False))
                wa = pack.build_pack(tb.book, "ch_001")["budget_report"]["world_anchor_tokens"]
                if want == 0:
                    self.assertEqual(wa, 0, "设为 0 应完全不注入世界锚点")
                else:
                    self.assertGreater(wa, pack.MAX_WORLD_ANCHOR_TOKENS,
                                       "自定义预算应覆盖默认值")

    def test_truncation_is_deterministic(self):
        """截断不得引入非确定性（同输入必须逐字节一致）。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进大殿。")
            self._thicken_bible(tb)
            a = pack.render_pack(pack.build_pack(tb.book, "ch_001"))
            b = pack.render_pack(pack.build_pack(tb.book, "ch_001"))
            self.assertEqual(a, b)

    def test_thin_bible_not_truncated(self):
        """薄 bible 不该被误截断（否则提示噪声会污染每章上下文）。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进大殿。")
            p = pack.build_pack(tb.book, "ch_001")
            wa = p["budget_report"]["world_anchor_tokens"]
            self.assertNotIn("按需取", p["p0"].get("world_anchors", ""),
                             f"薄 bible（{wa} tok）被误截断，阈值偏低")


class TestRollup(unittest.TestCase):

    def _rich_book(self, tb):
        tb.set_state("persons", {"entries": [
            {"id": "p_001", "name": "林牧", "type": "person", "status": "active",
             "tier_rank": 5, "tier_name": "辟海境"},
            {"id": "p_002", "name": "赵莽", "type": "person", "status": "active",
             "life_status": "deceased"},
        ]})
        tb.set_state("items", {"entries": [
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

    def test_digest_floor_keeps_head_line(self):
        """极端场景：单卷头行本身超预算 —— 保底保留头行（空摘要比超预算更有害）。"""
        with TempBook() as tb:
            self._rich_book(tb)
            cur = tb.state("current")
            cur["situation"] = "超长态势" * 400  # 单行 ~800 token，必超 500
            tb.set_state("current", cur)
            for v in ("vol_01", "vol_02"):
                tb.run_json("state", "rollup", v)
            lines = rollup.prior_volumes_digest(tb.book, "vol_03")
            self.assertTrue(lines, "即使超预算也必须保留态势头行，不得裁成空")
            self.assertIn("卷末态势", lines[0])

    def test_pack_no_rollup_no_block(self):
        with TempBook() as tb:
            self._rich_book(tb)
            tb.write("outlines/vol_02/beats/ch_055.md",
                     "---\nchapter: ch_055\nvol: vol_02\nform: 危机逼近\n---\n\n## 目标\n- 测试\n")
            payload = pack.build_pack(tb.book, "ch_055")
            self.assertNotIn("prior_volumes", payload["p0"])

    def test_digest_cap_trims_from_tail(self):
        with TempBook() as tb:
            self._rich_book(tb)
            tb.set_state("persons", {"entries": [
                {"id": f"p_{i:03d}", "name": f"角色{i}", "type": "person",
                 "status": "active", "tier_rank": (i % 12) + 1,
                 "tier_name": f"第{(i % 12) + 1}阶位阶名"} for i in range(1, 61)]})
            # 三卷 rollup：单卷摘要 ≤500，多卷合并必须触发尾部裁剪
            for v in ("vol_01", "vol_02", "vol_03"):
                tb.run_json("state", "rollup", v)
            lines = rollup.prior_volumes_digest(tb.book, "vol_04")
            self.assertTrue(lines, "裁剪保底：至少保留态势头行，不得裁成空")
            self.assertLessEqual(common.est_tokens("\n".join(lines)),
                                 rollup.PRIOR_VOLUMES_TOKEN_CAP,
                                 "超预算必须从尾部裁剪")
            self.assertIn("卷末态势", lines[0], "保底保留的是优先级最高的头行")


if __name__ == "__main__":
    unittest.main()
