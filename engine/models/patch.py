"""状态机提案与原子变更 (Proposal & Semantic Patch) 强类型模型。"""
from __future__ import annotations
from enum import Enum
from typing import Optional, Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from .entities import EntityType, EntityStatus, LifeStatus, FactionAttitude
from .current import CurrentState


class PatchOp(str, Enum):
    ADD = "add"
    REMOVE = "remove"
    MODIFY = "modify"
    UPSERT = "upsert"


class SemanticEntityPatch(BaseModel):
    """业务语义级原子补丁（避免 RFC 6902 数组数字下标在大模型端的漂移崩溃）。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    target_type: str = Field(..., description="实体类型：entity | line | pool | clock")
    target_id: str = Field(..., description="唯一业务 ID（如李玄、GUN-001、silver）")
    op: PatchOp = Field(default=PatchOp.MODIFY, description="操作类型")
    fields: dict[str, Any] = Field(default_factory=dict, description="需要原子变更的字段集合")
    evidence_quote: Optional[str] = Field(None, description="正文逐字引文支撑")


class EntityMutation(BaseModel):
    """提案中的单条实体变动（严格禁止未知键注入）。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    action: Literal["upsert", "register", "retire"] = Field(default="upsert", description="操作动作")
    name: str = Field(..., description="实体名称")
    type: Optional[EntityType] = Field(None, description="实体类别")
    summary: Optional[str] = Field(None, description="实体简介")
    aliases: list[str] = Field(default_factory=list, description="别名清单")
    card: Optional[str] = Field(None, description="对应人物卡路径")
    status: Optional[EntityStatus] = Field(None, description="状态")
    realm: Optional[str] = Field(None, description="境界/职级")
    faction: Optional[str] = Field(None, description="所属势力")
    life_status: Optional[LifeStatus] = Field(None, description="生命状态")
    attitude: Optional[FactionAttitude] = Field(None, description="政治立场")
    holder: Optional[str] = Field(None, description="道具持有者")
    location: Optional[str] = Field(None, description="道具所在地点")
    condition: Optional[str] = Field(None, description="道具完好状态")
    charges: Optional[int] = Field(None, ge=0, description="道具剩余充能")
    max_charges: Optional[int] = Field(None, ge=1, description="道具最大充能")
    dossier: Optional[str] = Field(None, description="恩怨羁绊备忘")
    quote: Optional[str] = Field(None, description="逐字支撑引文")


class ProposalModel(BaseModel):
    """对齐 novel-studio.state-mutation/v2 规范的强类型提案校验模型。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["novel-studio.state-mutation/v2"] = Field(
        default="novel-studio.state-mutation/v2", alias="schema"
    )
    chapter: str = Field(..., pattern=r"^ch_\d{3,}$")
    operation_id: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    draft: Optional[bool] = Field(None, alias="_draft")
    current: Optional[CurrentState] = None
    entities: Optional[list[EntityMutation]] = None
    lines: Optional[list[dict[str, Any]]] = None
    timeline: Optional[dict[str, Any]] = None
    ledger: Optional[dict[str, Any]] = None
    synopsis: Optional[dict[str, Any]] = None
