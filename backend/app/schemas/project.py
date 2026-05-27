"""
Pydantic schemas for project-related API responses.

Requirements: 9.1
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProjectResponse(BaseModel):
    """Single project item returned by GET /projects."""

    id: uuid.UUID = Field(..., description="Project UUID.")
    name: str = Field(..., description="Human-readable project name.")
    slug: str = Field(..., description="URL-safe slug (lowercase, hyphens).")
    status: Literal["draft", "generating", "ready", "published", "failed"] = Field(
        ...,
        description="Current lifecycle status of the project.",
    )
    created_at: datetime = Field(..., description="ISO 8601 UTC creation timestamp.")
    published_url: str | None = Field(
        default=None,
        description="Public URL of the published landing page, or null if not yet published.",
    )


class ProjectListResponse(BaseModel):
    """Paginated list of projects returned by GET /projects."""

    items: list[ProjectResponse] = Field(..., description="Projects on the current page.")
    total: int = Field(..., ge=0, description="Total number of projects matching the query.")
    page: int = Field(..., ge=1, description="Current page number (1-indexed).")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page.")
