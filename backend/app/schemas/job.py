"""
Pydantic schemas for the GET /jobs/{job_id} endpoint.

Requirements: 9.1, 10.3
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class JobStatusResponse(BaseModel):
    """Response body for GET /jobs/{job_id}."""

    job_id: uuid.UUID = Field(..., description="Unique identifier of the job.")
    status: Literal["pending", "processing", "completed", "failed"] = Field(
        ...,
        description="Current status of the job.",
    )
    progress: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Completion fraction between 0.0 (not started) and 1.0 (done).",
    )
    current_step: str | None = Field(
        default=None,
        description="Human-readable description of the step currently being executed.",
        examples=["gerando conteúdo"],
    )
    error: str | None = Field(
        default=None,
        description="Error message if the job failed, otherwise null.",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="Job result payload when status='completed', otherwise null.",
    )
