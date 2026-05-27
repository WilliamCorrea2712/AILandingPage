"""Project repository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, session: Session) -> None:
        super().__init__(Project, session)

    def get_by_user(self, user_id, page: int = 1, page_size: int = 20) -> tuple[list[Project], int]:
        q = self._session.query(Project).filter_by(user_id=user_id)
        total = q.count()
        items = q.order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total
