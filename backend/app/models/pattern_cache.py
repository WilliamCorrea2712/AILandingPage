"""
SQLAlchemy model for the ``pattern_cache`` table.

Stores auto-learned niche patterns extracted from high-rated generations.
Used by the generation worker to enrich copy with real user-validated patterns.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PatternCache(Base):
    """Auto-learned niche pattern extracted from validated generations."""

    __tablename__ = "pattern_cache"
    __table_args__ = (
        UniqueConstraint("niche", "pattern_type", "value",
                         name="uq_pattern_cache_niche_type_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    niche: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    pattern_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Types: "service", "differential", "testimonial", "faq_q", "faq_a",
    #        "cta", "headline", "subtitle"
    value: Mapped[str] = mapped_column(Text, nullable=False)
    frequency: Mapped[int] = mapped_column(
        Integer, server_default=text("1"), default=1)
    avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    def __repr__(self) -> str:
        return f"<PatternCache niche={self.niche!r} type={self.pattern_type!r} freq={self.frequency}>"
