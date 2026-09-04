"""当前场景速写 (Current) 强类型领域模型。"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class Loadout(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    cultivation: Optional[str] = Field(None, description="主修功法/核心能量体系")
    movement: Optional[str] = Field(None, description="身法/步法/机动手段")
    attack: Optional[str] = Field(None, description="招牌杀招/主战攻击手段")
    trump_card: Optional[str] = Field(None, description="绝境保命底牌")
    equipped_items: list[str] = Field(default_factory=list, description="常驻佩戴/激活法宝道具")


class CurrentState(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    time: Optional[str] = Field(None, description="此刻时间")
    region: Optional[str] = Field(None, description="宏观疆域/大地图区域")
    location: Optional[str] = Field(None, description="此刻具体地点/场景")
    power_level: Optional[str] = Field(None, description="能力/修为阶位")
    abilities: Optional[str] = Field(None, description="可用技能清单")
    injury: Optional[str] = Field(None, description="当前伤势")
    equipment: Optional[str] = Field(None, description="随身装备")
    assets: Optional[str] = Field(None, description="非资金类资源")
    situation: Optional[str] = Field(None, description="一句话处境速写")
    mood: Optional[str] = Field(None, description="POV 情绪基调")
    goal: Optional[str] = Field(None, description="POV 当下目标")
    key_relationships: Optional[str] = Field(None, description="当前核心关系速写")
    present_characters: list[str] = Field(default_factory=list, description="章末在场角色名单")
    loadout: Optional[Loadout] = Field(None, description="主角常驻作战体系")
    aftershock: Optional[str] = Field(None, description="上章戏剧余震与未平残局（下章开篇必接动作）")
    active_pressures: list[str] = Field(default_factory=list, description="当前悬在主角头上的核心危机与倒计时")
