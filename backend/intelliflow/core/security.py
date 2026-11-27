"""Password rules (SEC-1), one-time URL tokens and signed OAuth state.

Password hashing itself is Django's (Argon2id via `PASSWORD_HASHERS`), and session
tokens are JWTs issued by djangorestframework-simplejwt (see accounts/tokens.py).
"""

from __future__ import annotations

import hashlib
import re
import secrets
from typing import Any

from django.contrib.auth.hashers import make_password
from django.core import signing

from intelliflow.core.errors import AuthenticationError, ValidationFailedError

_PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,128}$")
_STATE_SALT = "intelliflow.oauth-state"


def validate_password_strength(password: str) -> None:
    if not _PASSWORD_RE.match(password):
        raise ValidationFailedError(
            "Please choose a password of at least 8 characters with at least one letter "
            "and one number.",
            code="weak_password",
        )


def burn_password_check(password: str) -> None:
    """Hash once for unknown e-mails so login timing does not reveal which accounts exist."""
    make_password(password)


def create_signed_state(data: dict[str, Any]) -> str:
    """Short-lived signed blob, e.g. the OAuth 2.0 `state` parameter (CSRF protection)."""
    return signing.dumps({**data, "nonce": secrets.token_hex(8)}, salt=_STATE_SALT)


def decode_signed_state(state: str, ttl_minutes: int = 15) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = signing.loads(state, salt=_STATE_SALT, max_age=ttl_minutes * 60)
    except signing.SignatureExpired as exc:
        raise AuthenticationError(
            "The authorisation request expired. Please try again.", code="invalid_state"
        ) from exc
    except signing.BadSignature as exc:
        raise AuthenticationError("Invalid authorisation state.", code="invalid_state") from exc
    return payload


def generate_url_token() -> tuple[str, str]:
    """Return (token for the URL, SHA-256 hex digest to store)."""
    token = secrets.token_urlsafe(32)
    return token, hash_url_token(token)


def hash_url_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode(), b.encode())
