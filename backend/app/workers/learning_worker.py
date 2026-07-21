"""
Learning Worker — auto-learning from accumulated generations.

Runs periodically (via Celery Beat) to:
1. Analyze completed generations (especially positively rated ones)
2. Extract patterns: services, differentials, testimonials, CTAs, headlines
3. Update pattern_cache table with frequency and quality scores
4. Promote high-quality patterns to the generation pipeline

This creates a continuous improvement loop without manual intervention.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.workers.learning_worker.run_pattern_learning",
    bind=True,
    max_retries=0,
    queue="training_jobs",
)
def run_pattern_learning(self, days_back: int = 7):
    """
    Analyze recent generations and extract/update niche patterns.
    Designed to run weekly, processing the last 7 days of data.
    """
    from app.database import get_db_session

    with get_db_session() as db:
        try:
            stats = _run_learning_cycle(db, days_back)
            logger.info(
                "Learning cycle complete: %d generations analyzed, "
                "%d patterns updated, %d new patterns discovered",
                stats["analyzed"], stats["updated"], stats["new"],
            )
            return stats
        except Exception as exc:
            logger.error("Learning cycle failed: %s", exc, exc_info=True)
            raise


def _run_learning_cycle(db, days_back: int) -> dict:
    """Core learning logic — analyze generations and update pattern cache."""
    from app.models.ai_generation import AIGeneration
    from app.models.pattern_cache import PatternCache
    from app.models.prompt import Prompt

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_back)

    # Fetch completed generations from the period
    generations = (
        db.query(AIGeneration)
        .filter(
            AIGeneration.status == "completed",
            AIGeneration.completed_at >= cutoff,
            AIGeneration.structured_json.isnot(None),
        )
        .all()
    )

    logger.info("Analyzing %d generations from last %d days", len(generations), days_back)

    # Group by niche and accumulate patterns
    niche_patterns: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for gen in generations:
        sj = gen.structured_json or {}
        niche = gen.niche or sj.get("niche", "")
        if not niche:
            continue

        # Weight: rated positive = 2.0, no rating = 1.0, rated negative = 0.0
        weight = 2.0 if gen.user_rating == 1 else (0.0 if gen.user_rating == -1 else 1.0)
        if weight == 0.0:
            continue  # skip negatively rated generations

        # Extract headline
        headline = sj.get("headline", "")
        if headline and len(headline) > 10:
            niche_patterns[niche]["headline"].append((headline, weight))

        # Extract services from structured_json (the worker saves them there)
        # We also parse from the prompt via Prompt model
        prompt_row = db.query(Prompt).filter_by(id=gen.prompt_id).first()
        if prompt_row:
            _extract_from_prompt(niche, prompt_row.content, weight, niche_patterns)

    # Update pattern_cache with accumulated data
    stats = {"analyzed": len(generations), "updated": 0, "new": 0}

    for niche, type_patterns in niche_patterns.items():
        for pattern_type, value_weights in type_patterns.items():
            for value, weight in value_weights:
                value_clean = str(value).strip()[:500]
                if not value_clean or len(value_clean) < 3:
                    continue

                existing = (
                    db.query(PatternCache)
                    .filter_by(niche=niche, pattern_type=pattern_type, value=value_clean)
                    .first()
                )

                if existing:
                    existing.frequency += 1
                    # Rolling average of rating
                    if existing.avg_rating is not None:
                        existing.avg_rating = (existing.avg_rating + weight) / 2
                    else:
                        existing.avg_rating = weight
                    existing.updated_at = datetime.now(tz=timezone.utc)
                    stats["updated"] += 1
                else:
                    entry = PatternCache(
                        niche=niche,
                        pattern_type=pattern_type,
                        value=value_clean,
                        frequency=1,
                        avg_rating=weight,
                        created_at=datetime.now(tz=timezone.utc),
                        updated_at=datetime.now(tz=timezone.utc),
                    )
                    db.add(entry)
                    stats["new"] += 1

    db.commit()

    # Also discover new niches not in the taxonomy
    _discover_new_niches(db, generations)

    return stats


def _extract_from_prompt(
    niche: str,
    prompt: str,
    weight: float,
    patterns: dict,
) -> None:
    """Extract service mentions and differentials from a prompt."""
    import re

    pl = prompt.lower()

    # Extract explicit service mentions ("especializada em X e Y")
    spec_m = re.search(
        r'especializ\w+\s+em\s+([^,\.]+?)(?:\s*,|\.|$)', pl
    )
    if spec_m:
        for part in re.split(r'\s+e\s+', spec_m.group(1).strip()):
            part_clean = part.strip().title()
            if 4 < len(part_clean) < 60:
                patterns[niche]["service"].append((part_clean, weight))

    # Extract differentials
    DIFF_PATTERNS = [
        (r"(\d+)\s*anos?\s+de\s+(?:experiencia|mercado)", "Anos de Experiencia"),
        (r"atendimento\s+24\s*h", "Atendimento 24h"),
        (r"garantia\s+de\s+(?:resultado|satisfacao)", "Garantia de Resultado"),
        (r"sem\s+fidelidade", "Sem Fidelidade"),
        (r"frete\s+gr[aá]tis", "Frete Grátis"),
        (r"primeira\s+consulta\s+gr[aá]tis", "Primeira Consulta Grátis"),
    ]
    for pattern, diff_name in DIFF_PATTERNS:
        if re.search(pattern, pl):
            patterns[niche]["differential"].append((diff_name, weight))


def _discover_new_niches(db, generations) -> None:
    """Log niches that appear frequently but aren't in the taxonomy."""
    from app.workers.generation_worker import NICHES as KNOWN_NICHES

    known_niche_names = {n for _, n, _ in KNOWN_NICHES}
    niche_counts: dict[str, int] = defaultdict(int)

    for gen in generations:
        niche = gen.niche or (gen.structured_json or {}).get("niche", "")
        if niche and niche not in known_niche_names:
            niche_counts[niche] += 1

    for niche, count in niche_counts.items():
        if count >= 3:
            logger.info(
                "NEW NICHE DISCOVERED (not in taxonomy): '%s' appeared %d times — "
                "consider adding to NICHES list",
                niche, count,
            )


def get_learned_patterns(db, niche: str, pattern_type: str, limit: int = 5) -> list[str]:
    """
    Retrieve top patterns for a niche from the cache.
    Used by generation worker to enrich copy with real learned data.
    """
    from app.models.pattern_cache import PatternCache

    try:
        rows = (
            db.query(PatternCache)
            .filter_by(niche=niche, pattern_type=pattern_type)
            .order_by(
                PatternCache.avg_rating.desc().nullslast(),
                PatternCache.frequency.desc(),
            )
            .limit(limit)
            .all()
        )
        return [r.value for r in rows]
    except Exception:
        return []
