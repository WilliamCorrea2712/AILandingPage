"""
Unit tests for JWT authentication and password hashing.

Tests cover:
- Token creation and verification (Task 3.1)
- Password hashing and verification (Task 3.2)
- CSRF token generation and validation (Task 3.3)

Requirements: 13.1, 13.6, 13.3
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_settings(monkeypatch):
    """Provide a minimal settings object so tests don't need a real .env."""
    mock = MagicMock()
    mock.JWT_SECRET = "a" * 32  # minimum 32 chars
    mock.JWT_EXPIRY_HOURS = 24
    mock.CSRF_SECRET = "b" * 32

    monkeypatch.setattr("app.auth.jwt.settings", mock)
    monkeypatch.setattr("app.middleware.csrf.settings", mock)
    return mock


# ---------------------------------------------------------------------------
# Task 3.1 — JWT
# ---------------------------------------------------------------------------


class TestCreateToken:
    def test_returns_non_empty_string(self):
        from app.auth.jwt import create_token

        token = create_token("user-123", "user")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_has_three_parts(self):
        """JWT tokens are three base64url segments separated by dots."""
        from app.auth.jwt import create_token

        token = create_token("user-123", "user")
        assert token.count(".") == 2


class TestVerifyToken:
    def test_valid_token_returns_payload(self):
        from app.auth.jwt import TokenPayload, create_token, verify_token

        token = create_token("user-abc", "admin")
        payload = verify_token(token)

        assert isinstance(payload, TokenPayload)
        assert payload.sub == "user-abc"
        assert payload.role == "admin"

    def test_empty_token_raises_invalid_jwt(self):
        from app.auth.jwt import verify_token
        from app.exceptions import InvalidJWTError

        with pytest.raises(InvalidJWTError):
            verify_token("")

    def test_garbage_token_raises_invalid_jwt(self):
        from app.auth.jwt import verify_token
        from app.exceptions import InvalidJWTError

        with pytest.raises(InvalidJWTError):
            verify_token("not.a.valid.jwt.token")

    def test_tampered_signature_raises_invalid_jwt(self):
        from app.auth.jwt import create_token, verify_token
        from app.exceptions import InvalidJWTError

        token = create_token("user-xyz", "user")
        # Flip the last character of the signature
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

        with pytest.raises(InvalidJWTError):
            verify_token(tampered)

    def test_expired_token_raises_invalid_jwt(self, monkeypatch):
        """Simulate an expired token by patching timedelta to negative."""
        from datetime import timedelta

        from app.auth import jwt as jwt_module
        from app.exceptions import InvalidJWTError

        # Create a token that expired 1 hour ago
        with patch.object(
            jwt_module,
            "timedelta",
            return_value=timedelta(hours=-1),
        ):
            token = jwt_module.create_token("user-exp", "user")

        with pytest.raises(InvalidJWTError):
            jwt_module.verify_token(token)

    def test_wrong_secret_raises_invalid_jwt(self, monkeypatch):
        from app.auth.jwt import create_token, verify_token
        from app.exceptions import InvalidJWTError

        token = create_token("user-123", "user")

        # Change the secret so verification fails
        import app.auth.jwt as jwt_module

        original_secret = jwt_module.settings.JWT_SECRET
        jwt_module.settings.JWT_SECRET = "z" * 32

        try:
            with pytest.raises(InvalidJWTError):
                verify_token(token)
        finally:
            jwt_module.settings.JWT_SECRET = original_secret


# ---------------------------------------------------------------------------
# Task 3.2 — Password hashing
# ---------------------------------------------------------------------------


class TestHashPassword:
    def test_returns_bcrypt_hash(self):
        from app.auth.password import hash_password

        hashed = hash_password("mysecretpassword")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    def test_different_calls_produce_different_hashes(self):
        """bcrypt uses a random salt, so two hashes of the same password differ."""
        from app.auth.password import hash_password

        h1 = hash_password("samepassword")
        h2 = hash_password("samepassword")
        assert h1 != h2

    def test_hash_encodes_cost_factor_12(self):
        from app.auth.password import hash_password

        hashed = hash_password("testpass")
        # bcrypt hash format: $2b$<cost>$...
        parts = hashed.split("$")
        cost = int(parts[2])
        assert cost >= 12


class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        from app.auth.password import hash_password, verify_password

        plain = "correct_horse_battery_staple"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_wrong_password_returns_false(self):
        from app.auth.password import hash_password, verify_password

        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_empty_password_can_be_hashed_and_verified(self):
        from app.auth.password import hash_password, verify_password

        hashed = hash_password("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False


# ---------------------------------------------------------------------------
# Task 3.3 — CSRF token helpers
# ---------------------------------------------------------------------------


class TestCSRFTokenHelpers:
    def test_generate_returns_signed_token(self):
        from app.middleware.csrf import generate_csrf_token

        token = generate_csrf_token()
        assert "." in token
        raw, _, sig = token.partition(".")
        assert len(raw) > 0
        assert len(sig) > 0

    def test_valid_token_passes_validation(self):
        from app.middleware.csrf import generate_csrf_token, validate_csrf_token

        token = generate_csrf_token()
        assert validate_csrf_token(token) is True

    def test_empty_token_fails_validation(self):
        from app.middleware.csrf import validate_csrf_token

        assert validate_csrf_token("") is False

    def test_token_without_dot_fails_validation(self):
        from app.middleware.csrf import validate_csrf_token

        assert validate_csrf_token("nodottoken") is False

    def test_tampered_raw_fails_validation(self):
        from app.middleware.csrf import generate_csrf_token, validate_csrf_token

        token = generate_csrf_token()
        raw, _, sig = token.partition(".")
        tampered = f"TAMPERED{raw}.{sig}"
        assert validate_csrf_token(tampered) is False

    def test_tampered_signature_fails_validation(self):
        from app.middleware.csrf import generate_csrf_token, validate_csrf_token

        token = generate_csrf_token()
        raw, _, sig = token.partition(".")
        tampered = f"{raw}.TAMPERED{sig}"
        assert validate_csrf_token(tampered) is False

    def test_two_tokens_are_different(self):
        """Each call generates a unique token due to random raw value."""
        from app.middleware.csrf import generate_csrf_token

        t1 = generate_csrf_token()
        t2 = generate_csrf_token()
        assert t1 != t2
