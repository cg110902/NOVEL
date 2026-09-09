"""对白声纹漂移检测（engine/voiceprint.py + check 集成）单测 — R5-c15（C2）。

只测「怎么说话」（句长/语气词/口头禅），不测人设对错；样本不足不判定。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import checks, voiceprint  # noqa: E402
from tests._fixtures import TempBook  # noqa: E402

# 基线风格：长句 + 口头禅「有意思」 + 语气词「吧」
_BASE_PARA = "林牧沉声道：「这笔买卖真是有意思吧，值得再赌上一把才对。」赵莽答道：「行，那就依你。」"
# 漂移风格：短句、无口头禅、无语气词（赵莽保持稳定句，作对照组）
_DRIFT_PARA = "林牧说：「知道了。」赵莽答道：「行，那就依你。」"
# 稳定风格（赵莽全程一致）
_STEADY_PARA = "赵莽答道：「行，那就依你。」"


def _book_with_dialogues(tb, base_chs, drift_chs):
    tb.set_state("entities", {"entries": [
        {"id": "p_001", "name": "林牧", "type": "person", "status": "active"},
        {"id": "p_002", "name": "赵莽", "type": "person", "status": "active"}]})
    for i, n in enumerate(range(1, base_chs + 1), start=1):
        tb.seed_chapter(f"ch_{n:03d}", _BASE_PARA * (3 if i % 2 else 2))
    for n in range(base_chs + 1, base_chs + drift_chs + 1):
        tb.seed_chapter(f"ch_{n:03d}", _DRIFT_PARA * 3)


class TestVoiceprint(unittest.TestCase):

    def test_drift_detected_with_reasons(self):
        with TempBook() as tb:
            # 窗口语义：近窗=近 6 章——漂移须整窗持续才报（偶一章短句属正常波动）
            _book_with_dialogues(tb, base_chs=8, drift_chs=6)
            rep = voiceprint.voiceprint_report(tb.book)
            chars = {c["name"]: c for c in rep["characters"]}
            self.assertIn("林牧", chars)
            lm = chars["林牧"]
            self.assertGreaterEqual(lm["baseline_lines"], voiceprint.DEFAULTS["min_lines"])
            self.assertTrue(lm["drift_reasons"], "林牧声纹漂移必须被检出")
            joined = "；".join(lm["drift_reasons"])
            self.assertTrue(("句长" in joined) or ("语气词" in joined) or ("口头禅" in joined))

    def test_steady_character_not_flagged(self):
        with TempBook() as tb:
            _book_with_dialogues(tb, base_chs=8, drift_chs=6)
            rep = voiceprint.voiceprint_report(tb.book)
            chars = {c["name"]: c for c in rep["characters"]}
            # 赵莽基线与近窗同款稳定对白 → 必须在判定池且零漂移
            self.assertIn("赵莽", chars)
            self.assertEqual(chars["赵莽"]["drift_reasons"], [])

    def test_insufficient_baseline_skipped(self):
        with TempBook() as tb:
            # 只给 2 章基线对白（~5 条 < min_lines=12）→ 不判定
            _book_with_dialogues(tb, base_chs=2, drift_chs=1)
            rep = voiceprint.voiceprint_report(tb.book)
            names = {c["name"] for c in rep["characters"]}
            self.assertNotIn("林牧", names)

    def test_mention_without_speech_not_attributed(self):
        """段内提及实体但非其说话（无说话动词紧邻）→ 对白不得被错归属。"""
        with TempBook() as tb:
            tb.set_state("entities", {"entries": [
                {"id": "p_001", "name": "林牧", "type": "person", "status": "active"},
                {"id": "p_002", "name": "赵莽", "type": "person", "status": "active"}]})
            # 两个注册实体都在场但都不说话（无动词紧邻）+ 说话人未注册：
            # 归属启发式必须双路失败（前缀无动词 / 回退非唯一实体）→ 丢弃
            tb.seed_chapter("ch_001",
                            "林牧不作声，赵莽也低头。掌柜的赔笑道：「客官说笑了。」" * 3)
            ds = voiceprint.extract_dialogues(tb.book)
            texts = [q for _, _, q in ds]
            self.assertFalse(any("客官说笑了" in t for t in texts),
                             "提及≠说话：该对白说话人未注册且无归属线索，必须丢弃")

    def test_unattributed_dialogue_dropped(self):
        with TempBook() as tb:
            tb.set_state("entities", {"entries": [
                {"id": "p_001", "name": "林牧", "type": "person", "status": "active"}]})
            # 无归属对白（段内无实体名+说话动词，也无唯一实体提及）→ 全部丢弃
            tb.seed_chapter("ch_001", "「这买卖真是有意思吧。」" * 4)
            ds = voiceprint.extract_dialogues(tb.book)
            self.assertEqual(ds, [])

    def test_check_emits_info_level(self):
        with TempBook() as tb:
            _book_with_dialogues(tb, base_chs=8, drift_chs=6)
            out = tb.run_json("check")
            codes = [i["code"] for i in out.get("infos", [])]
            self.assertIn("voiceprint_drift", codes)
            # info 级：不进 errors/warnings 通道（level=实际投递通道纪律）
            self.assertNotIn("voiceprint_drift", [w["code"] for w in out.get("warnings", [])])
            self.assertNotIn("voiceprint_drift", [e["code"] for e in out.get("errors", [])])

    def test_param_override_takes_effect(self):
        with TempBook() as tb:
            # 默认 min_lines=12：基线 ~5 条的林牧不进判定池
            _book_with_dialogues(tb, base_chs=2, drift_chs=6)
            self.assertNotIn("林牧", {c["name"] for c in
                                      voiceprint.voiceprint_report(tb.book)["characters"]})
            # 覆盖 min_lines=3 → 进入判定池（阈值经 project.json 真实生效）
            import json
            proj = json.loads(tb.path("project.json").read_text(encoding="utf-8"))
            proj["voiceprint"] = {"min_lines": 3}
            tb.path("project.json").write_text(json.dumps(proj, ensure_ascii=False),
                                               encoding="utf-8")
            self.assertIn("林牧", {c["name"] for c in
                                   voiceprint.voiceprint_report(tb.book)["characters"]})


if __name__ == "__main__":
    unittest.main()
