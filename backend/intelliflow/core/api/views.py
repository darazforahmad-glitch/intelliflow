"""Liveness and readiness probes for the container platform."""

from __future__ import annotations

from django.db import connection
from django.http import HttpRequest, JsonResponse

from intelliflow.core.kv import RedisStore, get_kv


def healthz(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def readyz(_request: HttpRequest) -> JsonResponse:
    checks: dict[str, str] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    checks["redis"] = "ok" if isinstance(get_kv(), RedisStore) else "memory-fallback"
    healthy = checks["database"] == "ok"
    return JsonResponse(
        {"status": "ok" if healthy else "degraded", **checks}, status=200 if healthy else 503
    )
