"""
SQLAlchemy ORM model for the ``prompts`` table.

Requirements: 14.1, 14.2
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Prompt(Base):
    """User-submitted prompt and its extracted NLP attributes."""

    __tablename__ = "prompts"
    __table_args__ = (
        CheckConstraint(
            "char_length(content) BETWEEN 10 AND 2000",
            name="ck_prompts_content_length",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    nlp_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'pt'"),
        default="pt",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="prompts")  # noqa: F821
    ai_generations: Mapped[list["AIGeneration"]] = relationship(  # noqa: F821
        "AIGeneration", back_populates="prompt"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Prompt id={self.id} user_id={self.user_id}>"
