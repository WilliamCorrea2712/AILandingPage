"""
Application settings loaded from environment variables using Pydantic Settings.

All critical configuration is centralised here. Values are read from environment
variables (or a .env file when running locally). Sensitive defaults are intentionally
left empty so that the application fails fast if they are not provided.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the WTech Landing Pages backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    DATABASE_URL: str = Field(
        ...,
        description=(
            "PostgreSQL connection string. "
            "Example: postgresql+asyncpg://user:password@localhost:5432/ai_landing"
        ),
    )

    # ------------------------------------------------------------------
    # Redis / Celery broker
    # ------------------------------------------------------------------
    REDIS_URL: str = Field(
        ...,
        description=(
            "Redis connection string used as Celery broker and cache backend. "
            "Example: redis://localhost:6379/0"
        ),
    )

    # ------------------------------------------------------------------
    # Model inference
    # ------------------------------------------------------------------
    MODEL_NAME: Literal["llama3", "mistral", "deepseek", "qwen"] = Field(
        default="llama3",
        description=(
            "Open-source model to use for inference. "
            "Accepted values: llama3, mistral, deepseek, qwen."
        ),
    )

    MODEL_PATH: str = Field(
        default="/models/weights",
        description="Absolute path to the directory containing model weight files.",
    )

    ADAPTER_PATH: str = Field(
        default="/models/adapters",
        description=(
            "Absolute path to the directory containing LoRA/QLoRA adapter checkpoints. "
            "Leave empty to run the base model without a fine-tuned adapter."
        ),
    )

    # ------------------------------------------------------------------
    # Vector database
    # ------------------------------------------------------------------
    VECTOR_DB_PROVIDER: Literal["qdrant", "chromadb", "weaviate"] = Field(
        ...,
        description=(
            "Vector database provider for semantic search. "
            "Accepted values: qdrant, chromadb, weaviate. "
            "The application will refuse to start if this variable is absent or invalid."
        ),
    )

    VECTOR_DB_URL: str = Field(
        ...,
        description=(
            "Base URL of the vector database service. "
            "Examples: http://localhost:6333 (Qdrant), "
            "http://localhost:8000 (ChromaDB), "
            "http://localhost:8080 (Weaviate)."
        ),
    )

    # ------------------------------------------------------------------
    # Security — JWT
    # ------------------------------------------------------------------
    JWT_SECRET: str = Field(
        ...,
        description=(
            "Secret key used to sign and verify JWT tokens. "
            "Must be a long, random string. Never commit the real value to source control."
        ),
        min_length=32,
    )

    JWT_EXPIRY_HOURS: int = Field(
        default=168,
        ge=1,
        le=720,
        description=(
            "JWT token lifetime in hours. "
            "Default: 168h (7 days). Maximum: 720h (30 days)."
        ),
    )

    # ------------------------------------------------------------------
    # Security — CSRF
    # ------------------------------------------------------------------
    CSRF_SECRET: str = Field(
        ...,
        description=(
            "Secret key used to generate and validate CSRF tokens. "
            "Must be a long, random string distinct from JWT_SECRET."
        ),
        min_length=32,
    )

    # ------------------------------------------------------------------
    # Publication / Cloudflare
    # ------------------------------------------------------------------
    PLATFORM_DOMAIN: str = Field(
        ...,
        description=(
            "Root domain of the platform used to build subdomains for published pages. "
            "Example: plataforma.com  →  {slug}.plataforma.com"
        ),
    )

    CLOUDFLARE_API_TOKEN: str = Field(
        default="",
        description=(
            "Cloudflare API token with permissions to manage DNS records and cache rules "
            "for the zone identified by CLOUDFLARE_ZONE_ID. Leave empty to skip CDN integration."
        ),
    )

    CLOUDFLARE_ZONE_ID: str = Field(
        default="",
        description="Cloudflare Zone ID for the domain managed by this platform.",
    )

    # ------------------------------------------------------------------
    # GPU / PyTorch
    # ------------------------------------------------------------------
    CUDA_VISIBLE_DEVICES: str = Field(
        default="0",
        description=(
            "Comma-separated list of GPU indices to expose to PyTorch/CUDA. "
            "Set to '' (empty string) to disable GPU usage and run on CPU only."
        ),
    )

    TORCH_DTYPE: Literal["float16", "bfloat16", "float32"] = Field(
        default="float16",
        description=(
            "PyTorch floating-point precision for model inference and training. "
            "Use float16 for RTX 4090, bfloat16 for A100/H100, float32 for CPU-only."
        ),
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------
    @field_validator("VECTOR_DB_PROVIDER", mode="before")
    @classmethod
    def validate_vector_db_provider(cls, value: str) -> str:
        """
        Enforce that VECTOR_DB_PROVIDER is one of the accepted values.
        Raises ValueError (which becomes a startup error) if the value is invalid,
        satisfying Requirements 12.3 and 12.7.
        """
        accepted = {"qdrant", "chromadb", "weaviate"}
        normalised = str(value).strip().lower()
        if normalised not in accepted:
            raise ValueError(
                f"VECTOR_DB_PROVIDER='{value}' is not supported. "
                f"Accepted values: {', '.join(sorted(accepted))}."
            )
        return normalised

    @field_validator("JWT_EXPIRY_HOURS", mode="before")
    @classmethod
    def validate_jwt_expiry(cls, value: int) -> int:
        """Ensure JWT expiry is within reasonable bounds."""
        try:
            hours = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("JWT_EXPIRY_HOURS must be an integer.") from exc
        if hours > 720:
            raise ValueError(f"JWT_EXPIRY_HOURS={hours} exceeds maximum of 720 hours (30 days).")
        return hours


# ---------------------------------------------------------------------------
# Module-level singleton — import this throughout the application.
# ---------------------------------------------------------------------------
settings = Settings()  # type: ignore[call-arg]
