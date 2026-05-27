"""POST /generate endpoint. Requirements: 9.4, 9.3"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.auth.jwt import TokenPayload
from app.database import get_db
from app.models.ai_generation import AIGeneration
from app.models.project import Project
from app.models.prompt import Prompt
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.workers.generation_worker import run_generation_pipeline

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerateResponse, status_code=202)
def generate(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    user: TokenPayload = Depends(get_current_user),
):
    now = datetime.now(tz=timezone.utc)

    # 1. Save the prompt
    prompt = Prompt(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user.user_id),
        content=body.prompt[:2000],  # enforce max length
        language="pt",
        created_at=now,
    )
    db.add(prompt)
    db.flush()  # get prompt.id without committing yet

    # 2. Create project
    project_name = body.project_name or body.prompt[:50]
    slug_base = project_name.lower().replace(" ", "-")
    slug_base = "".join(c if c.isalnum() or c == "-" else "" for c in slug_base)[:80]
    slug = f"{slug_base}-{uuid.uuid4().hex[:6]}"

    project = Project(
        id=uuid.uuid4(),
        user_id=uuid.UUID(user.user_id),
        name=project_name,
        slug=slug,
        status="generating",
        template_id=body.template_id,
        created_at=now,
        updated_at=now,
    )
    db.add(project)
    db.flush()

    # 3. Create generation record
    job_id = uuid.uuid4()
    gen = AIGeneration(
        id=uuid.uuid4(),
        project_id=project.id,
        prompt_id=prompt.id,
        job_id=job_id,
        status="pending",
        retry_count=0,
        created_at=now,
    )
    db.add(gen)
    db.commit()

    # 4. Enqueue Celery task
    try:
        run_generation_pipeline.apply_async(
            kwargs={
                "job_id": str(job_id),
                "prompt": body.prompt,
                "project_id": str(project.id),
                "brand_color": body.brand_color,
                "accent_color": body.accent_color,
                "logo_url": body.logo_url,
                "user_id": user.user_id,
            },
            task_id=str(job_id),
        )
    except Exception:
        # If Celery is unavailable, still return 202 — job will be picked up later
        pass

    return GenerateResponse(
        job_id=job_id,
        status="pending",
        project_id=project.id,
        estimated_seconds=45,
    )
