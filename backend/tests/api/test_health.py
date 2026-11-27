"""Health probes and the request log: container health checks call the probes every few
seconds, so successful probes stay out of the log while failures and real traffic do not."""

from __future__ import annotations

import logging

import pytest

from tests.conftest import Client


def _logged_paths(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        str(getattr(record, "path", ""))
        for record in caplog.records
        if record.name == "intelliflow.api" and record.getMessage() == "request"
    ]


def test_successful_probes_are_not_logged(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="intelliflow.api"):
        assert client.get("/healthz").json() == {"status": "ok"}
        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["database"] == "ok"
        assert client.get("/api/v1/auth/me").status_code == 401  # ordinary traffic

    assert _logged_paths(caplog) == ["/api/v1/auth/me"]


def test_failing_probe_is_logged(
    client: Client, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    class DatabaseDown:
        def cursor(self) -> None:
            raise RuntimeError("database down")

    monkeypatch.setattr("intelliflow.core.api.views.connection", DatabaseDown())
    with caplog.at_level(logging.INFO, logger="intelliflow.api"):
        ready = client.get("/readyz")

    assert ready.status_code == 503
    assert ready.json() == {"status": "degraded", "database": "error", "redis": "memory-fallback"}
    assert _logged_paths(caplog) == ["/readyz"]
