"""实体 (Entities) 强类型领域模型。"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class EntityType(str, Enum):
    PERSON = "person"
    ITEM = "item"
    PLACE = "place"
    FACTION = "faction"
    OTHER = "other"


class EntityStatus(str, Enum):
    ACTIVE = "active"
    RETIRED = "retired"


class LifeStatus(str, Enum):
    ALIVE = "alive"
    DECEASED = "deceased"
    MISSING = "missing"


class FactionAttitude(str, Enum):
    HOSTILE = "hostile"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    ALLIED = "allied"


class EntityEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(..., description="实体唯一名称")
    type: Optional[EntityType] = Field(None, description="实体类别")
    aliases: list[str] = Field(default_factory=list, description="别名列表")
    card: Optional[str] = Field(None, description="对应人物卡路径，如 protagonist.md")
    summary: Optional[str] = Field(None, description="一句话实体简介")
    status: Optional[EntityStatus] = Field(None, description="活跃/退场状态")
    realm: Optional[str] = Field(None, description="人物境界/阶位/社会职务")
    faction: Optional[str] = Field(None, description="人物所属势力组织名")
    life_status: Optional[LifeStatus] = Field(None, description="生命状态")
    attitude: Optional[FactionAttitude] = Field(None, description="势力政治阵营立场")
    holder: Optional[str] = Field(None, description="道具当前持有者名")
    location: Optional[str] = Field(None, description="道具当前所在地点")
    condition: Optional[str] = Field(None, description="道具当前完损状态")
    charges: Optional[int] = Field(None, ge=0, description="道具剩余使用次数/充能")
    max_charges: Optional[int] = Field(None, ge=1, description="道具最大使用次数/上限")
    dossier: Optional[str] = Field(None, description="恩怨羁绊、历史过节与交互备忘")


class EntitiesState(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    entries: list[EntityEntry] = Field(default_factory=list, description="全书注册实体清单")
