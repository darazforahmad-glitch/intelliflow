"""Request context: a request id on every log line and response, security headers,
and one structured log line per request (container health probes excluded)."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponseBase

from intelliflow.core.logging import request_id_var

logger = logging.getLogger("intelliflow.api")

# Container health probes hit these every few seconds; only failures are worth a log line.
PROBE_PATHS = frozenset({"/healthz", "/readyz"})


class RequestContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        incoming = request.headers.get("x-request-id", "")
        request_id = (
            incoming if 8 <= len(incoming) <= 64 and incoming.isascii() else uuid.uuid4().hex
        )
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        response["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.IS_PRODUCTION:
            response["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.path.startswith("/api/v1") and "Cache-Control" not in response:
            response["Cache-Control"] = "no-store"
        if request.path not in PROBE_PATHS or response.status_code >= 400:
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": elapsed_ms,
                    "request_id": request_id,
                },
            )
        return response


def client_ip(request: HttpRequest) -> str | None:
    """The caller's address (the proxy sets X-Forwarded-For in production)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded and not settings.IS_DEV_LIKE:
        return forwarded.split(",")[0].strip()[:45] or None
    address = request.META.get("REMOTE_ADDR")
    return str(address)[:45] if address else None
