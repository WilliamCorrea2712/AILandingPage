"""
Pydantic schemas for the POST /train endpoint.

Requirements: 9.1, 11.2
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TrainRequest(BaseModel):
    """Request body for POST /train (admin only)."""

    source: Literal["api", "database", "url"] = Field(
        ...,
        description="Origin of the training dataset.",
    )
    file_url: str | None = Field(
        default=None,
        description="URL of the dataset file. Required when source='url'.",
        examples=["https://example.com/dataset.jsonl"],
    )
    model_name: Literal["llama3", "mistral", "deepseek", "qwen"] = Field(
        default="llama3",
        description="Base model to fine-tune.",
    )
    technique: Literal["lora", "qlora", "peft"] = Field(
        default="qlora",
        description="Fine-tuning technique to apply.",
    )
    epochs: int = Field(
        default=3,
        ge=1,
        le=100,
        description="Number of training epochs.",
    )
    learning_rate: float = Field(
        default=2e-4,
        gt=0.0,
        lt=1.0,
        description="Learning rate for the optimiser.",
    )

    @model_validator(mode="after")
    def file_url_required_for_url_source(self) -> "TrainRequest":
        if self.source == "url" and not self.file_url:
            raise ValueError("file_url é obrigatório quando source='url'.")
        return self


class TrainResponse(BaseModel):
    """Response body for a successfully enqueued training job (HTTP 202)."""

    job_id: uuid.UUID = Field(..., description="Unique identifier of the training job.")
    status: str = Field(default="pending", description="Initial job status.")
    model_name: str = Field(..., description="Name of the model being fine-tuned.")
    dataset_size: int = Field(
        ...,
        ge=100,
        le=100_000,
        description="Number of examples in the training dataset.",
    )
