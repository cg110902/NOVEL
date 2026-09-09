"""时空事件轴与危机倒计时 (Timeline) 强类型领域模型。"""
from __future__ import annotations
import re
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, Field

EVT_ID_RE = re.compile(r"^EVT-\d{3,}$")


class ClockUrgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ClockStatus(str, Enum):
    ACTIVE = "Active"
    TRIGGERED = "Triggered"
    DEFUSED = "Defused"
    EXPIRED = "Expired"


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    time: str = Field(..., description="绝对/相对时间点，如'第一日·正午'")
    event: str = Field(..., description="发生的重大事件事实记录")
    chapter: Optional[str] = Field(None, description="事件发生章节")
    # 对象化扩展（v2 加法字段：事件成为可引用的 Object）
    id: Optional[str] = Field(None, pattern=r"^EVT-\d{3,}$", description="事件唯一编号（如 EVT-001；缺省由引擎自动分配）")
    participants: list[str] = Field(default_factory=list, description="参与实体引用（实体 id 或法定名）")
    place: Optional[str] = Field(None, description="发生地点引用（实体 id 或法定名）")
    causes: list[str] = Field(default_factory=list, description="前因事件引用（EVT-编号）")
    consequences: list[str] = Field(default_factory=list, description="后果事件引用（EVT-编号）")


class TimelineClock(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(..., description="时钟名称，如'宗门大比'、'毒发倒计时'")
    target_ch: int = Field(..., ge=1, description="目标爆发/结算章号")
    urgency: Optional[ClockUrgency] = Field(None, description="紧迫等级")
    desc: Optional[str] = Field(None, description="危机内容与超时后果简述")
    status: ClockStatus = Field(default=ClockStatus.ACTIVE, description="时钟状态")


class ArcStrategyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    chapter: str = Field(...)
    strategy: str = Field(...)


class TimelineArc(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(..., description="大弧名称")
    baseline: Optional[str] = Field(None)
    stage: Optional[str] = Field(None)
    inciting_event: Optional[str] = Field(None)
    strategy: Optional[str] = Field(None)
    ultimate: Optional[str] = Field(None)
    strategy_history: list[ArcStrategyEntry] = Field(default_factory=list)


class TimelineMilestone(BaseModel):
    """主线里程碑航标（四分位宏观锚点与阶段目标）。"""
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    id: str = Field(..., pattern=r"^MS-\d{3,}$", description="里程碑编号 (如 MS-001)")
    title: str = Field(..., min_length=2, description="里程碑标题 (如 '突破筑基期', '揭开身世第一重')")
    target_ch: int = Field(..., ge=1, description="预定达成章节")
    status: Literal["pending", "achieved", "abandoned"] = Field(default="pending", description="状态")
    desc: Optional[str] = Field(None, description="里程碑意义与达成标准")
    achieved_ch: Optional[str] = Field(None, description="实际达成章节 (如 ch_012)")


class TimelineState(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    events: list[TimelineEvent] = Field(default_factory=list, description="时空大事记")
    arcs: list[TimelineArc] = Field(default_factory=list, description="叙事大弧与战略走向")
    clocks: list[TimelineClock] = Field(default_factory=list, description="危机倒计时时钟")
    milestones: list[TimelineMilestone] = Field(default_factory=list, description="主线阶段里程碑航标")
