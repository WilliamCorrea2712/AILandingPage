"""
CSRF protection middleware for FastAPI.

Requirements: 13.3
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.exceptions import CSRFValidationError

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
CSRF_HEADER = "X-CSRF-Token"
CSRF_COOKIE = "csrf_token"


def _sign(token: str) -> str:
    return hmac.new(
        settings.CSRF_SECRET.encode(),
        token.encode(),
        hashlib.sha256,
    ).hexdigest()


def generate_csrf_token() -> str:
    """Generate a new CSRF token (raw value, not signed)."""
    return secrets.token_urlsafe(32)


def _validate(raw: str, signed: str) -> bool:
    expected = _sign(raw)
    return hmac.compare_digest(expected, signed)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validate CSRF tokens on state-mutating requests (POST, PUT, DELETE)."""

    async def dispatch(self, request: Request, call_next):
        if request.method in _SAFE_METHODS:
            return await call_next(request)

        # Skip CSRF for auth endpoints (login/register) and docs
        path = request.url.path
        if path.startswith("/auth/") or path in ("/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE)
        header_token = request.headers.get(CSRF_HEADER)

        if not cookie_token or not header_token:
            return JSONResponse(
                status_code=403,
                content={
                    "error_code": "CSRF_VALIDATION_ERROR",
                    "message": "Token CSRF ausente.",
                    "timestamp": _utc_now(),
                },
            )

        if not _validate(cookie_token, header_token):
            return JSONResponse(
                status_code=403,
                content={
                    "error_code": "CSRF_VALIDATION_ERROR",
                    "message": "Token CSRF inválido.",
                    "timestamp": _utc_now(),
                },
            )

        return await call_next(request)


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).isoformat()
