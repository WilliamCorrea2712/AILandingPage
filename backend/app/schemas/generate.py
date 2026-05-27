"""
Pydantic schemas for the POST /generate endpoint.

Requirements: 9.1, 9.4
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator


class GenerateRequest(BaseModel):
    """Request body for POST /generate."""

    prompt: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Natural-language description of the desired landing page (1–4000 chars).",
        examples=["Crie uma landing page para academia de musculação focada em captação de leads."],
    )
    project_name: str | None = Field(
        default=None,
        max_length=255,
        description="Optional name for the project. Auto-generated from the prompt if omitted.",
    )
    template_id: uuid.UUID | None = Field(
        default=None,
        description="Optional UUID of an existing template to use as the layout base.",
    )
    brand_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Optional primary brand colour in #RRGGBB format.",
        examples=["#FF5733"],
    )
    accent_color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Optional accent/highlight colour in #RRGGBB format.",
        examples=["#F6AD55"],
    )
    logo_url: str | None = Field(
        default=None,
        description="Data URI base64 ou URL do logo. Será inserido no header da landing page.",
        examples=["data:image/png;base64,iVBORw0KGgo..."],
    )

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("O prompt não pode ser composto apenas de espaços em branco.")
        return v


class GenerateResponse(BaseModel):
    """Response body for a successfully enqueued generation job (HTTP 202)."""

    job_id: uuid.UUID = Field(
        ...,
        description="Unique identifier of the Celery generation job.",
    )
    status: str = Field(
        default="pending",
        description="Initial job status — always 'pending' on creation.",
    )
    project_id: uuid.UUID = Field(
        ...,
        description="UUID of the project created or updated for this generation.",
    )
    estimated_seconds: int = Field(
        default=45,
        ge=0,
        description="Estimated number of seconds until the generation completes.",
    )
