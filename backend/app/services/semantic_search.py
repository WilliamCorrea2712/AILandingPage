"""
Semantic search with PostgreSQL fallback.

Requirements: 12.2, 12.5, 12.6
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.vector_db import VectorDBClient

logger = logging.getLogger(__name__)


def search_templates(
    query_text: str,
    vector_client: "VectorDBClient",
    db_session,
    threshold: float = 0.50,
    limit: int = 5,
) -> list[dict]:
    """
    Search for similar templates using cosine similarity.
    Falls back to most recent PostgreSQL templates if Vector DB is unavailable.
    """
    from app.services.embeddings import generate_embedding, TEMPLATES_COLLECTION

    try:
        query_emb = generate_embedding(query_text)
        results = vector_client.search(TEMPLATES_COLLECTION, query_emb, threshold=threshold, limit=limit)
        if results:
            return results
        # No results above threshold — return all that matched
        return results
    except Exception as exc:
        logger.warning("Vector DB unavailable during search: %s. Using PostgreSQL fallback.", exc)
        return _fallback_templates(db_session, limit)


def _fallback_templates(db_session, limit: int) -> list[dict]:
    from app.models.template import Template
    templates = db_session.query(Template).order_by(Template.created_at.desc()).limit(limit).all()
    return [
        {"id": str(t.id), "score": 0.0, "payload": {"name": t.name, "visual_style": t.visual_style, "template_id": str(t.id)}}
        for t in templates
    ]
