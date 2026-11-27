"""Shared fixtures. Tests run on SQLite by default (fast) or on PostgreSQL when
TEST_DATABASE_URL is set (CI does this), with Celery in eager mode and the
FakeLLMClient, so the whole suite is deterministic and costs nothing."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

os.environ.setdefault("ENVIRONMENT", "test")
os.environ["LLM_PROVIDER"] = "fake"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["EMAIL_BACKEND"] = "console"
os.environ["REDIS_URL"] = ""
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "1000"

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import reset_settings_cache

reset_settings_cache()

from app.core.database import get_database, init_database  # noqa: E402
from app.core.kv import MemoryStore, get_kv, reset_kv  # noqa: E402
from app.models import Base, EmailMessage  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    db = init_database(os.environ["DATABASE_URL"])
    Base.metadata.drop_all(db.engine)
    Base.metadata.create_all(db.engine)
    yield
    Base.metadata.drop_all(db.engine)


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    yield
    engine = get_database().engine
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    kv = get_kv()
    if isinstance(kv, MemoryStore):
        kv.clear()


@pytest.fixture(scope="session", autouse=True)
def _memory_kv() -> None:
    reset_kv()


@pytest.fixture
def db() -> Iterator[Session]:
    session = get_database().session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def latest_link(db: Session, to: str, marker: str) -> str:
    """Pull the one-time token out of the newest outbox e-mail (the dev 'inbox')."""
    db.expire_all()
    message = db.scalars(
        select(EmailMessage)
        .where(EmailMessage.to_address == to.lower())
        .order_by(EmailMessage.created_at.desc())
    ).first()
    assert message is not None, f"no e-mail sent to {to}"
    for word in message.body_text.split():
        if marker in word:
            return word.split("token=")[1]
    raise AssertionError(f"no '{marker}' link in e-mail: {message.subject}")


class Api:
    """Tiny helper around TestClient that signs requests as one user."""

    def __init__(self, client: TestClient, token: str, workspace_id: str) -> None:
        self.client = client
        self.token = token
        self.workspace_id = workspace_id

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def url(self, path: str) -> str:
        return f"/api/v1/workspaces/{self.workspace_id}{path}"

    def get(self, path: str, **kw: Any) -> Any:
        return self.client.get(self.url(path), headers=self.headers, **kw)

    def post(self, path: str, json: Any = None, **kw: Any) -> Any:
        return self.client.post(self.url(path), json=json, headers=self.headers, **kw)

    def put(self, path: str, json: Any = None, **kw: Any) -> Any:
        return self.client.put(self.url(path), json=json, headers=self.headers, **kw)

    def patch(self, path: str, json: Any = None, **kw: Any) -> Any:
        return self.client.patch(self.url(path), json=json, headers=self.headers, **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self.client.delete(self.url(path), headers=self.headers, **kw)


def register_and_login(
    client: TestClient, db: Session, email: str | None = None, password: str = "Secret123"
) -> str:
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
    token = latest_link(db, email, "verify-email")
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return str(r.json()["access_token"])


@pytest.fixture
def owner(client: TestClient, db: Session) -> Api:
    token = register_and_login(client, db)
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


@pytest.fixture(autouse=True)
def _templates(_database: None) -> None:
    from app.core.database import new_session
    from app.seeds.templates import seed_templates

    session = new_session()
    try:
        seed_templates(session)
    finally:
        session.close()


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
    from app.llm import set_llm_client

    holder: dict[str, Any] = {}

    def install(client: Any) -> Any:
        holder["client"] = client
        set_llm_client(client)
        return client

    yield install
    set_llm_client(None)
