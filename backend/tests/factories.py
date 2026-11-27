"""Direct-to-database builders for unit tests of the engine and services."""

from __future__ import annotations

import copy
import uuid
from decimal import Decimal
from typing import Any

from intelliflow.accounts.models import User
from intelliflow.automations.models import Automation, AutomationVersion
from intelliflow.automations.seeds import TEMPLATE_LIBRARY
from intelliflow.core.enums import (
    AutomationStatus,
    ConnectionMode,
    ConnectionProvider,
    MembershipRole,
    MembershipStatus,
)
from intelliflow.integrations.models import Connection
from intelliflow.workspaces.models import Membership, Workspace


def make_workspace(**overrides: Any) -> tuple[Workspace, User]:
    user = User.objects.create_user(
        f"owner-{uuid.uuid4().hex[:6]}@example.com",
        "Secret123",
        full_name="Ayesha Khan",
        email_verified=True,
    )
    workspace = Workspace.objects.create(
        name="Ayesha Boutique",
        language_pref="roman-ur",
        ai_credit_limit=1000,
        approval_threshold=Decimal("10000"),
        **overrides,
    )
    Membership.objects.create(
        user=user, workspace=workspace, role=MembershipRole.OWNER, status=MembershipStatus.ACTIVE
    )
    return workspace, user


def make_connection(
    workspace: Workspace, provider: str, *, phone_number_id: str = "PNID-1"
) -> Connection:
    config: dict[str, Any] = {}
    if provider == "whatsapp":
        config = {"phone_number_id": phone_number_id, "display_phone_number": "+92 300 0000000"}
    return Connection.objects.create(
        workspace=workspace,
        provider=ConnectionProvider(provider),
        mode=ConnectionMode.SANDBOX,
        config_json=config,
        display_name=f"Sandbox {provider}",
    )


def template_definition(code: str) -> dict[str, Any]:
    spec = next(t for t in TEMPLATE_LIBRARY if t["code"] == code)
    return copy.deepcopy(spec["definition"])


def make_automation(
    workspace: Workspace,
    definition: dict[str, Any],
    *,
    status: AutomationStatus = AutomationStatus.ACTIVE,
    minutes: str = "3",
) -> Automation:
    automation = Automation.objects.create(
        workspace=workspace,
        name=definition["name"],
        status=status,
        trigger_type=definition["trigger"]["type"],
        estimated_minutes_per_run=Decimal(minutes),
    )
    version = AutomationVersion.objects.create(
        automation=automation,
        version_no=1,
        definition_json=definition,
        validated=True,
        test_passed=True,
    )
    automation.current_version = version
    automation.save(update_fields=["current_version"])
    automation.refresh_from_db()
    return automation


ORDER_TEXT = (
    "Assalam o alaikum, mujhe 2 kurtay chahiye medium size black colour. "
    "Address: House 12, Street 5, Gulberg Lahore. Total Rs 4500"
)


def whatsapp_trigger(
    text: str = ORDER_TEXT, sender: str = "923001234567", name: str = "Ayesha"
) -> dict[str, Any]:
    from datetime import UTC, datetime

    return {
        "message_id": f"wamid.{uuid.uuid4().hex}",
        "from": sender,
        "name": name,
        "text": text,
        "type": "text",
        "timestamp": datetime.now(UTC).isoformat(),
    }
