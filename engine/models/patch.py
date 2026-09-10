"""状态机提案与原子变更 (Proposal & Semantic Patch) 强类型模型。"""
from __future__ import annotations
from enum import Enum
from typing import Optional, Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from .entities import EntityType, EntityStatus, LifeStatus, FactionAttitude, EntityRelation
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
    id: Optional[str] = Field(None, pattern=r"^[a-zA-Z0-9_#-]+$", description="实体全局稳定唯一业务主键编号")
    name: str = Field(..., description="实体名称")
    type: Optional[EntityType] = Field(None, description="实体类别")
    summary: Optional[str] = Field(None, description="实体简介")
    aliases: list[str] = Field(default_factory=list, description="别名清单")
    card: Optional[str] = Field(None, description="对应卡片路径")
    status: Optional[EntityStatus] = Field(None, description="状态")

    # 实力与层级标尺（全题材通用）
    tier_rank: Optional[int] = Field(None, ge=1, le=12, description="标准化实力/阶层档位(1-12)")
    tier_name: Optional[str] = Field(None, description="阶层全称")
    power_benchmark: Optional[str] = Field(None, description="破坏力/表现力物理实物标尺")
    realm: Optional[str] = Field(None, description="境界/职级（兼容旧版字段）")

    # 记忆物象与微动作
    sensory_anchor: Optional[str] = Field(None, description="感官外貌/标志性穿戴/物象记忆点")
    micro_actions: list[str] = Field(default_factory=list, description="习惯微动作与神态库")

    # 闭环称谓矩阵（全书恒定防吃书）
    address_matrix: dict[str, str] = Field(default_factory=dict, description="对特定实体的法定锁定称谓映射 {目标名: 我称呼对方}")

    # 人物与生命状态
    faction: Optional[str] = Field(None, description="所属势力")
    life_status: Optional[LifeStatus] = Field(None, description="生命状态")
    attitude: Optional[FactionAttitude] = Field(None, description="政治立场")

    # 资产与道具专属字段
    holder: Optional[str] = Field(None, description="道具持有者")
    location: Optional[str] = Field(None, description="道具所在地点")
    condition: Optional[str] = Field(None, description="道具完好状态")
    charges: Optional[int] = Field(None, ge=0, description="道具剩余充能")
    max_charges: Optional[int] = Field(None, ge=1, description="道具最大充能")
    cost_per_use: Optional[str] = Field(None, description="道具单次催动代价/消耗")
    durability: Optional[str] = Field(None, description="道具耐久/材质物象")

    # 势力专属字段
    scale_tier: Optional[int] = Field(None, ge=1, le=10, description="势力规模等级(1-10)")
    core_assets: list[str] = Field(default_factory=list, description="势力核心垄断资产与王牌")
    diplomacy: dict[str, str] = Field(default_factory=dict, description="势力外交拓扑 {势力名: 态度}；态度词表同 FactionAttitude 枚举 (hostile/neutral/friendly/allied)，但本字段是自由字符串字典、引擎不校验取值")

    # 地标/场景专属字段
    danger_tier: Optional[int] = Field(None, ge=1, le=10, description="地点危险度(1-10)")
    environment_rules: list[str] = Field(default_factory=list, description="地点特殊环境律则")

    # 叙事元数据
    dossier: Optional[str] = Field(None, description="恩怨羁绊备忘")
    scope: Optional[str] = Field(None, description="所属分卷生命周期（如 vol_01；省略表示全书通用）")
    golden_quote: Optional[str] = Field(None, description="首次高光定稿切片（100~200字物象细节）")
    relations: list[EntityRelation] = Field(default_factory=list, description="与特定角色的动态张力关系")
    quote: Optional[str] = Field(None, description="逐字支撑引文")

    # 对象化扩展（v2 加法字段，与 EntityEntry 同口径；提案可写）
    injury_level: Optional[int] = Field(None, ge=0, le=5, description="伤势等级 0~5（0=无伤，5=濒死；人物专用）")
    injury_desc: Optional[str] = Field(None, description="伤势文字说明")
    renown: Optional[int] = Field(None, description="声望/悬赏值（人物/势力）")


class ProposalModel(BaseModel):
    """对齐 novel-studio.state-mutation/v2 规范的强类型提案校验模型。

    与 schema 闸门对齐：
    - `schema` 键必填（信封契约，不给默认值）；
    - 仅认 `_draft`（populate_by_name=False，裸 `draft` 键按未知字段拒绝）。
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    schema_version: Literal["novel-studio.state-mutation/v2"] = Field(..., alias="schema")
    chapter: str = Field(..., pattern=r"^ch_\d{3,}$")
    operation_id: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    draft: Optional[bool] = Field(None, alias="_draft")
    current: Optional[CurrentState] = None
    entities: Optional[list[EntityMutation]] = None
    lines: Optional[list[dict[str, Any]]] = None
    timeline: Optional[dict[str, Any]] = None
    ledger: Optional[dict[str, Any]] = None
    synopsis: Optional[dict[str, Any]] = None
    locked: Optional[list[dict[str, Any]]] = None
    locked_candidates: Optional[list[dict[str, Any]]] = None
    cognition: Optional[list[dict[str, Any]]] = None
    cognition_delta: Optional[list[dict[str, Any]]] = None
    consequences: Optional[list[dict[str, Any]]] = None


# —— v3 寻址式提案：与 state.ASSERTED_KEYS 同步（刻意重复：models 层禁止导入
# state 防循环 ——
V3_TABLES = ("current", "persons", "items", "factions", "places", "lines",
             "timeline", "ledger", "synopsis", "locked", "cognition")


class V3OpModel(BaseModel):
    """单个寻址 op 的信封。载荷键按表区分、直通 v2（extra=allow）：

    深层规则（存在性/表一致性/字段合法性）归编译器（proposal_v3.compile_ops）
    与 v2 管线管——模型只钉信封形状，与 v2「浅层信封原则」同构。
    """
    model_config = ConfigDict(extra="allow")

    table: Literal["current", "persons", "items", "factions", "places", "lines",
                   "timeline", "ledger", "synopsis", "locked", "cognition"]
    action: str
    id: Optional[str] = None
    entry: Optional[dict[str, Any]] = None
    set: Optional[dict[str, Any]] = Field(None, alias="set")
    kind: Optional[str] = None
    event: Optional[dict[str, Any]] = None
    clock: Optional[dict[str, Any]] = None
    arc: Optional[dict[str, Any]] = None
    milestone: Optional[dict[str, Any]] = None
    pool: Optional[str] = None
    spec: Optional[dict[str, Any]] = None


class ProposalV3Model(BaseModel):
    """v3 提案信封：ops-only。v2 分区键一律按未知字段拒绝（extra=forbid），
    与编译器的「禁止混写」检查同义（分层门：结构先行，结构坏则编译不跑）。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=False)

    schema_version: Literal["novel-studio.state-mutation/v3"] = Field(..., alias="schema")
    chapter: str = Field(..., pattern=r"^ch_\d{3,}$")
    operation_id: Optional[str] = Field(None, pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    draft: Optional[bool] = Field(None, alias="_draft")
    ops: list[V3OpModel] = Field(..., min_length=1)
