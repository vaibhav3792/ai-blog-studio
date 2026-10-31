from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Blog(Base):
    __tablename__ = "blogs"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(400))
    title: Mapped[str] = mapped_column(String(300), default="")
    markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    mode: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plan: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    evidence: Mapped[Any] = mapped_column(JSON, default=list)
    warnings: Mapped[Any] = mapped_column(JSON, default=list)
    images: Mapped[Any] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
