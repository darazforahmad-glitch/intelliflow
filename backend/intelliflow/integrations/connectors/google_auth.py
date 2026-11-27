"""Google OAuth 2.0 credentials for Gmail and Sheets (authorization-code flow, REQ-IN-1)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from django.conf import settings

from intelliflow.engine.errors import ConnectionUnavailableError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - public endpoint, not a secret
# Narrowest scopes per provider (SEC-6).
SCOPES = {
    "gmail": ["https://www.googleapis.com/auth/gmail.modify", "openid", "email"],
    "google_sheets": ["https://www.googleapis.com/auth/spreadsheets", "openid", "email"],
}


def authorization_url(provider: str, state: str, redirect_uri: str) -> str:
    query = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES[provider]),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    response = httpx.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    response.raise_for_status()
    return dict(response.json())


def build_credentials(stored: dict[str, Any], save: Callable[[dict[str, Any]], None] | None):  # type: ignore[no-untyped-def]
    """google.oauth2 Credentials that refresh themselves and persist the new token."""
    import google.auth.transport.requests
    from google.auth.exceptions import RefreshError
    from google.oauth2.credentials import Credentials

    expiry = (
        datetime.fromisoformat(stored["expiry"]).astimezone(UTC).replace(tzinfo=None)
        if stored.get("expiry")
        else None
    )
    creds = Credentials(
        token=stored.get("access_token"),
        refresh_token=stored.get("refresh_token"),
        token_uri=TOKEN_URL,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=stored.get("scopes"),
        expiry=expiry,
    )
    if not creds.valid:
        try:
            creds.refresh(google.auth.transport.requests.Request())
        except RefreshError as exc:
            raise ConnectionUnavailableError(
                "Google access has expired or was revoked. Please reconnect your Google account."
            ) from exc
        if save is not None:
            save(
                {
                    **stored,
                    "access_token": creds.token,
                    "expiry": (
                        creds.expiry.replace(tzinfo=UTC).isoformat() if creds.expiry else None
                    ),
                }
            )
    return creds
