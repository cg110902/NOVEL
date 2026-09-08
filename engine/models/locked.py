"""不可逆事实台账 (Locked Fact) 领域模型。

记录死亡、不可逆破坏、世界规则确立与不可撤销承诺。
全书活跃条目上限 15 条，经提案通道写入（唯一写入口不变），恒定注入 beats 脚手架与 pack P0。
"""
from __future__ import annotations

import re
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

LOCK_ID_RE = re.compile(r"^LOCK-\d{3,}$")
MAX_LOCKED_ENTRIES = 15

LockedKind = Literal[
    "death", "destruction", "disbandment", "irreversible_action", "rule", "promise", "pact"
]


class LockedEntry(BaseModel):
    """单条不可逆事实条目。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    id: str = Field(..., pattern=r"^LOCK-\d{3,}$", description="不可逆事实唯一ID (如 LOCK-001)")
    fact: str = Field(..., min_length=4, description="事实简明陈述")
    since_ch: str = Field(..., pattern=r"^ch_\d{3,}$", description="确立生效章号 (如 ch_003)")
    kind: LockedKind = Field(
        ..., description="不可逆类型：death (死亡) | irreversible_action (不可逆动作) | rule (规则规范) | promise (死契承诺)"
    )
    quote: str = Field(..., min_length=2, description="final 原文佐证句 (经 RapidFuzz 柔性接地)")
    note: Optional[str] = Field(None, description="写作红线执行提示 (如 '严禁再次出场，回忆除外')")


class LockedState(BaseModel):
    """不可逆事实台账表 (state/locked.json) 根模型。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default="novel-studio.locked/v1", alias="schema_version")
    entries: list[LockedEntry] = Field(default_factory=list, max_length=50)
