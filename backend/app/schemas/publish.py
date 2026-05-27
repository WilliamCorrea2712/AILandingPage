"""
Pydantic schemas for the POST /publish endpoint.

Requirements: 9.1, 8.1
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator


class PublishRequest(BaseModel):
    """Request body for POST /publish."""

    project_id: uuid.UUID = Field(
        ...,
        description="UUID of the project to publish.",
    )
    generation_id: uuid.UUID = Field(
        ...,
        description="UUID of the completed AI generation to publish.",
    )
    custom_domain: str | None = Field(
        default=None,
        description="Optional fully-qualified custom domain (e.g. 'meusite.com.br').",
        examples=["meusite.com.br"],
    )

    @field_validator("custom_domain")
    @classmethod
    def validate_fqdn(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Basic FQDN validation: at least one dot, no spaces, no protocol prefix
        v = v.strip().lower()
        if " " in v or v.startswith("http"):
            raise ValueError(
                "custom_domain deve ser um FQDN válido sem protocolo (ex: 'meusite.com.br')."
            )
        if "." not in v:
            raise ValueError("custom_domain deve conter pelo menos um ponto.")
        return v


class PublishResponse(BaseModel):
    """Response body for a successfully enqueued publication job (HTTP 202)."""

    job_id: uuid.UUID = Field(..., description="Unique identifier of the publication job.")
    status: str = Field(default="pending", description="Initial job status.")
    subdomain: str = Field(
        ...,
        description="Estimated subdomain that will be assigned (e.g. 'meu-projeto.plataforma.com').",
    )
    estimated_minutes: int = Field(
        default=5,
        ge=1,
        description="Estimated minutes until the publication is live.",
    )
