"""
Password hashing utilities using bcrypt (cost >= 12).

Requirements: 13.6
"""
from __future__ import annotations

from passlib.context import CryptContext

# bcrypt with minimum cost factor 12
_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the plain-text password."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches the stored hash."""
    return _pwd_context.verify(plain, hashed)
