"""Web-form connector: a unique, secret webhook URL per form that accepts JSON or form data (REQ-IN-4)."""

from __future__ import annotations

from app.connectors.base import Connector


class WebformConnector(Connector):
    provider = "webform"
    label = "Web form"
    operations = {}  # trigger-only
