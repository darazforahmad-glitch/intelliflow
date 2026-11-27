"""UC-01 Register / Log In and REQ-AC-1..6."""

from __future__ import annotations

from tests.conftest import Client, latest_link, register_and_login


def _register(client: Client, email: str, password: str = "Secret123") -> None:
    r = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Usman Ali", "email": email, "password": password},
    )
    assert r.status_code == 201, r.text


def test_cannot_sign_in_before_email_verification(client: Client) -> None:
    _register(client, "usman@example.com")
    r = client.post(
        "/api/v1/auth/login", json={"email": "usman@example.com", "password": "Secret123"}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "email_not_verified"


def test_full_registration_flow_and_me(client: Client) -> None:
    token = register_and_login(client, email="Hadia@Example.com")
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "hadia@example.com"  # normalised
    assert me["email_verified"] is True
    assert me["memberships"] == []


def test_duplicate_email_rejected(client: Client) -> None:
    _register(client, "dup@example.com")
    r = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Dup", "email": "DUP@example.com", "password": "Secret123"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["hint"]


def test_weak_password_rejected_with_plain_message(client: Client) -> None:
    r = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Weak", "email": "weak@example.com", "password": "password"},
    )
    assert r.status_code == 422
    assert "letter and one number" in r.json()["error"]["message"]


def test_lockout_after_five_failed_attempts(client: Client) -> None:
    register_and_login(client, email="lock@example.com")
    for _ in range(5):
        r = client.post(
            "/api/v1/auth/login", json={"email": "lock@example.com", "password": "Wrong1234"}
        )
        assert r.status_code == 401
    # Even the correct password is refused while the account is locked (REQ-AC-2).
    r = client.post(
        "/api/v1/auth/login", json={"email": "lock@example.com", "password": "Secret123"}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "account_locked"


def test_password_reset_revokes_old_sessions(client: Client) -> None:
    old_token = register_and_login(client, email="reset@example.com")
    assert (
        client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"}).status_code
        == 202
    )
    reset_token = latest_link("reset@example.com", "reset-password")
    r = client.post(
        "/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "NewSecret456"}
    )
    assert r.status_code == 200
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}).status_code
        == 401
    )
    # The link is single-use.
    assert (
        client.post(
            "/api/v1/auth/reset-password", json={"token": reset_token, "new_password": "Another789"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "reset@example.com", "password": "NewSecret456"}
        ).status_code
        == 200
    )


def test_unknown_email_does_not_leak(client: Client) -> None:
    r = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 202
    r = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "Secret123"}
    )
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_refresh_token_flow(client: Client) -> None:
    register_and_login(client, email="refresh@example.com")
    pair = client.post(
        "/api/v1/auth/login", json={"email": "refresh@example.com", "password": "Secret123"}
    ).json()
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert r.status_code == 200
    # An access token cannot be used as a refresh token.
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": pair["access_token"]}
        ).status_code
        == 401
    )
