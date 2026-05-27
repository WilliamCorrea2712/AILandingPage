"""Template repository."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.template import Template
from app.repositories.base import BaseRepository


class TemplateRepository(BaseRepository[Template]):
    def __init__(self, session: Session) -> None:
        super().__init__(Template, session)

    def get_recent(self, limit: int = 5) -> list[Template]:
        return self._session.query(Template).order_by(Template.created_at.desc()).limit(limit).all()

    def get_by_style(self, style: str) -> list[Template]:
        return self._session.query(Template).filter_by(visual_style=style).all()

    def get_default(self) -> Template | None:
        return self._session.query(Template).filter_by(is_default=True).first()
