"""
SQLAlchemy declarative base shared by all ORM models.

Import ``Base`` from this module when defining new models so that
``Base.metadata`` always contains every table and Alembic can detect
schema changes automatically.

Requirements: 14.1
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
