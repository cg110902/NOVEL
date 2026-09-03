"""复式记账台账 (Ledger) 强类型领域模型。"""
from __future__ import annotations
from enum import Enum
from typing import Optional, Dict
from pydantic import BaseModel, ConfigDict, Field


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    OPENING_BALANCE = "opening_balance"
    MANUAL = "manual"


class LedgerPool(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    name: str = Field(..., description="资金/资源池名称")
    unit: Optional[str] = Field(None, description="计量单位")
    initial: int = Field(..., description="期初结余")
    current: int = Field(..., description="当前可用结余")


class LedgerTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    chapter: str = Field(..., pattern=r"^ch_\d{3,}$", description="发生章节编号")
    pool: str = Field(..., description="关联资源池 ID")
    delta: int = Field(..., description="收支变动额（收入为正，支出为负）")
    type: Optional[TransactionType] = Field(None, description="流水性质分类")
    subject: str = Field(..., description="收支明细事由")
    counterparty: Optional[str] = Field(None, description="交易对手方/收益方/支出方")
    note: Optional[str] = Field(None, description="备忘备注")
    balance_after: int = Field(..., description="发生后账户结余")


class LedgerState(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    note: Optional[str] = Field(None, description="货币与资产换算说明")
    pools: Dict[str, LedgerPool] = Field(default_factory=dict, description="资金池字典")
    transactions: list[LedgerTransaction] = Field(default_factory=list, description="历史交易对账流水")
