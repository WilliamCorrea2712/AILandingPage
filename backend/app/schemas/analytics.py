"""
Pydantic schemas for the GET /analytics endpoint.

Requirements: 9.1
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AnalyticsEvent(BaseModel):
    """A single analytics event record."""

    id: uuid.UUID = Field(..., description="Event UUID.")
    user_id: uuid.UUID | None = Field(default=None, description="UUID of the user who triggered the event.")
    event_type: str = Field(..., description="Type of event (e.g. 'generation_started').")
    project_id: uuid.UUID | None = Field(default=None, description="UUID of the related project.")
    job_id: uuid.UUID | None = Field(default=None, description="UUID of the related Celery job.")
    metadata: dict | None = Field(default=None, description="Additional event metadata.")
    created_at: datetime = Field(..., description="ISO 8601 UTC timestamp of the event.")


class AnalyticsSummary(BaseModel):
    """Aggregated analytics summary."""

    total_generations: int = Field(..., ge=0, description="Total number of generation jobs started.")
    total_publications: int = Field(..., ge=0, description="Total number of successful publications.")
    error_rate: float = Field(..., ge=0.0, le=1.0, description="Fraction of jobs that ended in error.")


class AnalyticsResponse(BaseModel):
    """Response body for GET /analytics."""

    events: list[AnalyticsEvent] = Field(..., description="List of analytics events matching the query.")
    summary: AnalyticsSummary = Field(..., description="Aggregated summary statistics.")
