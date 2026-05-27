"""POST /publish endpoint. Requirements: 9.1, 8.1"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.auth.jwt import TokenPayload
from app.config import settings
from app.schemas.publish import PublishRequest, PublishResponse
from app.workers.render_worker import run_render_job

router = APIRouter(tags=["publish"])


@router.post("/publish", response_model=PublishResponse, status_code=202)
def publish(
    body: PublishRequest,
    user: TokenPayload = Depends(get_current_user),
):
    job_id = uuid.uuid4()
    run_render_job.apply_async(
        kwargs={
            "job_id": str(job_id),
            "project_id": str(body.project_id),
            "generation_id": str(body.generation_id),
            "user_id": user.user_id,
        },
        task_id=str(job_id),
    )
    slug = str(body.project_id)[:8]
    return PublishResponse(
        job_id=job_id,
        status="pending",
        subdomain=f"{slug}.{settings.PLATFORM_DOMAIN}",
        estimated_minutes=5,
    )
