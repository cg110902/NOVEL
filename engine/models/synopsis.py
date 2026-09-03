"""梗概 (Synopsis) 强类型领域模型，对齐 engine/schemas/synopsis.schema.json。"""
from __future__ import annotations
from typing import Optional, Dict, Literal
from pydantic import BaseModel, ConfigDict, Field


class ChapterSynopsis(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    num: int = Field(..., ge=1, description="章节序号")
    title: Optional[str] = Field(None, description="章节标题")
    synopsis: Optional[str] = Field(None, description="章节梗概")
    source: Optional[Literal["manual"]] = Field(None, description="来源标记")


class SynopsisState(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)

    book_logline: Optional[str] = Field(None, description="全书一句话梗概")
    chapters: Dict[str, ChapterSynopsis] = Field(default_factory=dict, description="分章梗概字典，键为 ch_XXX")
