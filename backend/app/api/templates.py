"""GET /templates endpoint. Requirements: 14.3"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.template_repository import TemplateRepository
from app.schemas.template import TemplateListResponse, TemplateResponse
from app.services.cache import get_cached, set_cached

router = APIRouter(tags=["templates"])


@router.get("/templates", response_model=TemplateListResponse)
def list_templates(
    style: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    cache_key = f"templates:{style}:p{page}:ps{page_size}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    repo = TemplateRepository(db)
    if style:
        items = repo.get_by_style(style)
    else:
        items = repo.list()
    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start:start + page_size]

    result = TemplateListResponse(
        items=[TemplateResponse(
            id=t.id, name=t.name, visual_style=t.visual_style,
            description=t.description, preview_url=None,
        ) for t in page_items],
        total=total,
    )
    set_cached(cache_key, result.model_dump(mode="json"), ttl=3600)
    return result
