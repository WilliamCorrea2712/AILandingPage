"""
Redis cache layer with PostgreSQL fallback.

Requirements: 14.3, 14.6
"""
from __future__ import annotations

import json
import logging
from typing import Any

import redis as redis_lib

from app.config import settings

logger = logging.getLogger(__name__)

_redis: redis_lib.Redis | None = None


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def get_cached(key: str) -> Any | None:
    """Return cached value or None if not found / Redis unavailable."""
    try:
        r = _get_redis()
        raw = r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("Redis unavailable (get): %s. Falling back to DB.", exc)
        return None


def set_cached(key: str, value: Any, ttl: int = 300) -> None:
    """
    Store value in Redis with TTL (seconds).
    TTL must be between 60 and 3600 seconds.
    Silently skips if Redis is unavailable.
    """
    ttl = max(60, min(ttl, 3600))
    try:
        r = _get_redis()
        r.setex(key, ttl, json.dumps(value, default=str))
    except Exception as exc:
        logger.warning("Redis unavailable (set): %s. Cache write skipped.", exc)


def invalidate(key: str) -> None:
    """Delete a cache key. Silently skips if Redis is unavailable."""
    try:
        r = _get_redis()
        r.delete(key)
    except Exception as exc:
        logger.warning("Redis unavailable (delete): %s. Cache invalidation skipped.", exc)


def invalidate_pattern(pattern: str) -> None:
    """Delete all keys matching a pattern. Use with care."""
    try:
        r = _get_redis()
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except Exception as exc:
        logger.warning("Redis unavailable (pattern delete): %s.", exc)
