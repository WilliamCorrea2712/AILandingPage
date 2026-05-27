"""
Pydantic schema for standardised API error responses.

Every error returned by the API must conform to this schema so that clients
can reliably parse error details without inspecting HTTP status codes alone.

Requirements: 9.5
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standardised error response body returned for all API errors."""

    error_code: str = Field(
        ...,
        description="Machine-readable error identifier (e.g. 'PROMPT_TOO_SHORT').",
        examples=["PROMPT_TOO_SHORT"],
    )
    message: str = Field(
        ...,
        description="Human-readable description of the error.",
        examples=["O prompt deve ter no mínimo 10 caracteres."],
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="ISO 8601 UTC timestamp of when the error occurred.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "error_code": "PROMPT_TOO_SHORT",
                "message": "O prompt deve ter no mínimo 10 caracteres.",
                "timestamp": "2024-01-15T10:30:00Z",
            }
        }
    }
