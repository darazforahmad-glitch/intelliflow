"""Session tokens (JWT, djangorestframework-simplejwt).

An access/refresh pair is issued at sign-in; the refresh token is rotated on every
refresh. Each token carries the user's `token_version` ("tv"): "sign out everywhere"
and password resets bump the version, which revokes every token issued before.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from rest_framework_simplejwt.exceptions import ExpiredTokenError, TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken, Token

from intelliflow.accounts.models import User
from intelliflow.core.errors import AuthenticationError

TokenType = Literal["access", "refresh"]


@dataclass(frozen=True, slots=True)
class TokenClaims:
    user_id: uuid.UUID
    token_type: TokenType
    token_version: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int  # seconds until the access token expires


def issue_pair(user: User) -> TokenPair:
    refresh = RefreshToken.for_user(user)
    refresh["tv"] = user.token_version
    access = refresh.access_token  # copies "sub" and "tv"
    expires_in = int(access["exp"]) - int(access["iat"])
    return TokenPair(str(access), str(refresh), expires_in)


def decode_token(raw: str, expected_type: TokenType) -> TokenClaims:
    token_class: type[Token] = AccessToken if expected_type == "access" else RefreshToken
    try:
        token = token_class(raw)  # type: ignore[arg-type]
    except ExpiredTokenError as exc:
        raise AuthenticationError(
            "Your session has expired. Please sign in again.", code="token_expired"
        ) from exc
    except TokenError as exc:
        raise AuthenticationError(
            "Invalid session. Please sign in again.", code="invalid_token"
        ) from exc
    try:
        user_id = uuid.UUID(str(token["sub"]))
        version = int(token["tv"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Invalid session.", code="invalid_token") from exc
    return TokenClaims(
        user_id=user_id,
        token_type=expected_type,
        token_version=version,
        expires_at=datetime.fromtimestamp(int(token["exp"]), UTC),
    )


def user_from_token(raw: str | None, expected_type: TokenType = "access") -> User:
    if not raw:
        raise AuthenticationError("Please sign in to continue.")
    claims = decode_token(raw, expected_type)
    user = User.objects.filter(pk=claims.user_id).first()
    if user is None or user.token_version != claims.token_version:
        raise AuthenticationError(
            "Your session has ended. Please sign in again.", code="session_revoked"
        )
    return user
