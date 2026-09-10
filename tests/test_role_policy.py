"""SKILL 准读清单 ↔ pack 角色网关 的一致性回归。

**为什么需要这个文件**：`.agents/skills/*/SKILL.md` 的「准读清单」是给 Agent 看的
**规格**，`engine/pack.py` 的 `ROLE_DENY` / `ROLE_ALLOW_EXTRA` 是**实现**。两者一旦
分叉，Agent 严格照文档执行就会吃到 `PermissionError`——而这类分叉**没有任何其他测试
能发现**：网关自身的单测是拿 ROLE_DENY 当基准自证的，文档改了不会红。

已发现过的实例：
  · editor 准读清单曾列 `bible/06_style_guidelines.md`，网关却一律拒 `bible/`
    （已由 ROLE_ALLOW_EXTRA 修补，见 pack.py 注释）；
  · **同批漏掉的第 4 项 `characters/<在场角色>.md`**：文档授权、网关禁读
    `characters/`，且 SKILL §三.1 的 SOP 本身写的是「对照 beats 的称谓基准」——
    即三处口径里两处（网关 + SOP）一致，只有准读清单是过期的。已按「文档错」修正。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from engine.pack import ROLE_ALLOW_EXTRA, ROLE_DENY, deny_reason  # noqa: E402

SKILL_DIR = REPO_ROOT / ".agents" / "skills"

# 角色 → {SKILL 里写明的路径字面量: 实例化后的路径}
# 两条断言各看一边：字面量必须在 SKILL 里还在（文档漂移会红），
# 实例化路径必须被网关放行（网关收紧会红）。
DOC_READ_LIST: dict[str, dict[str, str]] = {
    "editor": {
        "outlines/vol_XX/beats/ch_XXX.md": "outlines/vol_01/beats/ch_001.md",
        "manuscript/vol_XX/raw/ch_XXX_v1.md": "manuscript/vol_01/raw/ch_001_v1.md",
        "bible/06_style_guidelines.md": "bible/06_style_guidelines.md",
    },
    "stylist": {
        "outlines/vol_XX/beats/ch_XXX.md": "outlines/vol_01/beats/ch_001.md",
        "manuscript/vol_XX/raw/ch_XXX_v2.md": "manuscript/vol_01/raw/ch_001_v2.md",
        "bible/06_style_guidelines.md": "bible/06_style_guidelines.md",
    },
    "auditor": {
        "manuscript/vol_XX/final/ch_XXX.md": "manuscript/vol_01/final/ch_001.md",
        "outlines/vol_XX/beats/ch_XXX.md": "outlines/vol_01/beats/ch_001.md",
        "state/locked.json": "state/locked.json",
        "state/current.json": "state/current.json",
        "state/persons.json": "state/persons.json",
        "state/items.json": "state/items.json",
        "state/factions.json": "state/factions.json",
        "state/places.json": "state/places.json",
    },
    "reader": {
        "manuscript/vol_XX/final/ch_XXX.md": "manuscript/vol_01/final/ch_001.md",
        "outlines/vol_XX/beats/ch_XXX.md": "outlines/vol_01/beats/ch_001.md",
        "state/persons.json": "state/persons.json",
        "state/items.json": "state/items.json",
        "state/factions.json": "state/factions.json",
        "state/places.json": "state/places.json",
    },
    "critic": {
        "manuscript/vol_XX/final/ch_XXX.md": "manuscript/vol_01/final/ch_001.md",
        "state/current.json": "state/current.json",
    },
    "librarian": {
        "manuscript/vol_XX/final/ch_{N-9..N}.md": "manuscript/vol_01/final/ch_010.md",
        "state/persons.json": "state/persons.json",
        "state/items.json": "state/items.json",
        "state/factions.json": "state/factions.json",
        "state/places.json": "state/places.json",
        "state/lines.json": "state/lines.json",
        "state/locked.json": "state/locked.json",
        "state/ledger.json": "state/ledger.json",
    },
}


class TestSkillReadListMatchesGateway(unittest.TestCase):
    """文档授权的路径，网关必须放行；文档没写的，网关必须拒绝。"""

    def _skill_text(self, role: str) -> str:
        p = SKILL_DIR / role / "SKILL.md"
        self.assertTrue(p.is_file(), f"缺少 .agents/skills/{role}/SKILL.md")
        return p.read_text(encoding="utf-8")

    def test_every_documented_path_is_allowed_by_gateway(self):
        """Agent 照文档执行不能吃 PermissionError。"""
        for role, paths in DOC_READ_LIST.items():
            for literal, instantiated in paths.items():
                with self.subTest(role=role, path=instantiated):
                    reason = deny_reason(Path("/tmp/whatever"), instantiated, role)
                    self.assertIsNone(
                        reason,
                        f"{role} 的准读清单写了 `{literal}`，但网关拒绝：{reason}\n"
                        f"→ 要么在 pack.ROLE_ALLOW_EXTRA 补白名单，要么修 SKILL 文档。")

    def test_skill_still_documents_these_paths(self):
        """反向：本表的字面量必须在 SKILL 里真的还在，否则这张表本身就过期了。"""
        for role, paths in DOC_READ_LIST.items():
            text = self._skill_text(role)
            for literal in paths:
                with self.subTest(role=role, literal=literal):
                    self.assertIn(literal, text,
                                  f"{role}/SKILL.md 里找不到 `{literal}`——"
                                  f"文档已改，请同步更新本测试的路径表。")

    def test_editor_skill_does_not_promise_character_cards(self):
        """editor 曾被授权读角色卡，但网关禁读 characters/，且 SOP 用的是 beats。

        这条锁定三条口径必须一致：网关（禁 characters/）+ 准读清单（不列角色卡）
        + SOP（称谓以 beats 为准）。任何一侧回退都会红。
        """
        text = self._skill_text("editor")
        self.assertIn("characters/", ROLE_DENY["editor"],
                      "网关不再禁读 characters/ 了？那准读清单与 SOP 要一起复核")
        # 准读清单里不得再出现 characters/ 的准读项
        allow_block = text.split("🟢 **准读清单")[1].split("🔴 **禁读清单")[0]
        self.assertNotIn("characters/", allow_block,
                         "editor 准读清单又把角色卡列为准读了——网关会拒收")
        # SOP 必须仍然指向 beats 的称谓对校清单
        self.assertIn("现场在场角色动态称谓基准", text,
                      "editor SOP 不再以 beats 的称谓基准为准？那称谓对账就没源头了")

    def test_whitelist_entries_are_still_exact_paths(self):
        """ROLE_ALLOW_EXTRA 必须是精确路径——前缀匹配会让 `x.json.bak` 也放行。"""
        for role, allowed in ROLE_ALLOW_EXTRA.items():
            for a in allowed:
                with self.subTest(role=role, path=a):
                    self.assertFalse(a.endswith("/"),
                                     f"{role} 的白名单项 `{a}` 是目录前缀，应写精确文件路径")


if __name__ == "__main__":
    unittest.main()
