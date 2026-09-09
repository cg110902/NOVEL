"""派生计算层 (Derived) 强类型领域模型。

定位：`state/derived.json` —— 全书唯一由引擎计算、不由任何人断言的状态表。
- 唯一写者：引擎（sync 封存时自动 seal + `state recompute` 手动重算）；
- 提案/手术刀禁止写入（validate_proposal 拒收 `derived` 分区）；
- 内容 = 纯函数 f(十一表真值 + final 正文)，随时可删、可重算；
- 快照/回滚/changelog 对它一视同仁（ Pluto 在 STATE_KEYS 内），但 check 的
  state_offline_edit 档跳过它（缓存语义：重算即合法变更）。
"""
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class LineTemp(BaseModel):
    """单条线的读者记忆温度（派生自正文落笔史 + 权重）。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    id: str = Field(..., description="线索编号（GUN-/MIS-/KNO-）")
    kind: str = Field(..., description="foreshadow | misunderstanding | knowledge")
    temp: Literal["hot", "warm", "cold", "never", "closed"] = Field(..., description="记忆温度档（closed=已闭环，仅快照）")
    last_seen_ch: Optional[int] = Field(None, description="正文最后一次落笔章号（无则 None）")
    gap: Optional[int] = Field(None, description="距今章距（无则 None）")
    status: Optional[str] = Field(None, description="封存时刻的线状态快照")


class SceneViolation(BaseModel):
    """场景合法性 violation（派生自 scene 引用 × 实体生死/注册表）。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    code: str = Field(..., description="present_unregistered | present_deceased | ref_unresolved | present_refs_mismatch")
    level: Literal["error", "warning"] = Field(..., description="error=硬伤 | warning=待核对")
    msg: str = Field(..., description="人话描述")
    refs: list[str] = Field(default_factory=list, description="涉事引用")


class HolderOrphan(BaseModel):
    """持有悬空（派生自 holder × 实体注册/生死）。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    item: str = Field(..., description="道具名")
    holder: str = Field(..., description="悬空的 holder 值")
    reason: str = Field(..., description="unregistered | deceased")


class KnowledgeFlag(BaseModel):
    """认知-真相挂载旗（派生自 beliefs.truth_ref × 线/事件/锁状态）。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    cog_id: str = Field(..., description="COG-编号")
    character: str = Field(..., description="认知主体")
    truth_ref: str = Field(..., description="真相锚点")
    verdict: Literal["aligned", "contradicted", "unresolved"] = Field(..., description="aligned 一致 | contradicted 冲突 | unresolved 锚点不存在")
    detail: str = Field(..., description="判定依据一句话")


class DerivedState(BaseModel):
    """派生表根模型（state/derived.json）。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(default="novel-studio.derived/v1", alias="schema_version")
    sealed_ch: str = Field(default="", description="封存章号（ch_XXX；空=尚未封存过）")
    sealed_at: str = Field(default="", description="封存时刻 ISO（仅审计用，不参与一致性比对）")
    line_temps: list[LineTemp] = Field(default_factory=list, description="全线记忆温度")
    scene_violations: list[SceneViolation] = Field(default_factory=list, description="场景合法性 violation（空=干净）")
    holder_orphans: list[HolderOrphan] = Field(default_factory=list, description="持有悬空清单（空=干净）")
    knowledge_flags: list[KnowledgeFlag] = Field(default_factory=list, description="认知-真相挂载旗")
    stats: dict[str, int] = Field(default_factory=dict, description="派生统计（实体数/线数/事件数等，供 cockpit 问书速查）")
