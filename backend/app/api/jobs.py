"""GET /jobs/{job_id} endpoint. Requirements: 10.3"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.auth.jwt import TokenPayload
from app.database import get_db
from app.models.ai_generation import AIGeneration
from app.schemas.job import JobStatusResponse

router = APIRouter(tags=["jobs"])

# Track progress per job_id in memory (updated by worker via DB)
STEP_PROGRESS = {
    "interpretando": 0.10,
    "analisando prompt com ia": 0.20,
    "consultando base de conhecimento": 0.35,
    "gerando conteudo": 0.50,
    "montando layout": 0.70,
    "renderizando": 0.85,
    "finalizando": 0.95,
    "concluido": 1.0,
    "pending": 0.05,
    "processing": 0.50,
    "completed": 1.0,
    "failed": 0.0,
}


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: TokenPayload = Depends(get_current_user),
):
    gen = db.query(AIGeneration).filter_by(job_id=job_id).first()
    if not gen:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    # Build result payload when completed
    result = None
    if gen.status == "completed" and gen.html_output:
        result = {
            "html_output": gen.html_output,
            "css_output": gen.css_output,
            "structured_json": gen.structured_json,
        }

    error = None
    current_step = None
    if gen.error_details:
        error = gen.error_details.get("error")
        # Worker stores current step in error_details when not an actual error
        current_step = gen.error_details.get("step")

    # Map raw DB status to valid API status
    PROCESSING_STEPS = {
        "interpretando", "analisando prompt com ia",
        "consultando base de conhecimento",
        "gerando conteudo", "montando layout", "renderizando",
        "finalizando", "concluido",
    }
    raw_status = gen.status or "pending"
    if raw_status in PROCESSING_STEPS:
        api_status = "processing"
        current_step = current_step or raw_status
    elif raw_status == "completed":
        api_status = "completed"
    elif raw_status == "failed":
        api_status = "failed"
    else:
        api_status = "pending"

    progress = STEP_PROGRESS.get(raw_status, STEP_PROGRESS.get(api_status, 0.1))

    return JobStatusResponse(
        job_id=gen.job_id,
        status=api_status,
        progress=progress,
        current_step=current_step,
        error=error,
        result=result,
    )
