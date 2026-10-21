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
    """
    Extract service mentions, differentials, audience, tone, style
    and intention signals from a prompt. More patterns → richer learning.
    """
    import re

    pl = prompt.lower()

    # ── Services: "especializada em X e Y", "vendemos X", "oferecemos X" ──
    for pat in [
        r'especializ\w+\s+em\s+([^,\.:\n]+?)(?:\s*[,\.\n]|$)',
        r'(?:vende(?:mos)?|oferece(?:mos)?|trabalhamos\s+com)\s+([^,\.:\n]+?)(?:\s*[,\.\n]|$)',
        r'(?:servi[cç]os?|produtos?):\s*([^,\.:\n]+?)(?:\s*[,\.\n]|$)',
        r'nossos\s+(?:servi[cç]os?|produtos?)\s+s[aã]o\s+([^,\.:\n]+?)(?:\s*[,\.\n]|$)',
    ]:
        m = re.search(pat, pl)
        if m:
            for part in re.split(r'\s*[,e]\s+', m.group(1).strip()):
                part_clean = part.strip().title()
                if 3 < len(part_clean) < 60:
                    patterns[niche]["service"].append((part_clean, weight))

    # ── Differentials ─────────────────────────────────────────────────────
    DIFF_PATTERNS = [
        (r"(\d+)\s*anos?\s+de\s+(?:experiencia|mercado|atuacao)", "Anos de Experiencia"),
        (r"atendimento\s+24\s*h", "Atendimento 24h"),
        (r"garantia\s+de\s+(?:resultado|satisfacao|qualidade)", "Garantia de Qualidade"),
        (r"sem\s+fidelidade", "Sem Fidelidade"),
        (r"frete\s+gr[aá]tis|entrega\s+gr[aá]tis", "Frete Gratis"),
        (r"primeira\s+consulta\s+gr[aá]tis|avalia[cç][aã]o\s+gr[aá]tis", "Primeira Consulta Gratis"),
        (r"profissionais?\s+certificados?", "Profissionais Certificados"),
        (r"tecnologia\s+de\s+ponta|equipamentos?\s+modernos?", "Tecnologia de Ponta"),
        (r"atendimento\s+personalizado", "Atendimento Personalizado"),
        (r"resultado\s+(?:comprovado|garantido|r[aá]pido)", "Resultado Comprovado"),
        (r"parcelamento|parcelado\s+sem\s+juros", "Parcelamento Disponivel"),
        (r"entrega\s+r[aá]pida|agilidade", "Entrega Rapida"),
    ]
    for pattern, diff_name in DIFF_PATTERNS:
        if re.search(pattern, pl):
            patterns[niche]["differential"].append((diff_name, weight))

    # ── Visual style signal ───────────────────────────────────────────────
    if re.search(r"premium|luxo|elegante|sofisticado|exclusivo", pl):
        patterns[niche]["visual_style"].append(("corporativo", weight))
    elif re.search(r"moderno|inovador|contemporaneo|digital", pl):
        patterns[niche]["visual_style"].append(("moderno", weight))
    elif re.search(r"minimalista|simples|clean", pl):
        patterns[niche]["visual_style"].append(("minimalista", weight))
    elif re.search(r"agressivo|impactante|bold|energetico", pl):
        patterns[niche]["visual_style"].append(("agressivo", weight))

    # ── Audience signal ───────────────────────────────────────────────────
    if re.search(r"\btodos\b|p[úu]blico\s+geral|qualquer\s+pessoa", pl):
        patterns[niche]["audience"].append(("publico geral", weight))
    elif re.search(r"empresa|b2b|corporativo|cnpj", pl):
        patterns[niche]["audience"].append(("empresas e profissionais", weight))
    elif re.search(r"mulher|feminino", pl):
        patterns[niche]["audience"].append(("mulheres", weight))
    elif re.search(r"homem|masculino", pl):
        patterns[niche]["audience"].append(("homens", weight))
    elif re.search(r"jovem|universitario|estudante", pl):
        patterns[niche]["audience"].append(("jovens e estudantes", weight))

    # ── Tone signal ───────────────────────────────────────────────────────
    if re.search(r"informal|descontraido|jovem|casual|divertido", pl):
        patterns[niche]["tone"].append(("informal", weight))
    elif re.search(r"formal|profissional|serio|corporativo", pl):
        patterns[niche]["tone"].append(("formal", weight))


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
    Uses a diversity-aware score that penalizes over-used patterns to prevent
    style convergence over time.

    Score formula:
        diversity_score = avg_rating * (1 / log2(frequency + 2))

    Effect:
        - A pattern with frequency=1 and rating=2.0 scores 2.0
        - A pattern with frequency=10 and rating=2.0 scores ~0.57
        - A pattern with frequency=100 and rating=2.0 scores ~0.30

    This naturally rotates patterns — high-quality but less-seen patterns
    surface before overly-repeated ones, preventing style lock-in.
    """
    from app.models.pattern_cache import PatternCache
    import math

    try:
        # Fetch more than needed so we can re-rank with diversity score
        fetch_limit = limit * 4
        rows = (
            db.query(PatternCache)
            .filter_by(niche=niche, pattern_type=pattern_type)
            .filter(PatternCache.avg_rating > 0)
            .order_by(PatternCache.avg_rating.desc().nullslast())
            .limit(fetch_limit)
            .all()
        )

        if not rows:
            # Fallback: any pattern for this niche/type regardless of rating
            rows = (
                db.query(PatternCache)
                .filter_by(niche=niche, pattern_type=pattern_type)
                .order_by(PatternCache.frequency.asc())  # least used first
                .limit(limit)
                .all()
            )
            return [r.value for r in rows]

        # Re-rank by diversity score
        def diversity_score(row) -> float:
            rating = row.avg_rating if row.avg_rating is not None else 1.0
            freq = max(row.frequency, 1)
            return rating * (1.0 / math.log2(freq + 2))

        ranked = sorted(rows, key=diversity_score, reverse=True)
        return [r.value for r in ranked[:limit]]

    except Exception:
        return []
