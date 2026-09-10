"""`state/inbox/README.md` ↔ 引擎真值的一致性回归。

**为什么需要这个文件**：`state/inbox/README.md`（由 `engine/state.py:INBOX_README`
生成，**72 行手写契约**）是 Stage 4 Reader 写提案时读的那份文档，里面手抄了几十条
业务规则：资源池三键、危机时钟五字段、target_ch 四种写法、引文阈值 85%/60%、
v3 每张表允许的动作……而这些规则**在代码里各有一份实现**。

两份真相，且此前**没有任何测试钉住它**——改了代码，README 不会红；改了 README，
代码也不会红。它自己就带着案底：文中「此前本文档写『提案校验期不拦这一条』，与实测相反」
一句，证明它**已经错过**。

本文件照 `tests/test_role_policy.py` 的路子，把可机械核验的契约逐条钉死：
  · 代码侧：跑真函数（compile_ops / Pydantic 枚举 / schema），取真值；
  · 文档侧：断言 README 里那段字面量还在（文档改了，本表必须同步更新）。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from engine import checks, state  # noqa: E402
from engine.models.entities import EntityStatus  # noqa: E402
from engine.proposal_v3 import compile_ops  # noqa: E402

SCHEMA_DIR = REPO_ROOT / "engine" / "schemas"


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _inbox_readme() -> str:
    """取 README 原文（同一份常量，写盘后就是 Agent 看到的那份）。"""
    text = state.INBOX_README
    assert isinstance(text, str) and len(text) > 2000, "INBOX_README 疑似被清空"
    return text


# v3「表 → 允许动作」，**按 README 里写的顺序**（代码报错文案也是这个顺序，
# 顺序一并钉死，防止有人重排后又说不清）。
V3_ACTIONS: dict[str, tuple[str, ...]] = {
    "persons": ("create", "update", "retire"),
    "items": ("create", "update", "retire"),
    "factions": ("create", "update", "retire"),
    "places": ("create", "update", "retire"),
    "current": ("update",),
    "timeline": ("append_event", "revise_event", "append_clock",
                 "append_arc", "append_milestone"),
    "locked": ("plant", "upsert", "retire"),
    "cognition": ("plant", "upsert", "retire"),
    "ledger": ("append_transaction", "declare_pool"),
    "synopsis": ("set",),
}

# lines 的报错文案不枚举动作，单独用「必须带 kind」钉。
LINES_KINDS = ("foreshadow", "misunderstanding", "knowledge")


def _compile_one(table: str, action: str) -> list[str]:
    proposal = {"schema": "novel-studio.state-mutation/v3", "chapter": "ch_001",
                "operation_id": "t", "ops": [{"table": table, "action": action}]}
    _, errors, _ = compile_ops(None, proposal)
    return errors


class TestInboxReadmeIsAlive(unittest.TestCase):
    """README 本身必须还在，且本测试表里的字面量必须还能在 README 里找到。"""

    def test_readme_carries_its_own_contract(self):
        text = _inbox_readme()
        for literal in ("entities.action 支持 upsert/register/retire",
                        "ledger.pools 资源池口径",
                        "timeline.clocks 危机时钟口径",
                        "v3 寻址式提案"):
            with self.subTest(literal=literal):
                self.assertIn(literal, text,
                              "INBOX_README 改了——请同步更新 tests/test_inbox_contract.py")

    def test_readme_is_written_to_disk_on_init(self):
        """README 不是只在内存里：init 出来的书必须真的有这份文件。"""
        from tests._fixtures import TempBook
        with TempBook() as tb:
            p = tb.book / "state" / "inbox" / "README.md"
            self.assertTrue(p.is_file(), "init 后 state/inbox/README.md 不存在")
            self.assertIn("资源池口径", p.read_text(encoding="utf-8"))


class TestV3ActionContract(unittest.TestCase):
    """v3 每张表允许的动作：README 写的 == compile_ops 报错里列的。"""

    def test_action_sets_match_readme(self):
        for table, actions in V3_ACTIONS.items():
            with self.subTest(table=table):
                errors = _compile_one(table, "__bogus__")
                self.assertTrue(errors, f"{table} 用了非法动作却没报错")
                joined = "/".join(actions)
                self.assertTrue(
                    any(joined in e for e in errors),
                    f"{table} 的合法动作集与 README 不符：README 写 `{joined}`，"
                    f"代码报错为 {errors}")

    def test_lines_op_requires_kind(self):
        errors = _compile_one("lines", "plant")
        self.assertTrue(any("kind" in e for e in errors),
                        "lines op 不校验 kind 了？README 写的是「lines op 须带 kind」")
        for kind in LINES_KINDS:
            with self.subTest(kind=kind):
                self.assertIn(kind, _inbox_readme(),
                              f"README 里找不到 lines 的 kind `{kind}`")


class TestFieldLevelContract(unittest.TestCase):
    """README 里手抄的字段级契约，逐条对真模型。"""

    def test_entity_status_only_active_retired(self):
        """README：「status 只许 active/retired」"""
        self.assertEqual({s.value for s in EntityStatus}, {"active", "retired"})
        self.assertIn("status 只许 active/retired", _inbox_readme())

    def test_crisis_clock_has_exactly_five_fields(self):
        """README：「合法字段仅五个……❌ 没有 id 字段，也没有 deadline_ch」"""
        clock = _schema("timeline")["properties"]["clocks"]["items"]
        self.assertEqual(set(clock["properties"]),
                         {"name", "target_ch", "urgency", "desc", "status"})
        self.assertFalse(clock["additionalProperties"], "时钟仍应拒绝未知字段")
        self.assertEqual(clock["properties"]["urgency"]["enum"],
                         ["low", "medium", "high", "critical"])
        self.assertEqual(clock["properties"]["status"]["enum"],
                         ["Active", "Triggered", "Defused", "Expired"])
        for banned in ("id", "deadline_ch"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, clock["properties"],
                                 f"时钟又长出 `{banned}` 了——README 明写没有这个字段")

    def test_ledger_pool_contract(self):
        """README：「池对象只接受 name/unit/initial 三键……严禁声明 current」"""
        pool = _schema("ledger")["properties"]["pools"]["additionalProperties"]
        props = set(pool["properties"])
        self.assertTrue({"name", "unit", "initial"} <= props)
        self.assertFalse(pool["additionalProperties"], "池仍应拒绝未知字段")
        self.assertIn("initial", pool["required"],
                      "README 明写「省略 initial 即整案拒收」")
        self.assertIn("严禁声明 \"current\"", _inbox_readme())

    def test_quote_grounding_ratios(self):
        """README：「相似度 ≥85% 视为命中；60~85% 提示『近似命中』」"""
        self.assertEqual(checks.QUOTE_PASS_RATIO, 85.0)
        self.assertEqual(checks.QUOTE_NEAR_RATIO, 60.0)
        self.assertIn("85", _inbox_readme())

    def test_target_ch_accepted_forms(self):
        """README：target_ch = int / ch_NNN / 第N章 / longline；"21" 与 ch_7 拒收。"""
        norm = state._norm_target
        for value, want in ((21, 21), ("ch_007", 7), ("第29章", 29), ("longline", "longline")):
            with self.subTest(value=value):
                got, err = norm(value)
                self.assertIsNone(err, f"{value!r} 应被接受：{err}")
                self.assertEqual(got, want)
        for bad in ("21", "ch_7", 0, -1, "第零章"):
            with self.subTest(bad=bad):
                _, err = norm(bad)
                self.assertIsNotNone(err, f"{bad!r} 应被拒收")


if __name__ == "__main__":
    unittest.main()
