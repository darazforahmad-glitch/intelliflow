"""DRF authentication: `Authorization: Bearer <access token>` (Section 3.3.2)."""

from __future__ import annotations

from typing import Any

from rest_framework.request import Request
from rest_framework_simplejwt.authentication import JWTAuthentication as BaseJWTAuthentication

from intelliflow.accounts.models import User
from intelliflow.accounts.tokens import user_from_token


class JWTAuthentication(BaseJWTAuthentication):
    """simplejwt's header parsing plus IntelliFlow's checks: the user must still exist
    and the token's version must match (revoked by "sign out everywhere")."""

    def authenticate(self, request: Request) -> tuple[User, Any] | None:  # type: ignore[override]
        header = self.get_header(request)
        if header is None:
            return None
        raw = self.get_raw_token(header)
        if raw is None:
            return None
        token = raw.decode() if isinstance(raw, bytes) else str(raw)
        return user_from_token(token), token

    def authenticate_header(self, request: Request) -> str:
        return 'Bearer realm="api"'
