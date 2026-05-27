"""
SQLAlchemy ORM model for the ``projects`` table.

Requirements: 14.1, 14.2
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Project(Base):
    """A user's landing page project."""

    __tablename__ = "projects"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=text("'draft'"),
        default="draft",
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("templates.id"),
        nullable=True,
    )
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

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="projects")  # noqa: F821
    template: Mapped["Template | None"] = relationship(  # noqa: F821
        "Template", back_populates="projects"
    )
    ai_generations: Mapped[list["AIGeneration"]] = relationship(  # noqa: F821
        "AIGeneration", back_populates="project", cascade="all, delete-orphan"
    )
    publications: Mapped[list["Publication"]] = relationship(  # noqa: F821
        "Publication", back_populates="project", cascade="all, delete-orphan"
    )
    analytics: Mapped[list["Analytics"]] = relationship(  # noqa: F821
        "Analytics", back_populates="project"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Project id={self.id} slug={self.slug!r} status={self.status!r}>"
