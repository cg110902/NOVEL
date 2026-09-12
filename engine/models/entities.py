"""实体 (Entities) 强类型领域模型。"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EntityType(str, Enum):
    PERSON = "person"
    ITEM = "item"
    PLACE = "place"
    LOCATION = "location"
    FACTION = "faction"
    OTHER = "other"


# 地点类实体（唯一真源）：`place` 与 `location` 在语义上同为「地点」，
# 但历史上 graph/pack 只认 "place" → 写成 location 的地点既不上图也不被注入。
# 任何「这是不是地点」的判定都必须走这个集合，禁止再手写字面量。
LOCATION_TYPES: frozenset[str] = frozenset({EntityType.PLACE.value, EntityType.LOCATION.value})


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


class EntityRelation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    target: str = Field(..., description="目标实体名称")
    type: str = Field(..., description="张力关系类型，如 debt, rival, ally, subordinate, distrust 等")
    desc: Optional[str] = Field(None, description="张力细节说明")
    strength: Optional[int] = Field(None, ge=1, le=5, description="关系强度 1~5（1=泛泛之交/小过节，5=生死与共/不共戴天）")
    status: Optional[str] = Field(None, pattern=r"^(active|resolved)$", description="关系状态：active 存续 | resolved 已了结")
    since_ch: Optional[str] = Field(None, pattern=r"^ch_\d{3,}$", description="关系确立章节（如 ch_007）")


# 已知关系谓词表（advisory 非穷举）：命中则静默通过，未命中仅出提示、不拒收——
# 关系语义开放（测试即有用中文"宿敌"的先例），引擎只做拼写引导，不做语义立法。
KNOWN_RELATION_PREDS: frozenset[str] = frozenset({
    # 英文程序侧
    "ally", "rival", "enemy", "friend", "debt", "subordinate", "distrust",
    "lover", "kin", "master", "apprentice", "creditor", "colleague", "leader",
    # 中文写作侧
    "盟友", "宿敌", "仇敌", "朋友", "师徒", "主仆", "道侣", "亲人", "同门",
    "上下级", "债主", "对手", "知己", "救命恩人",
})


class EntityEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    id: Optional[str] = Field(None, pattern=r"^[a-zA-Z0-9_#-]+$", description="实体全局稳定唯一业务主键编号，如 p_001, it_001, fac_001, loc_001")
    name: str = Field(..., description="实体唯一名称")
    type: Optional[EntityType] = Field(None, description="实体类别")
    aliases: list[str] = Field(default_factory=list, description="别名列表")
    card: Optional[str] = Field(None, description="对应卡片路径，如 characters/protagonist.md")
    summary: Optional[str] = Field(None, description="一句话实体简介")
    status: Optional[EntityStatus] = Field(None, description="活跃/退场状态")

    # 实力与层级标尺（全题材通用）- 区间由 checks 层 entity_tier_invalid 守卫（1-12），
    # 模型层不设 ge/le 以便该检查码可达（此前模型层直接拒收，导致该码为死码）。
    tier_rank: Optional[int] = Field(None, description="标准化实力/阶层档位(1-12数字标尺，便于跨题材比大小)")
    tier_name: Optional[str] = Field(None, description="阶层全称（如：辟海境后期 / S级战略异能者 / 集团执行总裁）")
    power_benchmark: Optional[str] = Field(None, description="破坏力/表现力物理实物标尺（如：单手掷出万斤巨石，剑气裂百米悬崖）")
    realm: Optional[str] = Field(None, description="人物境界/阶位/社会职务（兼容旧版字段）")

    # 记忆物象与微动作
    sensory_anchor: Optional[str] = Field(None, description="感官外貌/标志性穿戴/物象记忆点")
    micro_actions: list[str] = Field(default_factory=list, description="习惯微动作与神态库")

    # 闭环称谓矩阵（全书恒定防吃书）
    address_matrix: dict[str, str] = Field(default_factory=dict, description="对特定实体的法定锁定称谓映射 {目标名: 我称呼对方}")

    # 人物与生命状态
    role: Optional[str] = Field(None, description="角色叙事角色定位（如 protagonist / deuteragonist / antagonist / mentor / ally 等）")
    faction: Optional[str] = Field(None, description="人物所属势力组织名")
    life_status: Optional[LifeStatus] = Field(None, description="生命状态")
    attitude: Optional[FactionAttitude] = Field(None, description="势力政治阵营立场")

    # 资产与道具专属字段
    holder: Optional[str] = Field(None, description="道具当前持有者名")
    location: Optional[str] = Field(None, description="道具当前所在地点")
    condition: Optional[str] = Field(None, description="道具当前完损状态")
    charges: Optional[int] = Field(None, ge=0, description="道具剩余使用次数/充能")
    max_charges: Optional[int] = Field(None, ge=1, description="道具最大使用次数/上限")
    cost_per_use: Optional[str] = Field(None, description="道具单次催动代价/消耗")
    durability: Optional[str] = Field(None, description="道具耐久/材质物象")

    # 势力专属字段
    scale_tier: Optional[int] = Field(None, ge=1, le=10, description="势力规模等级(1-10)")
    core_assets: list[str] = Field(default_factory=list, description="势力核心垄断资产与王牌")
    diplomacy: dict[str, str] = Field(default_factory=dict, description="势力外交拓扑 {势力名: 态度}；态度词表同 FactionAttitude 枚举 (hostile/neutral/friendly/allied)，但本字段是自由字符串字典、引擎不校验取值")
    leader: Optional[str] = Field(None, description="最高掌权领袖角色名")
    headquarters: Optional[str] = Field(None, description="总部据点/山门祖庭地名")

    # 地标/场景专属字段
    danger_tier: Optional[int] = Field(None, ge=1, le=10, description="地点危险度(1-10)")
    danger_level: Optional[str] = Field(None, description="危险评级文字说明（如安全腹地/争端前线/绝地死境）")
    environment_rules: list[str] = Field(default_factory=list, description="地点特殊环境律则")

    # 叙事元数据
    dossier: Optional[str] = Field(None, description="恩怨羁绊、历史过节与交互备忘")
    scope: Optional[str] = Field(None, description="所属分卷生命周期（如 vol_01；省略表示全书通用）")
    golden_quote: Optional[str] = Field(None, description="首次高光定稿切片（100~200字物象细节）")
    relations: list[EntityRelation] = Field(default_factory=list, description="与特定角色的动态张力关系")

    # 对象化扩展（v2 加法字段：读者在意的可算属性）
    injury_level: Optional[int] = Field(None, ge=0, le=5, description="伤势等级 0~5（0=无伤，5=濒死；人物专用）")
    injury_desc: Optional[str] = Field(None, description="伤势文字说明（如\"左臂骨折\"，与 injury_level 同写）")
    renown: Optional[int] = Field(None, description="声望/悬赏值（人物/势力；正负皆可，正=美名，负=恶名/悬赏）")


class EntitiesState(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    entries: list[EntityEntry] = Field(default_factory=list, description="全书注册实体清单")

    @model_validator(mode="after")
    def check_unique_ids(self) -> EntitiesState:
        ids = [e.id for e in self.entries if e.id]
        if len(ids) != len(set(ids)):
            from collections import Counter
            dups = [k for k, v in Counter(ids).items() if v > 1]
            raise ValueError(f"存在重复的实体 ID: {', '.join(dups)}")
        return self
