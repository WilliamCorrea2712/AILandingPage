"""Smoke tests for system startup. Requirements: 12.3, 12.7, 2.2"""
import pytest


def test_vector_db_provider_validation():
    """VECTOR_DB_PROVIDER must reject invalid values at startup."""
    import os
    from unittest.mock import patch

    with patch.dict(os.environ, {"VECTOR_DB_PROVIDER": "invalid_provider"}):
        from importlib import reload
        import app.config as cfg
        reload(cfg)
        from app.services import vector_db as vdb
        reload(vdb)
        with pytest.raises(SystemExit):
            vdb.get_vector_db_client()


def test_exceptions_module_importable():
    """All exception classes must be importable."""
    from app.exceptions import (
        AppError, PromptTooShortError, PromptTooLongError,
        GenerationFailedError, RenderError, InvalidJWTError,
        RateLimitExceededError, CSRFValidationError,
    )
    assert issubclass(PromptTooShortError, AppError)
    assert PromptTooShortError.http_status == 400
    assert InvalidJWTError.http_status == 401


def test_config_has_required_fields():
    """Settings must expose all required configuration fields."""
    from app.config import settings
    required = [
        "DATABASE_URL", "REDIS_URL", "MODEL_NAME", "MODEL_PATH",
        "ADAPTER_PATH", "VECTOR_DB_PROVIDER", "VECTOR_DB_URL",
        "JWT_SECRET", "JWT_EXPIRY_HOURS", "CSRF_SECRET", "PLATFORM_DOMAIN",
    ]
    for field in required:
        assert hasattr(settings, field), f"Missing config field: {field}"
