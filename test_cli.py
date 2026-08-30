"""引擎 CLI 冻结断言（engine/README.md 所引 test_cli）。

运行：python -m unittest test_cli -v   （或 python test_cli.py）
纯 stdlib、零第三方依赖；书工作区建在临时目录，测试结束自动清理。
覆盖：批 1+2 四张工作单（review new / evidence candidates / proposal check /
evidence prev）+ 五个自交检 warning + 批 4 三台账扩展（KNO 知识线 / item holder /
current.key_relationships）+ 批 5 揭示时机对照/随身清单/retired 上台 +
批 6 软槽位（current.mood/goal）与线权重 weight 排序 + 既有闸门不回归。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import checks, common, evidence, state  # noqa: E402


# --------------------------------------------------------------------------- 夹具
BEATS1 = """---
chapter: ch_001
vol: vol_01
form: 单场景章
pov: 秦野·贴身第三人称
words: 2200-4500
style_notes: 短促 | 章首中间开始 | 章尾强钩
---
## 拍点

S1 秦野在义庄见到白七 [新实体→注册]

## 线动作

- 回收：MIS-777

## 任务书

## 目标

1. 读者能感到紧张，毛骨悚然。秦野确认白七身份存疑。

## 必须保留

- 秦野至章末仍不知义庄主事是谁。

## 本章禁忌

- 不用「灯」

## 验收

1. 秦野在义庄见白七。
2. 秦野付出四十枚。
"""

BEATS2 = """---
chapter: ch_002
vol: vol_01
form: 单场景章
form_reason: 延续压迫
pov: 秦野·贴身第三人称
words: 2400-4600
style_notes: 短促 | 章首中间开始 | 章尾强钩
---
## 拍点

S1 秦野入义庄后堂。

## 线动作

- （无）

## 任务书

## 目标

1. 秦野见到账册。

## 必须保留

- （无）

## 本章禁忌

- 不用「暗」

## 验收

1. 秦野见到账册。
"""

BEATS3 = """---
chapter: ch_003
vol: vol_01
form: 对话驱动章
pov: 秦野·贴身第三人称
words: 3000-4800
style_notes: 绵长 | 闲笔入题 | 悬置
---
## 拍点

S1 秦野问主事。

## 线动作

- 计划还樟叶线

## 任务书

## 目标

1. 秦野问出主事去向。

## 必须保留

- 主事不见秦野。

## 本章禁忌

- 不用「忽然」

## 验收

1. 秦野问出主事去向。
"""

FINAL1 = """义庄的门在身后合上，门轴发出一声长叹。

秦野数出四十枚，一枚一枚排在木格子里。「赎。」

白七的手比脸先动。账册翻过三页，当票推过来，纸角带着潮气。秦野注意到账册末页夹着一片枯叶——义庄的樟木，至少放了三年。樟叶边上有一道极浅的刻痕，像谁用针尖点过。

他收好当票，把账册推回去。白七没有抬头，也没有收账册，只是把手拢进袖子里。义庄深处很静，静得能听见樟木柜上灰簌簌往下落。

他出门时没有回头。门外的天已经黑透了。
"""

FINAL2 = ("后堂的账册摊在案上，纸页发黄，边角起毛。秦野翻到末页，那片樟叶还在。"
          "樟叶旁多了一道新刻的划痕，刻痕很浅，是近日才留下的。\n\n"
          "他合上账册，指尖在封面上停了一瞬。义庄深处传来更漏声，一下，又一下，"
          "像是有人在催他做决定。秦野站在原地，把更漏声听完了一段。\n")


def _run(args: list[str], book: Path, expect_rc: int = 0) -> subprocess.CompletedProcess:
    p = subprocess.run([sys.executable, str(ROOT / "studio.py"), *args, "-w", str(book)],
                       capture_output=True, text=True, cwd=ROOT)
    assert p.returncode == expect_rc, \
        f"{' '.join(args)} rc={p.returncode} want {expect_rc}\n{p.stdout}\n{p.stderr}"
    return p


def _run_json(args: list[str], book: Path, expect_rc: int = 0):
    return json.loads(_run([*args, "--json"], book, expect_rc).stdout)


def build_book(root: Path, with_beats3: bool = False) -> Path:
    """init + 夹具（两章 beats/final + 三个实体 + 字数带 + 书级空判据词）。"""
    b = root / "书"
    subprocess.run([sys.executable, str(ROOT / "studio.py"), "init", "-w", str(b),
                    "-t", "测试书", "-g", "悬疑", "-p", "秦野"],
                   capture_output=True, text=True, cwd=ROOT, check=True)
    for p in b.rglob("*.md"):
        t = re.sub(r"\{\{slot:[^}]*\}\}", "占位", p.read_text(encoding="utf-8"))
        p.write_text(t, encoding="utf-8")
    proj = json.loads((b / "project.json").read_text(encoding="utf-8"))
    proj["words_target"] = [100, 3000]
    proj["empty_criteria_words"] = ["毛骨悚然"]
    (b / "project.json").write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    (b / "outlines/vol_01/beats/ch_001.md").write_text(BEATS1, encoding="utf-8")
    (b / "outlines/vol_01/beats/ch_002.md").write_text(BEATS2, encoding="utf-8")
    if with_beats3:
        (b / "outlines/vol_01/beats/ch_003.md").write_text(BEATS3, encoding="utf-8")
    (b / "manuscript/vol_01/final/ch_001.md").write_text(FINAL1, encoding="utf-8")
    (b / "manuscript/vol_01/final/ch_002.md").write_text(FINAL2, encoding="utf-8")
    ents = {"entries": [
        {"name": "秦野", "type": "person", "aliases": [], "card": "", "summary": "主角", "status": "active"},
        {"name": "白七", "type": "person", "aliases": ["白掌柜"], "card": "", "summary": "义庄伙计", "status": "active"},
        {"name": "义庄", "type": "place", "aliases": [], "card": "", "summary": "停放棺木之处", "status": "active"},
    ]}
    (b / "state/entities.json").write_text(
        json.dumps(ents, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return b


# --------------------------------------------------------------------------- 纯函数
class TestUnits(unittest.TestCase):
    def test_cn_num(self):
        f = evidence._cn_num_to_int
        for s, want in {"三十": 30, "一百二": 102, "千五百": 1500, "两百": 200, "二十": 20,
                        "三": 3, "一百二十": 120, "九百九十九": 999, "十": 10,
                        "一万": None, "": None, "abc": None}.items():
            self.assertEqual(f(s), want, s)

    def test_amount_scan(self):
        pools = {"coin": {"unit": "枚"}, "silver": {"unit": "两"}, "nu": {"unit": ""}}
        text = "付了三十枚，又拿了一百二十枚；50枚、2,000枚；欠五两银子，3两。"
        d = {r["pool"]: r for r in evidence._amount_scan(text, pools)}
        self.assertEqual(d["coin"]["values"], [30, 50, 120, 2000])
        self.assertEqual(d["coin"]["count"], 4)
        self.assertEqual(d["silver"]["values"], [3, 5])
        self.assertNotIn("nu", d)

    def test_words_band_and_knobs(self):
        self.assertEqual(checks._words_band("2200-4500"), (2200, 4500))
        self.assertEqual(checks._words_band("2300～4800"), (2300, 4800))
        self.assertEqual(checks._words_band("无数字"), (None, None))
        self.assertEqual(checks._style_knobs("短促 | 章首 | 章尾"), ("短促", "章首", "章尾"))
        self.assertEqual(checks._style_knobs("短促｜章首｜章尾"), ("短促", "章首", "章尾"))
        self.assertEqual(checks._style_knobs(""), ())

    def test_md_section(self):
        md = "# t\n\n## 目标\n1. a\n2. b\n\n## 验收\n1. c\n"
        # 空行原样保留（调用方各自 strip/跳过）
        self.assertEqual(common.md_section(md, r"^##\s*目标"), ["1. a", "2. b", ""])
        self.assertEqual(common.md_section(md, r"^##\s*验收"), ["1. c"])
        self.assertEqual(common.md_section(md, r"^##\s*缺失"), [])

    def test_line_terms(self):
        reg = ["义庄", "秦野"]
        g = {"kind": "foreshadow", "name": "账册末页的樟叶", "plan": "樟叶指向义庄主事"}
        terms = evidence._line_terms_for(g, "foreshadow", reg)
        self.assertEqual(terms[0], "账册末页的樟叶")
        self.assertIn("义庄", terms)          # 经 plan 命中注册名
        self.assertNotIn("秦野", terms)        # 未出现在线元数据
        m = {"parties": "秦野、义庄主事", "content": "误会义庄主事是白七"}
        terms = evidence._line_terms_for(m, "misunderstanding", reg)
        self.assertEqual(terms[0], "秦野、义庄主事")
        self.assertIn("秦野", terms)           # parties 分词
        self.assertIn("义庄", terms)           # content 内含注册名


# --------------------------------------------------------------------------- 只读命令（未 sync 现场）
class TestReadOnlyCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="noveltest_ro_")
        cls.book = build_book(Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_check_new_warnings(self):
        d = _run_json(["check", "--json"], self.book)
        codes = {w["code"]: w["msg"] for w in d["warnings"]}
        self.assertEqual(d["errors"], [])
        msg = codes["acceptance_empty_criterion"]
        for w in ("读者", "感到", "紧张", "毛骨悚然"):
            self.assertIn(w, msg, msg)
        self.assertIn("MIS-777", codes["line_action_orphan"])
        self.assertTrue(any(w["code"] == "style_notes_copy" and "ch_002" in w["msg"]
                            for w in d["warnings"]))
        self.assertTrue(any(w["code"] == "words_band_crowded" and "ch_002" in w["msg"]
                            for w in d["warnings"]))
        self.assertTrue(any(w["code"] == "goal_no_split" and "ch_002" in w["msg"]
                            for w in d["warnings"]))
        self.assertFalse(any(w["code"] == "style_notes_copy" and "ch_001" in w["msg"]
                             for w in d["warnings"]))

    def test_candidates(self):
        d = _run_json(["evidence", "candidates", "ch_001"], self.book)
        amt = {a["pool"]: a for a in d["amounts"]}
        self.assertEqual(amt["standard_currency"]["values"], [1, 40])
        self.assertEqual(amt["standard_currency"]["count"], 3)
        self.assertEqual(len(d["new_entity_markers"]), 1)
        self.assertIn("白七", d["new_entity_markers"][0]["text"])
        self.assertEqual(d["present_candidates"], {"秦野": 2, "白七": 2, "义庄": 3})
        self.assertEqual(d["state_digest"], {})
        self.assertEqual(d["line_hits"], [])
        self.assertEqual(d["quote_balance"]["「"], d["quote_balance"]["」"])
        self.assertEqual(d["residue"], {"slot": 0, "candidate": 0})

    def test_prev_contrast(self):
        d = _run_json(["evidence", "prev", "ch_002"], self.book)
        self.assertEqual(d["prev"]["form"], "单场景章")
        self.assertEqual(d["prev"]["words"], "2200-4500")
        self.assertEqual(d["prev"]["must_keep"], ["秦野至章末仍不知义庄主事是谁。"])
        self.assertIn("秦野", d["prev_tail"])
        self.assertLessEqual(len(d["prev_tail"]), 300)
        self.assertIsNotNone(d["cur"])
        self.assertIsNone(_run_json(["evidence", "prev", "ch_001"], self.book)["prev"])

    def test_review_print_json_and_errors(self):
        p = _run(["review", "new", "ch_001"], self.book)
        self.assertIn("1. 秦野在义庄见白七。", p.stdout)
        self.assertIn("2. 秦野付出四十枚。", p.stdout)
        self.assertIn("秦野至章末仍不知义庄主事是谁。", p.stdout)
        self.assertIn("「=1 」=1", p.stdout)
        d = _run_json(["review", "new", "ch_001"], self.book)
        self.assertEqual(d["acceptance"], ["秦野在义庄见白七。", "秦野付出四十枚。"])
        self.assertEqual(_run(["review", "new", "ch_009"], self.book,
                              expect_rc=1).returncode, 1)
        _run(["evidence", "candidates", "abc"], self.book, expect_rc=2)

    def test_review_write_and_refuse(self):
        _run(["review", "new", "ch_001", "--write"], self.book)
        p = _run(["review", "new", "ch_001", "--write"], self.book, expect_rc=1)
        self.assertIn("已存在", p.stdout)
        self.assertTrue((self.book / "log/review/ch_001.md").is_file())

    def test_proposal_check_no_proposal(self):
        d = _run_json(["proposal", "check", "ch_009"], self.book, expect_rc=1)
        self.assertIn("error", d)
        p = _run(["proposal", "check", "ch_009"], self.book, expect_rc=1)
        self.assertIn("未找到", p.stdout)


# --------------------------------------------------------------------------- Stage 4 全流程（含落盘）
class TestStage4Flow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="noveltest_flow_")
        cls.book = build_book(Path(cls._tmp.name), with_beats3=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_full_stage4(self):
        b = self.book
        # 注记：骨架 → 填验收 → review_gate 过
        _run(["review", "new", "ch_001", "--write"], b)
        rp = b / "log/review/ch_001.md"
        t = rp.read_text(encoding="utf-8")
        t = t.replace("1. 秦野在义庄见白七。 ", "1. 秦野在义庄见白七。 ✓ 证据：「白七的手比脸先动」")
        t = t.replace("2. 秦野付出四十枚。 ", "2. 秦野付出四十枚。 ✓ 证据：「秦野数出四十枚」")
        rp.write_text(t, encoding="utf-8")
        self.assertEqual(checks.review_gate(b, "ch_001"), [])

        # 提案：六区填实 → proposal check 三方对照 → 幂等 → sync
        _run(["proposal", "new", "ch_001", "--write"], b)
        pp = b / "state/inbox/ch_001.json"
        d = json.loads(pp.read_text(encoding="utf-8"))
        d["current"] = {"time": "第一日·昏", "location": "义庄", "present_characters": ["秦野", "白七"]}
        d["lines"] = [{"kind": "foreshadow", "action": "plant", "name": "账册末页的樟叶",
                       "target_ch": 1, "plan": "樟叶指向义庄主事的去向"}]
        d["ledger"] = {"transactions": [{"pool": "standard_currency", "delta": -40,
                                         "subject": "赎当票"}]}
        d["synopsis"] = {"title": "义庄", "text": "秦野付四十枚赎当票，账册末页夹着三年樟叶。"}
        pp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

        d = _run_json(["proposal", "check", "ch_001"], b)
        self.assertEqual(d["check"]["errors"], [])
        cf = d["cross_facts"]
        self.assertEqual(cf["amounts_in_final"][0]["values"], [1, 40])
        self.assertEqual(cf["ledger_tx_in_proposal"], 1)
        self.assertEqual(cf["present_in_proposal"], ["秦野", "白七"])
        self.assertEqual(cf["present_mentions"]["秦野"], 2)
        before = {x.name: x.read_bytes() for x in (b / "state").glob("*.json")}
        _run(["proposal", "check", "ch_001", "--json"], b)
        after = {x.name: x.read_bytes() for x in (b / "state").glob("*.json")}
        self.assertEqual(before, after)  # 预检不落盘

        _run(["sync", "ch_001", "--dry-run"], b)
        _run(["sync", "ch_001"], b)
        row = _run_json(["status", "--json"], b)["pipeline"][0]
        for k in ("beats", "final", "proposal_merged", "snapshot"):
            self.assertTrue(row[k], row)

        # ch_002：update 线 target→2 → 提案 check 应见 due_lines(GUN-001)+提案操作
        _run(["review", "new", "ch_002", "--write"], b)
        rp2 = b / "log/review/ch_002.md"
        rp2.write_text(rp2.read_text(encoding="utf-8").replace(
            "1. 秦野见到账册。 ", "1. 秦野见到账册。 ✓ 证据：「后堂的账册摊在案上」"), encoding="utf-8")
        _run(["proposal", "new", "ch_002", "--write"], b)
        pp2 = b / "state/inbox/ch_002.json"
        d = json.loads(pp2.read_text(encoding="utf-8"))
        d["current"] = {"time": "第二日·夜", "location": "义庄·后堂", "present_characters": ["秦野"]}
        d["lines"] = [{"kind": "foreshadow", "action": "update", "id": "GUN-001",
                       "target_ch": 2, "status": "Reminded"}]
        d["synopsis"] = {"title": "后堂", "text": "账册樟叶旁现新划痕，近日所留。"}
        pp2.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

        d = _run_json(["proposal", "check", "ch_002"], b)
        cf = d["cross_facts"]
        self.assertEqual(cf["due_lines"], [{"id": "GUN-001", "target_ch": 1}])
        self.assertEqual(cf["lines_ops_in_proposal"], ["GUN-001"])
        _run(["sync", "ch_002"], b)

        # 逾期未还：ch_003 beats 不提 GUN-001 → line_action_missing 点名
        d = _run_json(["check", "--json"], b)
        msgs = [w["msg"] for w in d["warnings"]
                if w["code"] == "line_action_missing" and "ch_003" in w["msg"]]
        self.assertTrue(any("GUN-001" in m for m in msgs), msgs)

        # sync 后 candidates：line_hits 经 plan 命中、due_lines、state_digest
        d = _run_json(["evidence", "candidates", "ch_002"], b)
        hit = next(h for h in d["line_hits"] if h["id"] == "GUN-001")
        self.assertEqual(hit["hits"].get("义庄"), 1)
        self.assertIn({"id": "GUN-001", "kind": "foreshadow", "target_ch": 2}, d["due_lines"])
        self.assertEqual(d["state_digest"]["location"], "义庄·后堂")

    def test_review_gate_rejects_unfilled(self):
        """未填验收的注记不得过 review_gate（闸门不回归；自包含，不依赖其他用例）。"""
        b = self.book
        rp2 = b / "log/review/ch_002.md"
        existed = rp2.read_text(encoding="utf-8") if rp2.is_file() else None
        try:
            # beats ch_002 有 1 条验收；注记缺 ✓/✗ → 必拒
            rp2.write_text("# ch_002\n\n## 验收\n\n1. 秦野见到账册。 \n", encoding="utf-8")
            issues = checks.review_gate(b, "ch_002")
            self.assertTrue(issues, "缺 ✓/✗ 的注记应被拒")
            # 补上判定符与引文证据 → 通过
            rp2.write_text("# ch_002\n\n## 验收\n\n1. 秦野见到账册。 ✓ 证据：「后堂的账册摊在案上」\n",
                           encoding="utf-8")
            self.assertEqual(checks.review_gate(b, "ch_002"), [])
        finally:
            if existed is not None:
                rp2.write_text(existed, encoding="utf-8")
            elif rp2.is_file():
                rp2.unlink()


# --------------------------------------------------------------------------- 批 4：知识线 / item 持有 / 当前关系
FINAL3 = ("义庄主事不见秦野。秦野问白七主事去向，白七只说「早就走了」，说完便低下头去拨算盘。"
          "秦野收好当票，把账册推回去，出门时没有回头。回家路上他忽然明白："
          "白七从头到尾不是主事，只是看守。他想起柜台下那只比脸先动的手，后颈又一次发凉，"
          "把袖子拢了拢。")

BEATS4 = """---
chapter: ch_004
vol: vol_01
form: 单场景章
pov: 秦野·贴身第三人称
words: 3000-4800
style_notes: 短促 | 章首中间开始 | 章尾强钩
---
## 拍点

S1 秦野与白七摊牌。

## 线动作

- 揭示：KNO-001

## 任务书

## 目标

1. 白七承认自己只是看守。

## 必须保留

- （无）

## 本章禁忌

- 不用「忽然」

## 验收

1. 白七承认自己只是看守。
"""

FINAL4 = ("秦野把当票拍在柜台上，问白七主事到底是谁。白七拨算盘的手停了，半晌，"
          "承认自己只是看守，主事从来就没来过。秦野盯着他，后颈那股凉意总算散了大半。"
          "柜台的影子落在两人中间，谁也没有再说话。秦野把玉佩收进怀里，拢了拢袖子，"
          "最后才转身出门。门外的天黑透了，更漏声从远处传过来，一下，又一下。")


class TestKnowledgeAndItems(unittest.TestCase):
    """批 4 扩展：KNO 知识线生命周期 + item holder 闭合 + current.key_relationships。
    自包含（自带 build_book），不依赖其他用例的落盘。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="noveltest_kno_")
        cls.book = build_book(Path(cls._tmp.name), with_beats3=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_holder_closure_in_memory(self):
        data = {key: state.defaults_for(key) for key in state.STATE_KEYS}
        data["entities"]["entries"] = [
            {"name": "秦野", "type": "person", "aliases": [], "card": "", "summary": "", "status": "active"},
            {"name": "玉佩", "type": "item", "aliases": [], "card": "", "summary": "", "status": "active",
             "holder": "秦野", "location": "怀中", "condition": "完整"},
        ]
        self.assertEqual(state.verify_data(data), [])
        data["entities"]["entries"][1]["holder"] = "不存在的人"
        errs = state.verify_data(data)
        self.assertTrue(any("holder" in e for e in errs), errs)

    def test_kno_lifecycle_in_memory(self):
        lines = state.defaults_for("lines")
        rep = {"updated": [], "warnings": [], "errors": []}
        state._merge_lines(lines, [{"kind": "knowledge", "action": "plant",
                                    "secret": "白七不是义庄主事，他是看守的", "target_ch": 2,
                                    "note": "秦野 ch_2 前不得知道"}], 3, rep)
        self.assertEqual(rep["errors"], [])
        k = lines["knowledge"][0]
        self.assertEqual((k["id"], k["status"], k["plant_ch"], k["target_ch"]),
                         ("KNO-001", "Concealed", 3, 2))
        rep2 = {"updated": [], "warnings": [], "errors": []}
        state._merge_lines(lines, [{"kind": "knowledge", "action": "update", "id": "KNO-001",
                                    "target_ch": 5}], 3, rep2)
        state._merge_lines(lines, [{"kind": "knowledge", "action": "resolve",
                                    "id": "KNO-001"}], 3, rep2)
        self.assertEqual(rep2["errors"], [])
        self.assertEqual((lines["knowledge"][0]["target_ch"], lines["knowledge"][0]["status"]),
                         (5, "Revealed"))

        # remind 只适用于 foreshadow：knowledge remind 拒绝
        errs, _ = state.validate_proposal({"chapter": "ch_003", "operation_id": "t.kno.a1",
                                           "lines": [{"kind": "knowledge", "action": "remind",
                                                      "id": "KNO-001"}]})
        self.assertTrue(any("remind" in e for e in errs), errs)
        # ID 前缀必须是 KNO
        errs, _ = state.validate_proposal({"chapter": "ch_003", "operation_id": "t.kno.a2",
                                           "lines": [{"kind": "knowledge", "action": "plant", "secret": "x",
                                                      "id": "GUN-001", "target_ch": 2}]})
        self.assertTrue(any("KNO" in e for e in errs), errs)
        # resolve 不允许携带额外字段
        errs, _ = state.validate_proposal({"chapter": "ch_003", "operation_id": "t.kno.a3",
                                           "lines": [{"kind": "knowledge", "action": "resolve",
                                                      "id": "KNO-001", "note": "x"}]})
        self.assertTrue(any("note" in e for e in errs), errs)

        # 批6 S-B：weight 生命周期（plant 缺省 1 / 显式 3 / update 改 2）
        lines1 = state.defaults_for("lines")
        rep1 = {"updated": [], "warnings": [], "errors": []}
        state._merge_lines(lines1, [
            {"kind": "foreshadow", "action": "plant", "name": "无权重伏笔", "target_ch": 9},
            {"kind": "knowledge", "action": "plant", "secret": "带权重秘密", "target_ch": 5,
             "weight": 3},
        ], 3, rep1)
        self.assertEqual(rep1["errors"], [])
        self.assertEqual(lines1["foreshadows"][0]["weight"], 1)  # 缺省 1
        self.assertEqual(lines1["knowledge"][0]["weight"], 3)
        rep1b = {"updated": [], "warnings": [], "errors": []}
        state._merge_lines(lines1, [{"kind": "knowledge", "action": "update", "id": "KNO-001",
                                     "weight": 2}], 3, rep1b)
        self.assertEqual(lines1["knowledge"][0]["weight"], 2)
        # 非法权重（非整数 / <1）拒绝
        for bad in ("high", 0, True):
            errs, _ = state.validate_proposal({"chapter": "ch_003", "operation_id": "t.kno.w",
                                               "lines": [{"kind": "knowledge", "action": "plant",
                                                          "secret": "x", "target_ch": 5,
                                                          "weight": bad}]})
            self.assertTrue(any("weight" in e for e in errs), (bad, errs))

        # 批5 A1：揭示时机在 sync 报告里标章（提前/逾期），准点不标
        lines2 = state.defaults_for("lines")
        rep3 = {"updated": [], "warnings": [], "errors": []}
        state._merge_lines(lines2, [{"kind": "knowledge", "action": "plant", "secret": "x",
                                     "target_ch": 5}], 3, rep3)
        rep4 = {"updated": [], "warnings": [], "errors": []}
        state._merge_lines(lines2, [{"kind": "knowledge", "action": "resolve", "id": "KNO-001"}], 3, rep4)
        msg = rep4["updated"][-1]
        self.assertIn("提前", msg)
        self.assertIn("ch_005", msg)
        self.assertIn("ch_003", msg)
        rep5 = {"updated": [], "warnings": [], "errors": []}
        state._merge_lines(lines2, [{"kind": "knowledge", "action": "plant", "secret": "y",
                                     "target_ch": 4}], 4, rep5)
        state._merge_lines(lines2, [{"kind": "knowledge", "action": "resolve", "id": "KNO-002"}], 4, rep5)
        self.assertEqual(rep5["updated"][-1], "🔓 KNO-002 已揭示")

    def test_kno_sync_and_overdue(self):
        b = self.book
        (b / "manuscript/vol_01/final/ch_003.md").write_text(FINAL3, encoding="utf-8")
        (b / "log/review/ch_003.md").write_text(
            "# ch_003\n\n## 验收\n\n1. 秦野问出主事去向。 ✓ 证据：「早就走了」\n", encoding="utf-8")
        _run(["proposal", "new", "ch_003", "--write"], b)
        pp = b / "state/inbox/ch_003.json"
        d = json.loads(pp.read_text(encoding="utf-8"))
        d["current"] = {"time": "第三日·晨", "location": "义庄", "present_characters": ["秦野", "白七"],
                        "key_relationships": "秦野↔白七：试探未明",
                        "mood": "疑惧交加，对白七戒备", "goal": "查清主事去向，防被当成贼"}
        d["entities"] = [{"action": "upsert", "name": "玉佩", "type": "item", "summary": "遗物",
                          "holder": "秦野", "location": "怀中", "condition": "完整"}]
        d["lines"] = [
            # target 1：封存时已逾期（cur=3），权重 1
            {"kind": "knowledge", "action": "plant",
             "secret": "白七不是义庄主事，他是看守的", "target_ch": 1, "weight": 1,
             "note": "秦野 ch_3 前不得知道"},
            # longline 权重 2：不进 due/upcoming，只挂账（排序殿后）
            {"kind": "knowledge", "action": "plant",
             "secret": "墙皮后的公册是十年前埋的", "target_ch": "longline", "weight": 2},
            # target 4 = cur+1：status「账上提醒」的 soon 区间，权重 3
            {"kind": "knowledge", "action": "plant", "id": "KNO-003",
             "secret": "账册末页的刻痕是谁留的", "target_ch": 4, "weight": 3},
        ]
        d["synopsis"] = {"title": "主事", "text": "秦野问出主事去向，确认白七只是看守。"}
        pp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

        d = _run_json(["proposal", "check", "ch_003"], b)
        self.assertEqual(d["check"]["errors"], [])
        _run(["sync", "ch_003", "--dry-run"], b)  # 预演路径同样吃 KNO
        _run(["sync", "ch_003"], b)

        lines = json.loads((b / "state/lines.json").read_text(encoding="utf-8"))
        self.assertEqual([(k["id"], k["status"], k["target_ch"], k["weight"])
                          for k in lines["knowledge"]],
                         [("KNO-001", "Concealed", 1, 1),
                          ("KNO-002", "Concealed", "longline", 2),
                          ("KNO-003", "Concealed", 4, 3)])
        cur = json.loads((b / "state/current.json").read_text(encoding="utf-8"))
        self.assertEqual(cur["key_relationships"], "秦野↔白七：试探未明")
        self.assertEqual(cur["mood"], "疑惧交加，对白七戒备")
        self.assertEqual(cur["goal"], "查清主事去向，防被当成贼")
        ents = json.loads((b / "state/entities.json").read_text(encoding="utf-8"))["entries"]
        item = [e for e in ents if e["name"] == "玉佩"][0]
        self.assertEqual((item["holder"], item["location"], item["condition"]),
                         ("秦野", "怀中", "完整"))

        g = _run_json(["evidence", "gaps", "--json"], b)
        self.assertEqual(g["summary"]["open_knowledge"], 3)
        self.assertEqual(g["summary"]["overdue_knowledge"], 1)
        self.assertTrue([k for k in g["knowledge"] if k["id"] == "KNO-001"][0]["overdue"])
        self.assertFalse([k for k in g["knowledge"] if k["id"] == "KNO-002"][0]["overdue"])
        # 批6 S-B：清单排序——权重高→低（3→1），longline 殿后；条目带 weight
        self.assertEqual([k["id"] for k in g["knowledge"]], ["KNO-003", "KNO-001", "KNO-002"])
        self.assertEqual([k["weight"] for k in g["knowledge"]], [3, 1, 2])
        d = _run_json(["check", "--json"], b)
        self.assertTrue(any(w["code"] == "line_overdue" and "KNO-001" in w["msg"]
                            for w in d["warnings"]))
        self.assertTrue(any(w["code"] == "line_action_missing" and "KNO-001" in w["msg"]
                            for w in d["warnings"]))
        p = _run_json(["pack", "ch_003", "--json"], b)
        self.assertTrue(any("KNO-001" in m for m in p["p0"]["hard_reminders"]))
        self.assertFalse(any("KNO-002" in m for m in p["p0"]["hard_reminders"]))  # longline 不催
        self.assertEqual(p["p0"]["current"]["key_relationships"], "秦野↔白七：试探未明")
        # 批6 S-A/S-C：软槽位原样进 P0 回温
        self.assertEqual(p["p0"]["current"]["mood"], "疑惧交加，对白七戒备")
        self.assertEqual(p["p0"]["current"]["goal"], "查清主事去向，防被当成贼")

        # export 台账表：权重列
        _run(["export", "--views"], b)
        view = (b / "export/views/state_view.md").read_text(encoding="utf-8")
        self.assertTrue(any(ln.startswith("| KNO-003 |") and "| 3 |" in ln
                            for ln in view.splitlines()), view)

        # candidates：secret/note 中的注册名被计数；due/upcoming 含 knowledge；longline 不催
        d = _run_json(["evidence", "candidates", "ch_003"], b)
        kno_hits = [h for h in d["line_hits"] if h["id"] == "KNO-001"]
        self.assertTrue(kno_hits, "secret/note 中的注册名应被计数")
        self.assertEqual(kno_hits[0]["kind"], "knowledge")
        self.assertGreaterEqual(kno_hits[0]["hits"].get("白七", 0), 2)
        self.assertIn({"id": "KNO-001", "kind": "knowledge", "target_ch": 1}, d["due_lines"])
        self.assertIn({"id": "KNO-003", "kind": "knowledge", "target_ch": 4}, d["upcoming_lines"])
        self.assertFalse(any(x["id"] == "KNO-002" for x in d["due_lines"] + d["upcoming_lines"]))

        # P1：beats 出现过的实体被知识线触碰；item 实体块带 holder 三字段
        qy = [x for x in p["p1"]["entities"] if x["name"] == "秦野"][0]
        self.assertIn("KNO-001(Concealed)", qy["lines"])
        from engine import pack as pack_mod
        cur = {key: state.load_state(b, key) for key in ("current", "entities", "lines")}
        block = pack_mod._entity_block(b, "玉佩", cur, cur["lines"], full=False)
        self.assertEqual((block["holder"], block["location"], block["condition"]),
                         ("秦野", "怀中", "完整"))

        # status 账上提醒：soon 区间（target 4 = cur+1）报 KNO-003；longline 不报
        st = _run(["status"], b)
        self.assertIn("KNO-003", st.stdout)
        self.assertNotIn("KNO-002", st.stdout)

        # ---- 批5 A2：P1 人物块随身清单（holder 反查：秦野 → 玉佩） ----
        self.assertEqual(qy["carries"], ["玉佩（怀中·完整）"])

        # ---- 批5 A1+A3：ch_004 提案（KNO-001 逾期揭示 + 白七 retired 仍上台） ----
        (b / "outlines/vol_01/beats/ch_004.md").write_text(BEATS4, encoding="utf-8")
        (b / "manuscript/vol_01/final/ch_004.md").write_text(FINAL4, encoding="utf-8")
        (b / "log/review/ch_004.md").write_text(
            "# ch_004\n\n## 验收\n\n1. 白七承认自己只是看守。 ✓ 证据：「承认自己只是看守」\n",
            encoding="utf-8")
        _run(["proposal", "new", "ch_004", "--write"], b)
        pp4 = b / "state/inbox/ch_004.json"
        d4 = json.loads(pp4.read_text(encoding="utf-8"))
        d4["current"] = {"time": "第三日·暮", "location": "义庄",
                         "present_characters": ["秦野", "白七"]}
        d4["entities"] = [{"action": "upsert", "name": "白七", "status": "retired"}]
        d4["lines"] = [{"kind": "knowledge", "action": "resolve", "id": "KNO-001"}]
        d4["synopsis"] = {"title": "摊牌", "text": "秦野摊牌，白七承认只是看守。"}
        pp4.write_text(json.dumps(d4, ensure_ascii=False, indent=2), encoding="utf-8")

        d4 = _run_json(["proposal", "check", "ch_004"], b)
        self.assertEqual(d4["cross_facts"].get("kno_reveal_timing"),
                         [{"id": "KNO-001", "planned_ch": 1, "chapter": 4, "early": False}])
        sp = _run(["sync", "ch_004"], b)
        self.assertIn("逾期", sp.stdout)
        self.assertIn("KNO-001", sp.stdout)

        d4 = _run_json(["check", "--json"], b)
        self.assertEqual(d4["errors"], [])
        self.assertTrue(any(w["code"] == "retired_entity_on_stage" and "白七" in w["msg"]
                            for w in d4["warnings"]))

    def test_old_lines_file_fills_knowledge(self):
        """旧版 lines.json 缺 knowledge 键：读时按结构补齐（不报错、不改语义）。"""
        b = self.book
        p = b / "state/lines.json"
        raw = p.read_text(encoding="utf-8")
        try:
            d = json.loads(raw)
            d.pop("knowledge", None)
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            lines = state.load_state(b, "lines")
            self.assertEqual(lines["knowledge"], [])
        finally:
            p.write_text(raw, encoding="utf-8")


if __name__ == "__main__":
    unittest.main(verbosity=2)
