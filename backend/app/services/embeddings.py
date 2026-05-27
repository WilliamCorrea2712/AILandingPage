"""
Embedding generation and indexing service.

Requirements: 12.1, 12.4
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.vector_db import VectorDBClient

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
VECTOR_SIZE = 384
TEMPLATES_COLLECTION = "templates"
COMPONENTS_COLLECTION = "components"

_encoder = None


def _get_encoder():
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer
        _encoder = SentenceTransformer(EMBEDDING_MODEL)
    return _encoder


def generate_embedding(text: str) -> list[float]:
    """Generate a 384-dimensional embedding for the given text."""
    encoder = _get_encoder()
    return encoder.encode(text).tolist()


def index_all_templates_and_components(db_session, vector_client: "VectorDBClient") -> None:
    """
    Generate embeddings for all templates and components in the database
    and store them in the vector database. Called at system startup.
    """
    from app.models.component import Component
    from app.models.template import Template

    # Ensure collections exist
    vector_client.create_collection(TEMPLATES_COLLECTION, VECTOR_SIZE)
    vector_client.create_collection(COMPONENTS_COLLECTION, VECTOR_SIZE)

    templates = db_session.query(Template).all()
    for t in templates:
        text = f"{t.name} {t.description or ''} {t.visual_style}"
        emb = generate_embedding(text)
        vector_client.upsert(
            TEMPLATES_COLLECTION,
            str(t.id),
            emb,
            {"name": t.name, "visual_style": t.visual_style, "template_id": str(t.id)},
        )
    logger.info("Indexed %d templates in vector DB.", len(templates))

    components = db_session.query(Component).all()
    for c in components:
        text = f"{c.name} {c.type}"
        emb = generate_embedding(text)
        vector_client.upsert(
            COMPONENTS_COLLECTION,
            str(c.id),
            emb,
            {"name": c.name, "type": c.type, "component_id": str(c.id)},
        )
    logger.info("Indexed %d components in vector DB.", len(components))


def update_template_embedding(template_id: str, name: str, description: str, visual_style: str,
                               vector_client: "VectorDBClient") -> None:
    """Update the embedding for a single template (called after insert/update)."""
    text = f"{name} {description or ''} {visual_style}"
    emb = generate_embedding(text)
    vector_client.upsert(
        TEMPLATES_COLLECTION,
        template_id,
        emb,
        {"name": name, "visual_style": visual_style, "template_id": template_id},
    )


def update_component_embedding(component_id: str, name: str, component_type: str,
                                vector_client: "VectorDBClient") -> None:
    """Update the embedding for a single component (called after insert/update)."""
    text = f"{name} {component_type}"
    emb = generate_embedding(text)
    vector_client.upsert(
        COMPONENTS_COLLECTION,
        component_id,
        emb,
        {"name": name, "type": component_type, "component_id": component_id},
    )
