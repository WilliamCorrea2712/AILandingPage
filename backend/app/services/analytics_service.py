"""
Analytics event recording service.

Requirements: 14.4
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

VALID_EVENTS = frozenset({
    "generation_started",
    "generation_completed",
    "publication_done",
    "error_occurred",
})


def record_event(
    db_session,
    event_type: str,
    user_id: str | None = None,
    project_id: str | None = None,
    job_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Insert an analytics event into the database with UTC timestamp.

    Args:
        db_session: SQLAlchemy session.
        event_type: One of the VALID_EVENTS values.
        user_id: UUID of the user who triggered the event.
        project_id: UUID of the related project.
        job_id: UUID of the related Celery job.
        metadata: Additional event metadata.
    """
    from app.models.analytics import Analytics

    if event_type not in VALID_EVENTS:
        logger.warning("Unknown analytics event_type: %s", event_type)

    event = Analytics(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user_id) if user_id else None,
        event_type=event_type,
        project_id=uuid.UUID(project_id) if project_id else None,
        job_id=uuid.UUID(job_id) if job_id else None,
        metadata=metadata or {},
        created_at=datetime.now(tz=timezone.utc),
    )
    try:
        db_session.add(event)
        db_session.commit()
    except Exception as exc:
        db_session.rollback()
        logger.error("Failed to record analytics event '%s': %s", event_type, exc)
