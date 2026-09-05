"""伏笔、知情差与误会暗线 (Lines) 强类型领域模型。"""
from __future__ import annotations
from enum import Enum
from typing import Annotated, Optional, Union, Literal
from pydantic import BaseModel, ConfigDict, Field


class ForeshadowStatus(str, Enum):
    PLANTED = "Planted"
    REMINDED = "Reminded"
    RESOLVED = "Resolved"


class MisunderstandingStatus(str, Enum):
    ACTIVE = "Active"
    ESCALATED = "Escalated"
    RESOLVED = "Resolved"


class KnowledgeStatus(str, Enum):
    CONCEALED = "Concealed"
    REVEALED = "Revealed"


class Foreshadow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    id: str = Field(..., pattern=r"^GUN-\d{3,}$", description="伏笔唯一编号")
    name: str = Field(..., description="伏笔名称/核心物件")
    plant_ch: int = Field(..., ge=1, description="埋设章节号")
    status: ForeshadowStatus = Field(default=ForeshadowStatus.PLANTED, description="伏笔状态")
    target_ch: Optional[Union[Annotated[int, Field(ge=1)], Literal["longline"]]] = Field(
        None, description="预定回收章号或长线")
    weight: int = Field(default=1, ge=1, description="权重分级")
    plan: Optional[str] = Field(None, description="预定回收方案")
    requires: list[str] = Field(default_factory=list, description="前置依赖线索ID列表，如 ['GUN-001']")


class Misunderstanding(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    id: str = Field(..., pattern=r"^MIS-\d{3,}$", description="误会认知差唯一编号")
    parties: str = Field(..., description="涉及主体角色，如'张彪与李玄'")
    content: str = Field(..., description="误会表面认知，如'张彪误判李玄隐忍多年'")
    truth: Optional[str] = Field(None, description="事实真相，如'实为刚刚觉醒金手指'")
    level: int = Field(default=1, ge=1, description="误会强度等级")
    target_ch: Optional[Union[Annotated[int, Field(ge=1)], Literal["longline"]]] = Field(
        None, description="预定澄清章号或长线")
    status: MisunderstandingStatus = Field(default=MisunderstandingStatus.ACTIVE, description="误会状态")
    requires: list[str] = Field(default_factory=list, description="前置依赖线索ID列表")


class Knowledge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    id: str = Field(..., pattern=r"^KNO-\d{3,}$", description="秘密/情报知情差编号")
    secret: str = Field(..., description="秘密事实内容")
    plant_ch: int = Field(..., ge=1, description="信息确立章节")
    status: KnowledgeStatus = Field(default=KnowledgeStatus.CONCEALED, description="信息保密状态")
    target_ch: Optional[Union[Annotated[int, Field(ge=1)], Literal["longline"]]] = Field(
        None, description="预定揭示章号")
    weight: int = Field(default=1, ge=1, description="重要度权重")
    note: Optional[str] = Field(None, description="谁不得知晓或揭示约束")
    requires: list[str] = Field(default_factory=list, description="前置依赖线索ID列表")


class LinesState(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    foreshadows: list[Foreshadow] = Field(default_factory=list, description="伏笔明暗线清单")
    misunderstandings: list[Misunderstanding] = Field(default_factory=list, description="误会认知差清单")
    knowledge: list[Knowledge] = Field(default_factory=list, description="核心秘密知情差清单")
