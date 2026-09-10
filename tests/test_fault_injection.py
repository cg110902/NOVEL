"""故障注入（负向）测试套件 —— 证明闸门真的存在。

动机：项目 268 个测试几乎全是正向用例。正向只能证明「没坏」，
负向才能证明「文档承诺的闸门真的会拦」。errcodes 注册了 55 个错误码，
本套件为其中最有代表性的一批补上「必须报错」的断言。

纪律（否则就是自欺）：
- 每个用例断言**必须被拒**，不是「不报错就通过」；
- 断言尽量点名错误码/关键词，避免 `assertTrue(errors)` 这种恒真式；
- 每个用例先跑 mutate 自检：见 tests/mutation_guard.py 的配套变异。

零 LLM token、纯脚本、秒级。
"""
from __future__ import annotations

import copy
import json
import unittest

from tests._fixtures import TempBook


def _v2(ch="ch_001", op="ch_001.fault.01", **kw):
    p = {"schema": "novel-studio.state-mutation/v2", "chapter": ch, "operation_id": op}
    p.update(kw)
    return p


def _v3(ch="ch_001", op="ch_001.fault.01", *ops):
    return {"schema": "novel-studio.state-mutation/v3", "chapter": ch,
            "operation_id": op, "ops": list(ops)}


REJECT = "该提案必须被拒绝，但被静默放行了"


class _Base(unittest.TestCase):
    def _rejected(self, prop, expected_ch="ch_001", *, book=None, needle=None):
        """返回 errors；断言非空，且（若给 needle）命中关键词。"""
        from engine import state
        errs = state.apply_proposal(book, copy.deepcopy(prop), expected_ch, dry_run=True)
        errors = errs.get("errors") or []
        self.assertTrue(errors, f"{REJECT}: {prop}")
        if needle:
            self.assertTrue(any(needle in e for e in errors),
                            f"期望命中「{needle}」，实际: {errors}")
        return errors

    def _rejected_envelope(self, prop, expected_ch="ch_001", *, book=None, needle=None):
        """只走信封 + 业务规则层（validate_proposal），不进合并。"""
        from engine import state
        errors, _ = state.validate_proposal(copy.deepcopy(prop), expected_ch, book=book)
        self.assertTrue(errors, f"{REJECT}: {prop}")
        if needle:
            self.assertTrue(any(needle in e for e in errors),
                            f"期望命中「{needle}」，实际: {errors}")
        return errors


# ---------------------------------------------------------------------------
# 一、信封与业务规则层（validate_proposal）
# ---------------------------------------------------------------------------
class TestEnvelopeGates(_Base):
    def test_pool_missing_initial_rejected(self):
        """新池省略 initial 会被当成 0，污染整本书余额基准 → 必须拒收。"""
        self._rejected_envelope(
            _v2(ledger={"pools": {"stone": {"name": "灵石", "unit": "块"}}}),
            needle="initial")

    def test_pool_declaring_current_rejected(self):
        """余额一律由流水重算；声明 current 即拒收。"""
        self._rejected_envelope(
            _v2(ledger={"pools": {"stone": {"name": "灵石", "unit": "块",
                                            "initial": 10, "current": 10}}}),
            needle="current")

    def test_pool_unknown_key_rejected(self):
        """池对象只认 name/unit/initial 三键（键名打错如 intial 必须现形）。"""
        self._rejected_envelope(
            _v2(ledger={"pools": {"stone": {"name": "灵石", "unit": "块",
                                            "initial": 1, "extra": 1}}}),
            needle="未知字段")

    def test_cross_chapter_transaction_rejected(self):
        """流水只能记在本章，禁止改写他章账目。"""
        self._rejected_envelope(
            _v2(ledger={"transactions": [{"chapter": "ch_002", "pool": "standard_currency",
                                          "delta": -10, "type": "expense", "subject": "x"}]}),
            needle="提案所属章")

    def test_income_must_be_positive(self):
        self._rejected_envelope(
            _v2(ledger={"transactions": [{"chapter": "ch_001", "pool": "standard_currency",
                                          "delta": -5, "type": "income", "subject": "x"}]}),
            needle="type=income")

    def test_expense_must_be_negative(self):
        self._rejected_envelope(
            _v2(ledger={"transactions": [{"chapter": "ch_001", "pool": "standard_currency",
                                          "delta": 5, "type": "expense", "subject": "x"}]}),
            needle="type=expense")

    def test_charges_over_max_rejected(self):
        self._rejected_envelope(
            _v2(entities=[{"name": "断水剑", "id": "it_001", "type": "item",
                           "charges": 9, "max_charges": 3}]),
            needle="max_charges")

    def test_plant_requires_target_ch(self):
        """缺省会静默占用长线配额（全书仅 5 条），故强制显式声明。"""
        self._rejected_envelope(
            _v2(lines=[{"kind": "foreshadow", "action": "plant",
                        "id": "GUN-001", "name": "断刀来历"}]),
            needle="target_ch")

    def test_target_ch_rejects_unpadded(self):
        """ch_7（无补零）与 "21"（字符串数字）都必须拒收。"""
        for bad in ("ch_7", "21"):
            with self.subTest(bad=bad):
                self._rejected_envelope(
                    _v2(lines=[{"kind": "foreshadow", "action": "plant", "id": "GUN-001",
                                "name": "断刀来历", "target_ch": bad}]),
                    needle="target_ch")

    def test_locked_requires_note(self):
        """只记 fact 不记红线，日后判断能否绕过时无据可依。"""
        self._rejected_envelope(
            _v2(locked=[{"id": "LOCK-001", "fact": "断水剑断于江边",
                         "kind": "destruction", "quote": "咔嚓"}]),
            needle="note")

    def test_derived_partition_rejected(self):
        """derived 是引擎派生表，提案禁写。"""
        self._rejected_envelope(_v2(derived={"stats": {}}), needle="derived")

    def test_candidate_field_rejected(self):
        """candidate_* 是复核用候选字段，不得进入合并。"""
        self._rejected_envelope(_v2(candidate_foo=[1]), needle="candidate_")

    def test_explicit_null_rejected(self):
        """闸门语义：Optional 键要么缺席要么合法值，显式 null 非法。"""
        self._rejected_envelope(_v2(current={"injury": None}), needle="null")

    def test_duplicate_entity_name_in_one_proposal(self):
        """同案重名会被静默折叠成一条，导致登记数据凭空丢失。"""
        self._rejected_envelope(
            _v2(entities=[{"name": "林牧", "id": "p_001", "type": "person"},
                          {"name": "林牧", "id": "p_002", "type": "person"}]),
            needle="重名")

    def test_unknown_entity_field_rejected(self):
        self._rejected_envelope(
            _v2(entities=[{"name": "林牧", "id": "p_001", "type": "person", "realm_x": 1}]),
            needle="未知字段")

    def test_bad_locked_kind_rejected(self):
        self._rejected_envelope(
            _v2(locked=[{"id": "LOCK-001", "fact": "刀断了", "kind": "nonsense",
                         "quote": "咔嚓", "note": "不可复原"}]),
            needle="kind")

    def test_draft_flag_rejected(self):
        self._rejected_envelope(_v2(_draft=True), needle="草稿")

    def test_missing_operation_id_rejected(self):
        self._rejected_envelope(_v2(op="") if False else
                                {"schema": "novel-studio.state-mutation/v2",
                                 "chapter": "ch_001"},
                                needle="operation_id")


# ---------------------------------------------------------------------------
# 二、合并与写闸门层（跨表一致性，validate_proposal 看不到）
# ---------------------------------------------------------------------------
class TestMergeGates(_Base):
    def test_undeclared_pool_rejected(self):
        """流水引用未声明的池 → 合并期拦下（validate_proposal 层看不到全量账本）。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧买了一把刀。")
            self._rejected(
                _v2(ledger={"transactions": [{"chapter": "ch_001", "pool": "stone",
                                              "delta": -10, "type": "expense",
                                              "subject": "买刀"}]}),
                book=tb.book, needle="ledger_pool_undeclared")

    def test_locked_id_reuse_rejected(self):
        """不可逆事实禁止就地覆写；改史须 retire 留痕后另立新 ID。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "玄阳子倒在血泊中，再没起来。")
            rep = tb_run_apply(tb, _v2(
                locked=[{"id": "LOCK-001", "fact": "玄阳子战死", "kind": "death",
                         "since_ch": "ch_001", "quote": "倒在血泊中",
                         "note": "严禁再次出场"}]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            # 同 ID 改内容 → 拒收
            self._rejected(
                _v2(op="ch_001.fault.02",
                    locked=[{"id": "LOCK-001", "fact": "玄阳子其实没死", "kind": "death",
                             "since_ch": "ch_001", "quote": "倒在血泊中",
                             "note": "改史"}]),
                book=tb.book, needle="LOCK-001")

    def test_cognition_id_reuse_rejected(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧知道刀断了。")
            rep = tb_run_apply(tb, _v2(
                cognition=[{"id": "COG-001", "character": "林牧", "kind": "fact",
                            "content": "刀断了", "since_ch": "ch_001", "quote": "刀断了"}]))
            self.assertEqual(rep["errors"], [], rep["errors"])
            self._rejected(
                _v2(op="ch_001.fault.02",
                    cognition=[{"id": "COG-001", "character": "张彪", "kind": "fact",
                                "content": "刀断了", "since_ch": "ch_001",
                                "quote": "刀断了"}]),
                book=tb.book, needle="COG-001")

    def test_prerequisite_unmet_blocks_resolve(self):
        """前置线未闭环就收网 → 写闸门（_prereq_errors）拦截，不等 check。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧看着远方。")
            tb_run_apply(tb, _v2(lines=[
                {"kind": "foreshadow", "action": "plant", "id": "GUN-001",
                 "name": "前置线", "target_ch": 10},
                {"kind": "foreshadow", "action": "plant", "id": "GUN-002",
                 "name": "依赖线", "target_ch": 10, "requires": ["GUN-001"]},
            ]))
            self._rejected(
                _v2(op="ch_001.fault.02",
                    lines=[{"kind": "foreshadow", "action": "resolve", "id": "GUN-002"}]),
                book=tb.book, needle="前置")

    def test_deceased_in_present_characters_rejected(self):
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧独自站着。")
            tb_run_apply(tb, _v2(
                entities=[{"name": "林牧", "id": "p_001", "type": "person"},
                          {"name": "玄阳子", "id": "p_002", "type": "person",
                           "life_status": "deceased"}],
                current={"present_characters": ["林牧"]}))
            self._rejected(
                _v2(op="ch_001.fault.02",
                    current={"present_characters": ["林牧", "玄阳子"]}),
                book=tb.book, needle="离世")

    def test_operation_id_reuse_with_different_content(self):
        """同 operation_id 异内容 = 拒收（防复用 id 悄悄改内容）。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧买了一把刀。")
            tb_run_apply(tb, _v2(current={"location": "临江城"}))
            self._rejected(_v2(current={"location": "落鹰峡"}),
                           book=tb.book, needle="operation_id")

    def test_same_operation_id_same_content_is_idempotent(self):
        """同 id 同内容 = 幂等跳过（不是报错）——崩溃重放保护。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧买了一把刀。")
            tb_run_apply(tb, _v2(current={"location": "临江城"}))
            from engine import state
            rep = state.apply_proposal(tb.book, _v2(current={"location": "临江城"}), "ch_001")
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertTrue(rep.get("duplicate"), rep)


# ---------------------------------------------------------------------------
# 三、v3 寻址式提案的严格性（typo-guard）
# ---------------------------------------------------------------------------
class TestV3AddressingGates(_Base):
    def test_create_existing_id_rejected(self):
        """v3 核心价值：create 撞已存在 id → 点名拒收（v2 会静默更新）。

        注意口径（proposal_v3 预门设计）：必须「同效异写」才会落到存在性检查。
        「同字节重放」被预门短路为干净 skip —— 那是崩溃重放保护，不是漏检
        （见 test_create_replay_is_clean_skip）。
        """
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进大殿。")
            tb_run_apply(tb, _v3("ch_001", "op1",
                                 {"table": "persons", "action": "create",
                                  "entry": {"id": "p_001", "name": "林牧", "type": "person"}}))
            # 同 id、不同内容 → 落到编译期存在性检查，必须点名拒收
            self._rejected(
                _v3("ch_001", "op2",
                    {"table": "persons", "action": "create",
                     "entry": {"id": "p_001", "name": "林牧", "type": "person",
                               "summary": "改了简介"}}),
                book=tb.book, needle="p_001")

    def test_create_replay_is_clean_skip(self):
        """同字节重放（崩溃重放）必须是干净 skip，既不得报错也不得重复合并。

        若无此预门，create 类提案崩溃重放会先撞「已存在」而永远到不了门。
        """
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进大殿。")
            op = {"table": "persons", "action": "create",
                  "entry": {"id": "p_001", "name": "林牧", "type": "person"}}
            tb_run_apply(tb, _v3("ch_001", "op1", op))
            from engine import state
            rep = state.apply_proposal(tb.book, _v3("ch_001", "op2", op), "ch_001")
            self.assertEqual(rep["errors"], [], rep["errors"])
            self.assertTrue(rep.get("duplicate"), rep)
            persons = tb.state("persons")["entries"]
            self.assertEqual(len(persons), 1, f"重放不应产生重复实体: {persons}")

    def test_update_nonexistent_id_rejected(self):
        """update 撞不存在的 id → 拒收（不静默新建）。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进大殿。")
            self._rejected(
                _v3("ch_001", "op1",
                    {"table": "items", "action": "update", "id": "it_999",
                     "set": {"charges": 1}}),
                book=tb.book, needle="it_999")

    def test_update_wrong_table_rejected(self):
        """表错位（拿 persons 的 id 去 items update）→ 拒收。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进大殿。")
            tb_run_apply(tb, _v3("ch_001", "op1",
                                 {"table": "persons", "action": "create",
                                  "entry": {"id": "p_001", "name": "林牧", "type": "person"}}))
            self._rejected(
                _v3("ch_001", "op2",
                    {"table": "items", "action": "update", "id": "p_001",
                     "set": {"charges": 1}}),
                book=tb.book, needle="p_001")

    def test_v3_and_v2_mixed_rejected(self):
        """同一文件禁止 v2 分区与 v3 ops 混写。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧走进大殿。")
            bad = _v3("ch_001", "op1", {"table": "current", "action": "update",
                                        "set": {"location": "临江城"}})
            bad["entities"] = []          # v2 分区键混入
            self._rejected(bad, book=tb.book)


# ---------------------------------------------------------------------------
# 四、事实探针（audit）——Drafter「放飞事实」时的机械兜底
# ---------------------------------------------------------------------------
class TestAuditProbes(unittest.TestCase):
    """这些用例同时是「Stage 2 之后跑 audit」这一建议的可行性依据。"""

    def _audit(self, tb, ch="ch_001"):
        from engine.audit import run_audit
        return run_audit(tb.book, ch)

    def test_deceased_on_stage_caught(self):
        """已故角色出场 → location_presence 硬矛盾。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "玄阳子站在殿中，朝林牧点头。")
            tb.set_state("persons", {"entries": [
                {"id": "p_002", "name": "玄阳子", "type": "person",
                 "life_status": "deceased"}]})
            r = self._audit(tb)
            self.assertGreater(r["hard_count"], 0, r)
            self.assertIn("location_presence",
                          [c["probe"] for c in r["candidates"]], r["candidates"])

    def test_exhausted_item_usage_caught(self):
        """充能耗尽的道具被使用 → charges_possession 硬矛盾。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "林牧掏出断水剑，一剑劈开石柱。")
            tb.set_state("items", {"entries": [
                {"id": "it_001", "name": "断水剑", "type": "item",
                 "holder": "林牧", "charges": 0, "max_charges": 3}]})
            r = self._audit(tb)
            self.assertIn("charges_possession",
                          [c["probe"] for c in r["candidates"]], r["candidates"])

    def test_deceased_speaks_caught(self):
        """已故角色发言 → locked_facts 硬矛盾。

        注意：探针有 `if n <= since_num: continue` 的守卫——死亡事实确立章
        及其之前不参与比对（当章正在写这场死亡）。故此处审计 ch_002。
        """
        with TempBook() as tb:
            tb.seed_chapter("ch_002", '玄阳子道："你来了。"')
            tb.set_state("persons", {"entries": [
                {"id": "p_002", "name": "玄阳子", "type": "person",
                 "life_status": "deceased"}]})
            tb.set_state("locked", {"schema_version": "novel-studio.locked/v1",
                                    "entries": [{"id": "LOCK-001", "fact": "玄阳子战死",
                                                 "kind": "death", "since_ch": "ch_001",
                                                 "quote": "倒在血泊中", "note": "严禁出场"}]})
            r = self._audit(tb, "ch_002")
            self.assertIn("locked_facts",
                          [c["probe"] for c in r["candidates"]], r["candidates"])

    # ------------------------------------------------------------------
    # 知情差：旁白 / 心理描写（原盲区，现已补上）
    # ------------------------------------------------------------------
    # 关键前提：旁白里的「他」无从归因，**只有本章视角角色能指名时才可判定**。
    # 群像/全知视角下旁白知情是合法的，指名不到必须放过——否则全是误报。
    _SECRET = {"id": "KNO-001", "secret": "水井下藏着三百两银子",
               "plant_ch": 1, "status": "Concealed", "weight": 2, "target_ch": 10}

    def _pov_book(self, tb, body, holders=("玄阳子",), pov_ref="p_001"):
        """铺一本「视角角色=林牧(p_001)、知情者=玄阳子(p_002)」的书。"""
        tb.seed_chapter("ch_001", body)
        tb.set_state("persons", {"entries": [
            {"id": "p_001", "name": "林牧", "type": "person"},
            {"id": "p_002", "name": "玄阳子", "type": "person"}]})
        if pov_ref:
            tb.set_state("current", {"pov_ref": pov_ref})
        tb.set_state("lines", {"foreshadows": [], "misunderstandings": [],
                               "knowledge": [{**self._SECRET, "holders": list(holders)}]})
        return self._audit(tb)

    def _secret_leaks(self, rep):
        return [c for c in rep["candidates"] if c["probe"] == "secret_leakage"]

    def test_narration_leak_by_unaware_pov_is_caught(self):
        """★ 原盲区：视角人物不知情，心理描写却把秘密当既定事实陈述。"""
        with TempBook() as tb:
            r = self._pov_book(tb, "他心里清楚，那笔藏在水井下的银子一共三百两。")
            hits = self._secret_leaks(r)
            self.assertEqual(len(hits), 1, f"旁白/心理描写泄密未抓到：{r['candidates']}")
            self.assertEqual(hits[0]["severity"], "candidate_soft")
            self.assertIn("林牧", hits[0]["title"])
            self.assertIn("心理描写", hits[0]["title"])

    def test_plain_narration_leak_is_caught(self):
        """不带内心标记的一般旁白同样在射程内（视角人物仍不知情）。"""
        with TempBook() as tb:
            r = self._pov_book(tb, "那口废井的井底压着三百两银子，水井边爬满青苔。")
            self.assertEqual(len(self._secret_leaks(r)), 1, r["candidates"])
            self.assertIn("旁白", self._secret_leaks(r)[0]["title"])

    def test_aware_pov_stays_silent(self):
        """视角人物本就在知情圈内 → 不得误报。"""
        with TempBook() as tb:
            r = self._pov_book(tb, "他心里清楚，那笔藏在水井下的银子一共三百两。",
                               pov_ref="p_002")
            self.assertEqual(self._secret_leaks(r), [], r["candidates"])

    def test_narration_without_pov_is_not_judged(self):
        """指名不到视角角色 → 无从归因，宁可不报（这是不误报的代价）。"""
        with TempBook() as tb:
            r = self._pov_book(tb, "他心里清楚，那笔藏在水井下的银子一共三百两。",
                               pov_ref=None)
            self.assertIsNone(r["pov"], "不该解析出视角角色")
            self.assertEqual(self._secret_leaks(r), [], r["candidates"])

    def test_omniscient_pov_mode_is_not_misread_as_character(self):
        """「群像切片 / 主角视角」是视角**模式**不是角色名，不得当成视角角色。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", "那口废井的井底，压着三百两银子。")
            tb.set_state("persons", {"entries": [
                {"id": "p_001", "name": "林牧", "type": "person"},
                {"id": "p_002", "name": "玄阳子", "type": "person"}]})
            tb.set_state("lines", {"foreshadows": [], "misunderstandings": [],
                                   "knowledge": [{**self._SECRET,
                                                  "holders": ["玄阳子"]}]})
            r = self._audit(tb)   # beats 的 pov 是模板默认的「主角视角」
            self.assertIsNone(r["pov"], "视角模式被误当成了角色名")
            self.assertEqual(self._secret_leaks(r), [], r["candidates"])

    def test_negated_narration_is_not_a_leak(self):
        """「他不知道 X」是反证，不是泄密——没有这道闸就是笑话。"""
        with TempBook() as tb:
            r = self._pov_book(tb, "他不知道水井下藏着三百两银子。")
            self.assertEqual(self._secret_leaks(r), [], r["candidates"])

    def test_beats_pov_name_is_resolved(self):
        """beats front-matter 写「林牧·视角」时也能解析出视角角色。"""
        with TempBook() as tb:
            tb.write("outlines/vol_01/beats/ch_001.md",
                     "---\nchapter: ch_001\nvol: vol_01\npov: 林牧·视角\n---\n")
            tb.set_state("persons", {"entries": [
                {"id": "p_001", "name": "林牧", "type": "person"},
                {"id": "p_002", "name": "玄阳子", "type": "person"}]})
            tb.set_state("lines", {"foreshadows": [], "misunderstandings": [],
                                   "knowledge": [{**self._SECRET,
                                                  "holders": ["玄阳子"]}]})
            tb.seed_chapter("ch_001", "他心里清楚，那笔藏在水井下的银子一共三百两。")
            # seed_chapter 会覆盖 beats，故在其之后再写一次（带视角角色名的版本）
            tb.write("outlines/vol_01/beats/ch_001.md",
                     "---\nchapter: ch_001\nvol: vol_01\npov: 林牧·视角\n---\n")
            r = self._audit(tb)
            self.assertEqual(r["pov"], "林牧", "beats 的 pov 未解析出角色")
            self.assertEqual(len(self._secret_leaks(r)), 1, r["candidates"])

    def test_dialogue_leak_still_caught(self):
        """原有对白射程不得被本次改动破坏。"""
        with TempBook() as tb:
            tb.seed_chapter("ch_001", '林牧道："水井下的银子，一共三百两。"')
            tb.set_state("persons", {"entries": [
                {"id": "p_001", "name": "林牧", "type": "person"},
                {"id": "p_002", "name": "玄阳子", "type": "person"}]})
            tb.set_state("lines", {"foreshadows": [], "misunderstandings": [],
                                   "knowledge": [{**self._SECRET,
                                                  "holders": ["玄阳子"]}]})
            r = self._audit(tb)
            hits = self._secret_leaks(r)
            self.assertEqual(len(hits), 1, r["candidates"])
            self.assertIn("道出", hits[0]["title"])


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def tb_run_apply(tb, prop, ch="ch_001"):
    """在 TempBook 上真实落盘一个提案，返回 rep。"""
    from engine import state
    rep = state.apply_proposal(tb.book, copy.deepcopy(prop), ch)
    assert not rep["errors"], rep["errors"]
    return rep


if __name__ == "__main__":
    unittest.main()
