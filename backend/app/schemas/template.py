"""
Pydantic schemas for template-related API responses.

Requirements: 9.1
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class TemplateResponse(BaseModel):
    """Single template item returned by GET /templates."""

    id: uuid.UUID = Field(..., description="Template UUID.")
    name: str = Field(..., description="Template display name.")
    visual_style: Literal["minimalista", "corporativo", "moderno", "agressivo"] = Field(
        ...,
        description="Visual style category of the template.",
    )
    description: str | None = Field(
        default=None,
        description="Optional human-readable description of the template.",
    )
    preview_url: str | None = Field(
        default=None,
        description="URL of the template preview image.",
    )


class TemplateListResponse(BaseModel):
    """Paginated list of templates returned by GET /templates."""

    items: list[TemplateResponse] = Field(..., description="Templates on the current page.")
    total: int = Field(..., ge=0, description="Total number of templates matching the query.")
