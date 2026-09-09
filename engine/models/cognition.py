"""角色认知台账 (Cognition Matrix) 强类型领域模型。

记录全书重要角色各自的动态认知边界：
- fact: 角色通过目击或确凿告知而掌握的客观事实
- suspicion: 角色所产生的怀疑或试探假设
- misunderstanding: 角色目前深信不疑的认知误区
- secret_known: 角色知晓的核心秘密 (与 lines.knowledge 协同)
用于从根本上切除大模型写作时的全知上帝视角与知情差穿帮。
"""
from __future__ import annotations

import re
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

COG_ID_RE = re.compile(r"^COG-\d{3,}$")

CognitionKind = Literal["fact", "suspicion", "misunderstanding", "secret_known"]


class CognitionEntry(BaseModel):
    """单条角色动态认知条目。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    id: str = Field(..., pattern=r"^COG-\d{3,}$", description="认知条目唯一编号 (如 COG-001)")
    character: str = Field(..., min_length=1, description="知情角色名")
    kind: CognitionKind = Field(default="fact", description="认知性质：fact (确凿获知) | suspicion (心生怀疑) | misunderstanding (误解) | secret_known (知晓机密)")
    content: str = Field(..., min_length=2, description="角色所知/所疑核心陈述")
    since_ch: str = Field(..., pattern=r"^ch_\d{3,}$", description="该认知建立或变迁的章节 (如 ch_002)")
    quote: str = Field(..., min_length=2, description="定稿逐字佐证原句")
    note: Optional[str] = Field(None, description="知情限制或机锋约束 (如 '仅怀疑，未掌握确凿铁证')")
    truth_ref: Optional[str] = Field(None, description="真相锚点（GUN-/KNO-/EVT-/LOCK-编号；供机械判定认知与真相是否冲突）")


class CognitionState(BaseModel):
    """角色认知台账表 (state/cognition.json) 根模型。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default="novel-studio.cognition/v1", alias="schema_version")
    entries: list[CognitionEntry] = Field(default_factory=list, description="角色认知条目清单")
