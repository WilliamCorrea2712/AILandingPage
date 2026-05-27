"""
SQLAlchemy ORM models — exports all models so that ``Base.metadata``
is fully populated when this package is imported (e.g. by Alembic).

Requirements: 14.1, 14.2
"""

from app.models.ai_generation import AIGeneration
from app.models.analytics import Analytics
from app.models.base import Base
from app.models.component import Component
from app.models.project import Project
from app.models.prompt import Prompt
from app.models.publication import Publication
from app.models.template import Template
from app.models.training_data import TrainingData
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Prompt",
    "Project",
    "AIGeneration",
    "Template",
    "Component",
    "TrainingData",
    "Analytics",
    "Publication",
]
