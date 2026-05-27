"""
JWT authentication utilities.

Requirements: 13.1, 9.2
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings
from app.exceptions import InvalidJWTError

ALGORITHM = "HS256"


@dataclass
class TokenPayload:
    user_id: str
    role: str
    exp: datetime


def create_token(user_id: str, role: str) -> str:
    """Create a signed JWT token for the given user."""
    expire = datetime.now(tz=timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def verify_token(token: str) -> TokenPayload:
    """Verify and decode a JWT token. Raises InvalidJWTError on failure."""
    try:
        data = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        return TokenPayload(
            user_id=data["sub"],
            role=data.get("role", "user"),
            exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc),
        )
    except JWTError as exc:
        raise InvalidJWTError(f"Token JWT inválido ou expirado: {exc}") from exc


def get_current_user(token: str) -> TokenPayload:
    """Alias for verify_token — used as a FastAPI dependency."""
    return verify_token(token)
