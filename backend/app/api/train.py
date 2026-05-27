"""POST /train endpoint. Requirements: 9.1, 11.2"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.auth.jwt import TokenPayload
from app.schemas.train import TrainRequest, TrainResponse
from app.workers.training_worker import run_training_job

router = APIRouter(tags=["train"])


@router.post("/train", response_model=TrainResponse, status_code=202)
def train(
    body: TrainRequest,
    user: TokenPayload = Depends(require_admin),
):
    job_id = uuid.uuid4()
    run_training_job.apply_async(
        kwargs={
            "job_id": str(job_id),
            "source": body.source,
            "model_name": body.model_name,
            "technique": body.technique,
            "epochs": body.epochs,
            "learning_rate": body.learning_rate,
            "file_url": body.file_url,
        },
        task_id=str(job_id),
    )
    return TrainResponse(job_id=job_id, status="pending", model_name=body.model_name, dataset_size=100)
