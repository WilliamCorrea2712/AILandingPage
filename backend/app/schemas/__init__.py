"""
Pydantic schemas for all API request/response bodies.

Requirements: 9.1, 9.5
"""

from app.schemas.analytics import AnalyticsEvent, AnalyticsResponse, AnalyticsSummary
from app.schemas.error import ErrorResponse
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.schemas.job import JobStatusResponse
from app.schemas.project import ProjectListResponse, ProjectResponse
from app.schemas.publish import PublishRequest, PublishResponse
from app.schemas.template import TemplateListResponse, TemplateResponse
from app.schemas.train import TrainRequest, TrainResponse

__all__ = [
    # generate
    "GenerateRequest",
    "GenerateResponse",
    # train
    "TrainRequest",
    "TrainResponse",
    # publish
    "PublishRequest",
    "PublishResponse",
    # project
    "ProjectResponse",
    "ProjectListResponse",
    # template
    "TemplateResponse",
    "TemplateListResponse",
    # analytics
    "AnalyticsEvent",
    "AnalyticsSummary",
    "AnalyticsResponse",
    # job
    "JobStatusResponse",
    # error
    "ErrorResponse",
]
