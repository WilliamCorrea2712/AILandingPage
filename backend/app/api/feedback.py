"""
POST /feedback/{job_id} — submit user rating for a generated landing page.

Rating 1 = positive (👍), -1 = negative (👎).
Positive ratings automatically promote the generation to validated training data.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.auth.jwt import TokenPayload
from app.database import get_db
from app.models.ai_generation import AIGeneration
from app.models.training_data import TrainingData

router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    rating: int = Field(..., description="1 = gostei, -1 = não gostei")
    feedback_text: str | None = Field(
        default=None,
        max_length=1000,
        description="Comentário opcional sobre a landing page gerada",
    )


class FeedbackResponse(BaseModel):
    job_id: uuid.UUID
    rating: int
    message: str


@router.post("/feedback/{job_id}", response_model=FeedbackResponse)
def submit_feedback(
    job_id: uuid.UUID,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    user: TokenPayload = Depends(get_current_user),
):
    if body.rating not in (1, -1):
        raise HTTPException(status_code=422, detail="Rating deve ser 1 (positivo) ou -1 (negativo).")

    gen = db.query(AIGeneration).filter_by(job_id=job_id).first()
    if not gen:
        raise HTTPException(status_code=404, detail="Job não encontrado.")
    if gen.status != "completed":
        raise HTTPException(status_code=400, detail="Só é possível avaliar gerações concluídas.")

    # Save feedback
    gen.user_rating = body.rating
    gen.feedback_text = body.feedback_text
    gen.feedback_at = datetime.now(tz=timezone.utc)

    # Positive rating → promote to validated training data immediately
    if body.rating == 1 and gen.html_output:
        _promote_to_training(db, gen)

    db.commit()

    return FeedbackResponse(
        job_id=job_id,
        rating=body.rating,
        message="Obrigado! Seu feedback melhora as próximas gerações." if body.rating == 1
                else "Feedback registrado. Vamos melhorar!",
    )


def _promote_to_training(db: Session, gen: AIGeneration) -> None:
    """Save a positively-rated generation as validated training data."""
    try:
        # Get original prompt
        from app.models.prompt import Prompt
        prompt_row = db.query(Prompt).filter_by(id=gen.prompt_id).first()
        if not prompt_row:
            return

        # Build completion from structured JSON (compact, useful for LLM training)
        import json
        completion = json.dumps({
            "niche": gen.niche or (gen.structured_json or {}).get("niche", ""),
            "headline": (gen.structured_json or {}).get("headline", ""),
            "sections": (gen.structured_json or {}).get("sections", []),
            "style": (gen.structured_json or {}).get("style", ""),
            "rating": gen.user_rating,
        }, ensure_ascii=False)

        # Check if already exists
        existing = db.query(TrainingData).filter_by(
            prompt=prompt_row.content[:2000]
        ).first()

        if existing:
            # Update quality score on re-rating
            existing.quality_score = 1.0
            existing.is_validated = True
        else:
            td = TrainingData(
                id=uuid.uuid4(),
                prompt=prompt_row.content[:2000],
                completion=completion[:10000],
                source="user_feedback",
                quality_score=1.0,
                is_validated=True,
                created_at=datetime.now(tz=timezone.utc),
            )
            db.add(td)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Failed to promote to training data: %s", e)
