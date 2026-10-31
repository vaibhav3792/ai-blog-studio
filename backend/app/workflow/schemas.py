from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Task(BaseModel):
    id: int
    title: str
    goal: str = Field(..., description="One sentence describing what the reader should do/understand.")
    bullets: List[str] = Field(..., description="3 to 6 concrete bullets, covered in order.")
    target_words: int = Field(..., description="Target words (120-550).")

    tags: List[str] = Field(default_factory=list)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False

    # Limits are enforced here instead of in the JSON schema, because strict
    # structured-output modes reject minItems/maxItems.
    @field_validator("bullets")
    @classmethod
    def _trim_bullets(cls, v: List[str]) -> List[str]:
        return [b for b in v if b.strip()][:6]

    @field_validator("target_words")
    @classmethod
    def _clamp_words(cls, v: int) -> int:
        return max(120, min(550, v))


class Plan(BaseModel):
    blog_title: str
    audience: str
    tone: str
    blog_kind: Literal["explainer", "tutorial", "news_roundup", "comparison", "system_design"] = "explainer"
    constraints: List[str] = Field(default_factory=list)
    tasks: List[Task]


class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = None  # ISO "YYYY-MM-DD" or null
    snippet: Optional[str] = None
    source: Optional[str] = None


class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal["closed_book", "hybrid", "open_book"]
    reason: str
    queries: List[str] = Field(default_factory=list)


class ImageProposal(BaseModel):
    section_id: int = Field(..., description="id of the section the visual belongs to")
    kind: Literal["diagram", "illustration"]
    alt: str
    caption: str = Field(..., description="One sentence telling the reader what to notice.")
    filename: str = Field(default="", description="illustration only: short snake_case name, no extension")
    prompt: str = Field(default="", description="illustration only: prompt for the image model")
    mermaid: str = Field(default="", description="diagram only: Mermaid source, no code fences")


class GlobalImagePlan(BaseModel):
    images: List[ImageProposal] = Field(default_factory=list)
