"""GET /analytics endpoint. Requirements: 9.1"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.auth.jwt import TokenPayload
from app.database import get_db
from app.models.analytics import Analytics
from app.schemas.analytics import AnalyticsEvent, AnalyticsResponse, AnalyticsSummary

router = APIRouter(tags=["analytics"])


@router.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(
    event_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: TokenPayload = Depends(require_admin),
):
    q = db.query(Analytics)
    if event_type:
        q = q.filter_by(event_type=event_type)
    events = q.order_by(Analytics.created_at.desc()).limit(100).all()

    total_gen = db.query(Analytics).filter_by(event_type="generation_started").count()
    total_pub = db.query(Analytics).filter_by(event_type="publication_done").count()
    total_err = db.query(Analytics).filter_by(event_type="error_occurred").count()
    error_rate = total_err / max(total_gen, 1)

    return AnalyticsResponse(
        events=[AnalyticsEvent(
            id=e.id, user_id=e.user_id, event_type=e.event_type,
            project_id=e.project_id, job_id=e.job_id,
            metadata=e.metadata, created_at=e.created_at,
        ) for e in events],
        summary=AnalyticsSummary(
            total_generations=total_gen,
            total_publications=total_pub,
            error_rate=round(error_rate, 4),
        ),
    )
