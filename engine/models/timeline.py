"""时空事件轴与危机倒计时 (Timeline) 强类型领域模型。"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


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


class TimelineState(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    events: list[TimelineEvent] = Field(default_factory=list, description="时空大事记")
    arcs: list[TimelineArc] = Field(default_factory=list, description="叙事大弧与战略走向")
    clocks: list[TimelineClock] = Field(default_factory=list, description="危机倒计时时钟")
