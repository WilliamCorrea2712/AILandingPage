"""
POST /feedback/{job_id}  — User rates a generation (👍 / 👎 + optional text).

When a user rates a generation:
1. Saves user_rating (+1 / -1) and optional feedback_text on AIGeneration
2. Updates quality_score on the linked TrainingData row
3. Updates avg_rating on all PatternCache rows for that niche
4. Schedules an immediate mini learning cycle if rating is positive

This closes the feedback loop so get_learned_patterns() has real human signal
instead of the default 0.7 quality_score set at generation time.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.auth.jwt import TokenPayload
from app.database import get_db

router = APIRouter(tags=["feedback"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    rating: int = Field(
        ...,
        description="1 = positivo (gostei), -1 = negativo (não gostei)",
        ge=-1,
        le=1,
    )
    feedback_text: str | None = Field(
        default=None,
        max_length=1000,
        description="Comentário opcional do usuário sobre a geração.",
    )


class FeedbackResponse(BaseModel):
    job_id: uuid.UUID
    rating: int
    quality_score: float
    message: str


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post(
    "/feedback/{job_id}",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
)
def submit_feedback(
    job_id: uuid.UUID,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    user: TokenPayload = Depends(get_current_user),
):
    """
    Submit user feedback (thumbs up/down) for a generation.
    Updates training data quality and pattern cache scores.
    """
    from app.models.ai_generation import AIGeneration
    from app.models.training_data import TrainingData
    from app.models.pattern_cache import PatternCache
    from app.models.project import Project

    # ── 1. Find the generation ─────────────────────────────────────────────
    gen = db.query(AIGeneration).filter_by(job_id=job_id).first()
    if not gen:
        raise HTTPException(status_code=404, detail="Geração não encontrada.")

    # Verify the generation belongs to the requesting user
    project = db.query(Project).filter_by(id=gen.project_id).first()
    if not project or str(project.user_id) != user.user_id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    if gen.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Só é possível avaliar gerações concluídas.",
        )

    # ── 2. Save rating on the generation ──────────────────────────────────
    gen.user_rating = body.rating
    gen.feedback_text = body.feedback_text
    gen.feedback_at = datetime.now(tz=timezone.utc)

    # ── 3. Compute quality score ───────────────────────────────────────────
    # +1 → 1.0, -1 → 0.1, re-rating averages with previous score
    new_raw_score = 1.0 if body.rating == 1 else 0.1
    quality_score = new_raw_score

    # ── 4. Update TrainingData quality_score ──────────────────────────────
    niche = gen.niche or (gen.structured_json or {}).get("niche", "")

    if niche:
        # Update the most recent validated training row for this niche
        training_rows = (
            db.query(TrainingData)
            .filter(TrainingData.prompt.ilike(f"%{niche}%"))
            .filter(TrainingData.is_validated == True)
            .order_by(TrainingData.created_at.desc())
            .limit(5)
            .all()
        )
        for tr in training_rows:
            if tr.quality_score is not None:
                # Rolling average: blend existing score with new human signal
                tr.quality_score = round((tr.quality_score * 0.6) + (new_raw_score * 0.4), 4)
            else:
                tr.quality_score = new_raw_score
            quality_score = tr.quality_score
            break  # update only the most recent one

        # ── 5. Update PatternCache avg_rating for this niche ──────────────
        # Positive rating boosts patterns; negative rating penalizes them
        rating_delta = 0.3 if body.rating == 1 else -0.3
        pattern_rows = (
            db.query(PatternCache)
            .filter_by(niche=niche)
            .all()
        )
        for pr in pattern_rows:
            if pr.avg_rating is not None:
                pr.avg_rating = max(0.0, min(2.0, round(pr.avg_rating + rating_delta, 4)))
            else:
                pr.avg_rating = 1.0 + rating_delta
            pr.updated_at = datetime.now(tz=timezone.utc)

    db.commit()

    # ── 6. Trigger immediate mini learning cycle for positive feedback ─────
    if body.rating == 1 and niche:
        try:
            from app.workers.learning_worker import run_pattern_learning
            run_pattern_learning.apply_async(
                kwargs={"days_back": 1},
                queue="training_jobs",
                countdown=5,  # 5s delay so the commit above is visible
            )
        except Exception:
            pass  # non-critical — weekly cycle will catch it

    return FeedbackResponse(
        job_id=job_id,
        rating=body.rating,
        quality_score=round(quality_score, 4),
        message=(
            "Obrigado! Seu feedback melhora as próximas gerações."
            if body.rating == 1
            else "Feedback registrado. Vamos melhorar."
        ),
    )
