"""Direct-to-database builders for unit tests of the engine and services."""

from __future__ import annotations

import copy
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Automation, AutomationVersion, Connection, Membership, User, Workspace
from app.models.enums import (
    AutomationStatus,
    ConnectionMode,
    ConnectionProvider,
    MembershipRole,
    MembershipStatus,
)
from app.seeds.templates import TEMPLATE_LIBRARY


def make_workspace(db: Session, **overrides: Any) -> tuple[Workspace, User]:
    user = User(
        full_name="Ayesha Khan",
        email=f"owner-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("Secret123"),
        email_verified=True,
    )
    workspace = Workspace(
        name="Ayesha Boutique",
        language_pref="roman-ur",
        ai_credit_limit=1000,
        approval_threshold=Decimal("10000"),
        **overrides,
    )
    db.add_all([user, workspace])
    db.flush()
    db.add(
        Membership(
            user_id=user.id,
            workspace_id=workspace.id,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
    )
    db.commit()
    return workspace, user


def make_connection(
    db: Session, workspace: Workspace, provider: str, *, phone_number_id: str = "PNID-1"
) -> Connection:
    config: dict[str, Any] = {}
    if provider == "whatsapp":
        config = {"phone_number_id": phone_number_id, "display_phone_number": "+92 300 0000000"}
    connection = Connection(
        workspace_id=workspace.id,
        provider=ConnectionProvider(provider),
        mode=ConnectionMode.SANDBOX,
        config_json=config,
        display_name=f"Sandbox {provider}",
    )
    db.add(connection)
    db.commit()
    return connection


def template_definition(code: str) -> dict[str, Any]:
    spec = next(t for t in TEMPLATE_LIBRARY if t["code"] == code)
    return copy.deepcopy(spec["definition"])


def make_automation(
    db: Session,
    workspace: Workspace,
    definition: dict[str, Any],
    *,
    status: AutomationStatus = AutomationStatus.ACTIVE,
    minutes: str = "3",
) -> Automation:
    automation = Automation(
        workspace_id=workspace.id,
        name=definition["name"],
        status=status,
        trigger_type=definition["trigger"]["type"],
        estimated_minutes_per_run=Decimal(minutes),
    )
    db.add(automation)
    db.flush()
    version = AutomationVersion(
        automation_id=automation.id,
        version_no=1,
        definition_json=definition,
        validated=True,
        test_passed=True,
    )
    db.add(version)
    db.flush()
    automation.current_version_id = version.id
    db.commit()
    db.refresh(automation)
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
