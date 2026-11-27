"""Shared fixtures. Tests run on SQLite by default (fast) or on PostgreSQL when
TEST_DATABASE_URL is set (CI does this), with Celery in eager mode and the
FakeLLMClient (config/settings_test.py), so the whole suite is deterministic and free.

Every test is transactional: work really commits, so `transaction.on_commit` hooks
(Celery dispatch, live events) run exactly as in production."""

from __future__ import annotations

import json as jsonlib
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from rest_framework.test import APIClient

from intelliflow.core.kv import MemoryStore, get_kv, reset_kv
from intelliflow.notifications.models import EmailMessage


@pytest.fixture(autouse=True)
def _database(transactional_db: None) -> Iterator[None]:
    yield
    kv = get_kv()
    if isinstance(kv, MemoryStore):
        kv.clear()


@pytest.fixture(scope="session", autouse=True)
def _memory_kv() -> None:
    reset_kv()


@pytest.fixture(autouse=True)
def _templates(_database: None) -> None:
    from intelliflow.automations.seeds import seed_templates

    seed_templates()


class Response:
    """httpx-style view of a Django test response (status_code, json(), text, headers)."""

    def __init__(self, response: Any) -> None:
        self._response = response
        self.status_code: int = response.status_code
        self.headers = response.headers

    @property
    def content(self) -> bytes:
        if getattr(self._response, "streaming", False):
            return b"".join(self._response.streaming_content)
        return bytes(self._response.content)

    @property
    def text(self) -> str:
        return self.content.decode()

    def json(self) -> Any:
        return jsonlib.loads(self.content or b"null")


class Client:
    """Small wrapper so tests read like HTTP calls: client.post(url, json=..., headers=...)."""

    def __init__(self) -> None:
        self.api = APIClient()

    @staticmethod
    def _extra(headers: dict[str, str] | None) -> dict[str, str]:
        extra = {}
        for key, value in (headers or {}).items():
            name = key.upper().replace("-", "_")
            extra[name if name == "CONTENT_TYPE" else f"HTTP_{name}"] = value
        return extra

    def request(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Response:
        call = getattr(self.api, method.lower())
        extra = self._extra(headers)
        content_type = extra.pop("CONTENT_TYPE", None)
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}{'&' if '?' in url else '?'}{query}"
        if content is not None:
            body = content.encode() if isinstance(content, str) else content
            return Response(
                call(url, body, content_type=content_type or "application/octet-stream", **extra)
            )
        if data is not None:
            return Response(call(url, data, **extra))  # form-encoded
        if json is not None:
            return Response(call(url, json, format="json", **extra))
        return Response(call(url, **extra))

    def get(self, url: str, **kw: Any) -> Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> Response:
        return self.request("POST", url, **kw)

    def put(self, url: str, **kw: Any) -> Response:
        return self.request("PUT", url, **kw)

    def patch(self, url: str, **kw: Any) -> Response:
        return self.request("PATCH", url, **kw)

    def delete(self, url: str, **kw: Any) -> Response:
        return self.request("DELETE", url, **kw)


@pytest.fixture
def client() -> Client:
    return Client()


def latest_link(to: str, marker: str) -> str:
    """Pull the one-time token out of the newest outbox e-mail (the dev 'inbox')."""
    message = EmailMessage.objects.filter(to_address=to.lower()).order_by("-created_at").first()
    assert message is not None, f"no e-mail sent to {to}"
    for word in message.body_text.split():
        if marker in word:
            return word.split("token=")[1]
    raise AssertionError(f"no '{marker}' link in e-mail: {message.subject}")


class Api:
    """Tiny helper that signs requests as one user inside one workspace."""

    def __init__(self, client: Client, token: str, workspace_id: str) -> None:
        self.client = client
        self.token = token
        self.workspace_id = workspace_id

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def url(self, path: str) -> str:
        return f"/api/v1/workspaces/{self.workspace_id}{path}"

    def get(self, path: str, **kw: Any) -> Response:
        return self.client.get(self.url(path), headers=self.headers, **kw)

    def post(self, path: str, json: Any = None, **kw: Any) -> Response:
        return self.client.post(self.url(path), json=json, headers=self.headers, **kw)

    def put(self, path: str, json: Any = None, **kw: Any) -> Response:
        return self.client.put(self.url(path), json=json, headers=self.headers, **kw)

    def patch(self, path: str, json: Any = None, **kw: Any) -> Response:
        return self.client.patch(self.url(path), json=json, headers=self.headers, **kw)

    def delete(self, path: str, **kw: Any) -> Response:
        return self.client.delete(self.url(path), headers=self.headers, **kw)


def register_and_login(client: Client, email: str | None = None, password: str = "Secret123") -> str:
    email = email or f"owner-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Ayesha Khan",
            "email": email,
            "phone": "+923001234567",
            "password": password,
        },
    )
    assert r.status_code == 201, r.text
    token = latest_link(email, "verify-email")
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


@pytest.fixture
def owner(client: Client) -> Api:
    token = register_and_login(client)
    r = client.post(
        "/api/v1/workspaces",
        json={
            "name": "Ayesha Boutique",
            "business_type": "Online clothing seller",
            "language_pref": "roman-ur",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    return Api(client, token, r.json()["id"])


ORDER_ANSWERS = [
    "Customer WhatsApp pe order bhejta hai. Phir main order details Excel register mein copy karta hoon. "
    "Uske baad payment screenshot check karta hoon. Phir customer ko confirmation message bhejta hoon. "
    "Phir staff order pack karta hai aur main TCS courier book karke tracking number customer ko bhejta hoon. "
    "Aakhir mein order deliver ho jata hai.",
    "Hafte mein taqreeban 40 orders aate hain.",
    "Excel mein copy karne mein 3 minute lagte hain, payment check mein 2 minute, confirmation bhejne mein "
    "1 minute, packing 10 minute aur courier booking 5 minute.",
]


def run_order_interview(api: Api) -> dict[str, Any]:
    """Drive the Flow Mapper interview to completion and return the process map JSON."""
    r = api.post("/interviews", {"process_name": "Order process"})
    assert r.status_code == 201, r.text
    session_id = r.json()["id"]
    for answer in ORDER_ANSWERS:
        r = api.post(f"/interviews/{session_id}/messages", {"content": answer})
        assert r.status_code == 200, r.text
    assert r.json()["ready_for_mapping"] is True
    r = api.post(f"/interviews/{session_id}/complete")
    assert r.status_code == 201, r.text
    return dict(r.json())


def connect_sandbox(api: Api, *providers: str) -> dict[str, dict[str, Any]]:
    created = {}
    for provider in providers:
        r = api.post("/connections/sandbox", {"provider": provider})
        assert r.status_code == 201, r.text
        created[provider] = r.json()
    return created


@pytest.fixture
def llm_override() -> Iterator[Any]:
    from intelliflow.llm import set_llm_client

    holder: dict[str, Any] = {}

    def install(client: Any) -> Any:
        holder["client"] = client
        set_llm_client(client)
        return client

    yield install
    set_llm_client(None)
