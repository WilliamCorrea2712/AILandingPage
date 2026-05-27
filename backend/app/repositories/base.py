"""
Base repository with generic CRUD operations and transaction safety.

Requirements: 14.5
"""
from __future__ import annotations

import logging
from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from app.models.base import Base

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT], session: Session) -> None:
        self._model = model
        self._session = session

    def get(self, id) -> ModelT | None:
        return self._session.get(self._model, id)

    def list(self, **filters) -> list[ModelT]:
        return self._session.query(self._model).filter_by(**filters).all()

    def create(self, **kwargs) -> ModelT:
        obj = self._model(**kwargs)
        try:
            self._session.add(obj)
            self._session.commit()
            self._session.refresh(obj)
            return obj
        except Exception as exc:
            self._session.rollback()
            logger.error("DB write failed (%s.create): %s", self._model.__name__, exc)
            raise

    def update(self, obj: ModelT, **kwargs) -> ModelT:
        try:
            for k, v in kwargs.items():
                setattr(obj, k, v)
            self._session.commit()
            self._session.refresh(obj)
            return obj
        except Exception as exc:
            self._session.rollback()
            logger.error("DB write failed (%s.update): %s", self._model.__name__, exc)
            raise

    def delete(self, obj: ModelT) -> None:
        try:
            self._session.delete(obj)
            self._session.commit()
        except Exception as exc:
            self._session.rollback()
            logger.error("DB write failed (%s.delete): %s", self._model.__name__, exc)
            raise
