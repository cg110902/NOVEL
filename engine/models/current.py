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


class MoodEntry(BaseModel):
    """单角色章末情绪快照（隐含情绪：角色真实内在状态，可与表面言行不一致）。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    label: str = Field(..., min_length=1, description="情绪词（如 暴怒/隐忍/惊惧；advisory 非穷举，不做语义立法）")
    level: Optional[int] = Field(None, ge=1, le=5, description="烈度 1~5（1=微澜，5=失控边缘；缺省=未评级）")
    quote: Optional[str] = Field(None, description="final 原文佐证（情绪落笔句，经柔性接地）")


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
    # 对象化扩展（v2 加法字段：scene 引用化——字符串保留兼容，引用供精确装配）
    time_day: Optional[int] = Field(None, ge=1, description="故事日计数（第N日；time 自由文本的数值孪生）")
    pov_ref: Optional[str] = Field(None, description="视角角色对象引用（实体 id 如 p_001，或法定名）")
    place_ref: Optional[str] = Field(None, description="当前地点对象引用（实体 id 如 loc_012，或法定名）")
    present_refs: list[str] = Field(default_factory=list, description="在场角色对象引用清单（实体 id 或法定名，与 present_characters 并存）")
    # 出厂情绪快照（章效状态：只记章末一拍，历史演进走 changelog 回放；缺席=本章无特殊情绪交代）
    present_moods: dict[str, MoodEntry] = Field(default_factory=dict, description="在场角色隐含情绪快照 {角色名: {label, level?, quote?}}")
