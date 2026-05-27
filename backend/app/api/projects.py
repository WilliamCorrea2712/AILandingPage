"""GET /projects endpoint. Requirements: 14.3"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.auth.jwt import TokenPayload
from app.database import get_db
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectListResponse, ProjectResponse
from app.services.cache import get_cached, set_cached

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=ProjectListResponse)
def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: TokenPayload = Depends(get_current_user),
):
    cache_key = f"projects:{user.user_id}:p{page}:ps{page_size}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    repo = ProjectRepository(db)
    items, total = repo.get_by_user(user.user_id, page=page, page_size=page_size)
    result = ProjectListResponse(
        items=[ProjectResponse(
            id=p.id, name=p.name, slug=p.slug, status=p.status,
            created_at=p.created_at, published_url=None,
        ) for p in items],
        total=total, page=page, page_size=page_size,
    )
    set_cached(cache_key, result.model_dump(mode="json"), ttl=300)
    return result
