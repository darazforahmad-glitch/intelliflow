"""Password hashing (Argon2id, SEC-1), session tokens (PyJWT) and one-time URL tokens."""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ValidationFailedError

# argon2-cffi defaults to Argon2id with the RFC 9106 low-memory profile.
_hasher = PasswordHasher()
_JWT_ALGORITHM = "HS256"
_PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,128}$")

TokenType = Literal["access", "refresh"]


def validate_password_strength(password: str) -> None:
    if not _PASSWORD_RE.match(password):
        raise ValidationFailedError(
            "Please choose a password of at least 8 characters with at least one letter "
            "and one number.",
            code="weak_password",
        )


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# A pre-computed hash used to keep login timing constant for unknown e-mails.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    verify_password(_DUMMY_HASH, password)


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: uuid.UUID
    token_type: TokenType
    token_version: int
    expires_at: datetime


def _encode(claims: dict[str, Any]) -> str:
    return jwt.encode(claims, get_settings().secret_key, algorithm=_JWT_ALGORITHM)


def create_token(
    user_id: uuid.UUID, token_version: int, token_type: TokenType
) -> tuple[str, datetime]:
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if token_type == "access"  # noqa: S105 - token kind, not a secret
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    expires = now + ttl
    token = _encode(
        {
            "sub": str(user_id),
            "typ": token_type,
            "tv": token_version,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": secrets.token_hex(8),
            "iss": "intelliflow",
        }
    )
    return token, expires


def decode_token(token: str, expected_type: TokenType) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[_JWT_ALGORITHM],
            issuer="intelliflow",
            options={"require": ["sub", "exp", "typ", "tv"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(
            "Your session has expired. Please sign in again.", code="token_expired"
        ) from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError(
            "Invalid session. Please sign in again.", code="invalid_token"
        ) from exc
    if payload.get("typ") != expected_type:
        raise AuthenticationError("Invalid session. Please sign in again.", code="invalid_token")
    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise AuthenticationError("Invalid session.", code="invalid_token") from exc
    return TokenClaims(
        user_id=user_id,
        token_type=expected_type,
        token_version=int(payload["tv"]),
        expires_at=datetime.fromtimestamp(payload["exp"], UTC),
    )


def create_signed_state(data: dict[str, Any], ttl_minutes: int = 15) -> str:
    """Short-lived signed blob, e.g. the OAuth 2.0 `state` parameter (CSRF protection)."""
    now = datetime.now(UTC)
    claims = {
        **data,
        "typ": "state",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
        "nonce": secrets.token_hex(8),
        "iss": "intelliflow",
    }
    return _encode(claims)


def decode_signed_state(state: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            state, get_settings().secret_key, algorithms=[_JWT_ALGORITHM], issuer="intelliflow"
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError(
            "The authorisation request expired. Please try again.", code="invalid_state"
        ) from exc
    if payload.get("typ") != "state":
        raise AuthenticationError("Invalid authorisation state.", code="invalid_state")
    return payload


def generate_url_token() -> tuple[str, str]:
    """Return (token for the URL, SHA-256 hex digest to store)."""
    token = secrets.token_urlsafe(32)
    return token, hash_url_token(token)


def hash_url_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode(), b.encode())
