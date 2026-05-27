"""
Redis-backed sliding-window rate limiting middleware.

Requirements: 13.5, 9.3
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import redis as redis_lib
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

# Global rate limits
GLOBAL_LIMIT = 100   # requests per minute per authenticated user
GENERATE_LIMIT = 10  # requests per minute for POST /generate

_redis: redis_lib.Redis | None = None


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _sliding_window_check(key: str, limit: int, window: int = 60) -> tuple[bool, int]:
    """
    Returns (allowed, retry_after_seconds).
    Uses a sorted set with timestamps as scores.
    """
    r = _get_redis()
    now = time.time()
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, window)
    results = pipe.execute()
    count = results[2]
    if count > limit:
        oldest = r.zrange(key, 0, 0, withscores=True)
        retry_after = window - int(now - oldest[0][1]) if oldest else window
        return False, max(retry_after, 1)
    return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply per-user rate limiting using Redis sliding window."""

    async def dispatch(self, request: Request, call_next):
        # Identify user by JWT sub or by IP as fallback
        user_id = _extract_user_id(request)

        # Determine applicable limit
        is_generate = (
            request.method == "POST"
            and request.url.path.rstrip("/") in ("/generate", "/api/generate")
        )
        limit = GENERATE_LIMIT if is_generate else GLOBAL_LIMIT
        key = f"rl:{user_id}:{'generate' if is_generate else 'global'}"

        try:
            allowed, retry_after = _sliding_window_check(key, limit)
        except Exception:
            # If Redis is unavailable, allow the request (fail open)
            return await call_next(request)

        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "message": "Limite de requisições excedido. Tente novamente mais tarde.",
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                },
            )

        return await call_next(request)


def _extract_user_id(request: Request) -> str:
    """Extract user identifier from JWT or fall back to client IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            from app.auth.jwt import verify_token
            payload = verify_token(token)
            return f"user:{payload.user_id}"
        except Exception:
            pass
    # Fallback: use client IP
    forwarded = request.headers.get("X-Forwarded-For")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"ip:{ip}"
