"""
SQLAlchemy ORM model for the ``ai_generations`` table.

Requirements: 14.1, 14.2
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, SmallInteger, Text, text
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AIGeneration(Base):
    """Record of a single AI generation job and its outputs."""

    __tablename__ = "ai_generations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompts.id"),
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'pending'"),
        default="pending",
    )
    niche: Mapped[str | None] = mapped_column(String(100), nullable=True)
    structured_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    html_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    css_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    user_rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # 1 = positive (👍), -1 = negative (👎), None = no feedback
    feedback_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default=text("0"),
        default=0,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    # Relationships
    project: Mapped["Project"] = relationship(  # noqa: F821
        "Project", back_populates="ai_generations"
    )
    prompt: Mapped["Prompt"] = relationship(  # noqa: F821
        "Prompt", back_populates="ai_generations"
    )
    publications: Mapped[list["Publication"]] = relationship(  # noqa: F821
        "Publication", back_populates="generation"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AIGeneration id={self.id} job_id={self.job_id} status={self.status!r}>"
        )
