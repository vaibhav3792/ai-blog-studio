from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=3, max_length=400)


class BlogUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=300)
    markdown: Optional[str] = None


class BlogSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic: str
    title: str
    status: str
    mode: Optional[str] = None
    word_count: int = 0
    created_at: datetime
    updated_at: datetime


class BlogDetail(BlogSummary):
    markdown: str = ""
    error: Optional[str] = None
    plan: Optional[Any] = None
    evidence: List[Any] = []
    warnings: List[str] = []
    images: List[str] = []
