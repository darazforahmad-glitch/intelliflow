"""One error format for the whole API (Section 2.3.1):

    {"error": {"code": "...", "message": "...", "hint": "...", "details": ..., "request_id": "..."}}

Every message is plain language; validation problems come back as 422 with one entry
per field so the web app can show them next to the inputs.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf
from rest_framework.response import Response
from rest_framework.views import set_rollback

from intelliflow.core.errors import AppError
from intelliflow.core.logging import request_id_var

logger = logging.getLogger("intelliflow.api")


def _flatten(errors: Any, prefix: str = "") -> list[dict[str, Any]]:
    """Turn DRF's nested error dict into [{"field": "keys.p256dh", "message": "..."}]."""
    details: list[dict[str, Any]] = []
    if isinstance(errors, dict):
        for key, value in errors.items():
            name = "" if key in {"non_field_errors", drf.ErrorDetail("non_field_errors")} else key
            path = f"{prefix}.{name}" if prefix and name else (prefix or str(name))
            details.extend(_flatten(value, path))
    elif isinstance(errors, list):
        for index, value in enumerate(errors):
            if isinstance(value, dict | list):
                details.extend(_flatten(value, f"{prefix}.{index}" if prefix else str(index)))
            else:
                details.append({"field": prefix or None, "message": str(value)})
    else:
        details.append({"field": prefix or None, "message": str(errors)})
    return details


def _error(status: int, code: str, message: str, **extra: Any) -> Response:
    body: dict[str, Any] = {"code": code, "message": message, **extra}
    request_id = request_id_var.get()
    if request_id:
        body["request_id"] = request_id
    return Response({"error": body}, status=status)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    set_rollback()  # undo the current atomic block, if the view is inside one
    if isinstance(exc, AppError):
        return Response(exc.to_dict(request_id_var.get()), status=exc.status_code)
    if isinstance(exc, drf.ValidationError):
        return _error(
            422, "validation_failed", "Some fields need attention.", details=_flatten(exc.detail)
        )
    if isinstance(exc, drf.ParseError | drf.UnsupportedMediaType):
        return _error(
            422,
            "validation_failed",
            "Some fields need attention.",
            details=[{"field": None, "message": str(exc.detail)}],
        )
    if isinstance(exc, drf.NotAuthenticated | drf.AuthenticationFailed):
        return _error(401, "unauthenticated", "Please sign in to continue.")
    if isinstance(exc, drf.PermissionDenied | DjangoPermissionDenied):
        return _error(403, "forbidden", "You do not have access to this.")
    if isinstance(exc, drf.NotFound | Http404):
        return _error(404, "not_found", "Not found.")
    if isinstance(exc, drf.MethodNotAllowed):
        return _error(405, "method_not_allowed", "Method not allowed.")
    if isinstance(exc, drf.Throttled):
        return _error(429, "rate_limited", "Too many requests. Please wait a moment.")
    if isinstance(exc, drf.APIException):
        return _error(exc.status_code, exc.default_code, str(exc.detail))
    logger.exception("unhandled error", exc_info=exc)
    return _error(500, "internal_error", "Something went wrong on our side. Please try again.")
