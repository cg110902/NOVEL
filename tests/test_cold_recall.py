"""A5 冷线回收锚定（pack 注入 + beats new 提醒）与 A4b locked 盲区提示单测 — R5-c14。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import checks, pack  # noqa: E402
from tests._fixtures import TempBook  # noqa: E402

_AUDIT = "---\nhard: 0\nadjudicated: false\n---\n\n# 仲裁\n"


def _fast_memory(tb):
    """压低读者记忆阈值：weight=1 的线 4 章不提即冷（测试提速用）。"""
    proj = json.loads(tb.path("project.json").read_text(encoding="utf-8"))
    proj["reader_memory"] = {"working_window": 2, "fuzzy_window": 3,
                             "cold_line_base": 4, "cold_line_per_weight": 1}
    tb.path("project.json").write_text(json.dumps(proj, ensure_ascii=False, indent=2),
                                       encoding="utf-8")


def _seed(tb, text_extra=""):
    tb.set_state("persons", {"entries": [
        {"id": "p_001", "name": "林牧", "type": "person", "status": "active"},
        {"id": "p_002", "name": "赵莽", "type": "person", "status": "active"}]})
    tb.seed_chapter("ch_001", "林牧与赵莽进了城。" + text_extra)
    tb.write("log/audit/ch_001.md", _AUDIT)
    tb.write("state/inbox/ch_001.json", json.dumps({
        "schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
        "operation_id": "ch_001.reader.r",
        "synopsis": {"text": "开局。"},
        "lines": [{"kind": "foreshadow", "action": "plant", "id": "GUN-001",
                   "name": "断水剑的来历", "target_ch": 30, "weight": 1}]},
        ensure_ascii=False))
    assert tb.run_json("sync", "ch_001").get("snapshot", {}).get("ok")


def _plain_ch(tb, n: int):
    ch = f"ch_{n:03d}"
    tb.seed_chapter(ch, f"第{n}章，林牧照常练剑。")
    tb.write(f"log/audit/{ch}.md", _AUDIT)
    tb.write(f"state/inbox/{ch}.json", json.dumps({
        "schema": "novel-studio.state-mutation/v2", "chapter": ch,
        "operation_id": f"{ch}.reader.r",
        "synopsis": {"text": "日常。"}}, ensure_ascii=False))
    assert tb.run_json("sync", ch).get("snapshot", {}).get("ok")


class TestColdRecallHints(unittest.TestCase):
    """A5：pack 只注入「beats 计划回收 × 已冷」的可执行子集（≤2 条）。"""

    def test_pack_injects_cold_recall_hint(self):
        with TempBook() as tb:
            _fast_memory(tb)
            _seed(tb, "席间有人说起断水剑的来历。")  # last_seen = ch_001
            for n in range(2, 7):
                _plain_ch(tb, n)                      # ch_006 时 gap=5 > 4 → 冷
            tb.write("outlines/vol_01/beats/ch_007.md",
                     "---\nchapter: ch_007\nvol: vol_01\nform: 爆发\n---\n\n"
                     "## 目标\n\n- 测试\n\n## 线动作\n\n- resolve GUN-001\n")
            payload = pack.build_pack(tb.book, "ch_007")
            hints = payload["p0"].get("cold_recall_hints") or []
            self.assertEqual(len(hints), 1)
            self.assertIn("GUN-001", hints[0])
            self.assertIn("ch_001", hints[0])  # 上次出现章
            self.assertIn("先半句锚定", hints[0])
            text = pack.render_pack(payload)
            self.assertIn("冷线回收锚定", text)

    def test_warm_resolved_line_not_injected(self):
        with TempBook() as tb:
            _fast_memory(tb)
            _seed(tb, "席间有人说起断水剑的来历。")
            _plain_ch(tb, 2)
            tb.seed_chapter("ch_003", "林牧又查起断水剑的来历。")  # last_seen=3, gap=0 → 热
            tb.write("log/audit/ch_003.md", _AUDIT)
            tb.write("state/inbox/ch_003.json", json.dumps({
                "schema": "novel-studio.state-mutation/v2", "chapter": "ch_003",
                "operation_id": "ch_003.reader.r",
                "synopsis": {"text": "查证。"}}, ensure_ascii=False))
            assert tb.run_json("sync", "ch_003").get("snapshot", {}).get("ok")
            tb.write("outlines/vol_01/beats/ch_004.md",
                     "---\nchapter: ch_004\nvol: vol_01\nform: 爆发\n---\n\n"
                     "## 线动作\n\n- resolve GUN-001\n")
            payload = pack.build_pack(tb.book, "ch_004")
            self.assertNotIn("cold_recall_hints", payload["p0"])

    def test_hint_cap_two(self):
        with TempBook() as tb:
            _fast_memory(tb)
            _seed(tb, "席间说起断水剑的来历、古矿的封条、沉船的货物。")
            for n in range(2, 7):
                _plain_ch(tb, n)
            tb.write("state/inbox/ch_006.json", json.dumps({
                "schema": "novel-studio.state-mutation/v2", "chapter": "ch_006",
                "operation_id": "ch_006.reader.r2",
                "synopsis": {"text": "多线。"},
                "lines": [{"kind": "foreshadow", "action": "plant", "id": "GUN-002",
                           "name": "古矿的封条", "target_ch": 30, "weight": 1},
                          {"kind": "foreshadow", "action": "plant", "id": "GUN-003",
                           "name": "沉船的货物", "target_ch": 30, "weight": 1}]},
                ensure_ascii=False))
            # 重新播种正文（三章线在 ch_001 已提及，last_seen=1 → ch_007 gap=6 冷）
            tb.seed_chapter("ch_006", "第六章过渡。")
            tb.write("log/audit/ch_006.md", _AUDIT)
            assert tb.run_json("sync", "ch_006").get("snapshot", {}).get("ok")
            tb.write("outlines/vol_01/beats/ch_007.md",
                     "---\nchapter: ch_007\nvol: vol_01\nform: 爆发\n---\n\n"
                     "## 线动作\n\n- resolve GUN-001\n- resolve GUN-002\n- resolve GUN-003\n")
            payload = pack.build_pack(tb.book, "ch_007")
            hints = payload["p0"].get("cold_recall_hints") or []
            self.assertEqual(len(hints), 2, "可执行子集上限 2 条")

    def test_beats_new_mentions_cold_due_line(self):
        with TempBook() as tb:
            _fast_memory(tb)
            _seed(tb, "席间有人说起断水剑的来历。")
            for n in range(2, 7):
                _plain_ch(tb, n)
            # GUN-001 target 30 太远；改 target 到近窗（ch_007+5 内）使其进 beats 提醒
            lines = tb.state("lines")
            for g in lines["foreshadows"]:
                if g["id"] == "GUN-001":
                    g["target_ch"] = 9
            tb.set_state("lines", lines)
            out = tb.run("beats", "new", "ch_007", "--write")
            self.assertEqual(out.returncode, 0, out.stderr)
            beats = tb.path("outlines/vol_01/beats/ch_007.md").read_text(encoding="utf-8")
            self.assertIn("冷线提醒", beats)
            self.assertIn("GUN-001", beats)


class TestLockedFactTraceable(unittest.TestCase):
    """A4b：locked plant 的 fact 不含已登记实体名 → 写入时刻 info 提示（不阻断）。"""

    def test_untraceable_fact_flagged(self):
        with TempBook() as tb:
            _seed(tb)
            proposal = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
                        "operation_id": "ch_001.reader.r",
                        "synopsis": {"text": "开局。"},
                        "locked": [{"action": "plant", "id": "LOCK-001",
                                    "fact": "那人当年死于剑下", "note": "旧案"}]}
            battery = checks.verify_candidates(tb.book, "ch_001", proposal)
            codes = [it["code"] for it in battery.get("items", [])]
            self.assertIn("locked_fact_untraceable", codes)
            sev = next(it["sev"] for it in battery["items"]
                       if it["code"] == "locked_fact_untraceable")
            self.assertEqual(sev, "info")

    def test_fact_with_entity_name_not_flagged(self):
        with TempBook() as tb:
            _seed(tb)
            proposal = {"schema": "novel-studio.state-mutation/v2", "chapter": "ch_001",
                        "operation_id": "ch_001.reader.r",
                        "synopsis": {"text": "开局。"},
                        "locked": [{"action": "plant", "id": "LOCK-001",
                                    "fact": "林牧之父死于剑下", "note": "旧案"}]}
            battery = checks.verify_candidates(tb.book, "ch_001", proposal)
            codes = [it["code"] for it in battery.get("items", [])]
            self.assertNotIn("locked_fact_untraceable", codes)


if __name__ == "__main__":
    unittest.main()
