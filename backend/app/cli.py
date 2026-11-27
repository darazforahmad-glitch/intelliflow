"""Management commands:  python -m app.cli <command>

seed                         insert the template library (idempotent)
create-admin                 create or promote a platform admin
generate-keys                print fresh SECRET_KEY and ENCRYPTION_KEYS values
generate-vapid               print a VAPID key pair for Web Push
demo                         build a demo workspace through the real code paths
"""

from __future__ import annotations

import argparse
import base64
import random
import secrets
import sys
import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import select


def _seed() -> None:
    from app.core.database import new_session
    from app.seeds.templates import seed_templates

    db = new_session()
    try:
        print(f"Inserted {seed_templates(db)} template(s).")
    finally:
        db.close()


def _create_admin(email: str, name: str, password: str) -> None:
    from app.core.database import new_session
    from app.core.security import hash_password, validate_password_strength
    from app.models import User

    validate_password_strength(password)
    db = new_session()
    try:
        user = db.scalar(select(User).where(User.email == email.lower()))
        if user is None:
            user = User(
                full_name=name,
                email=email.lower(),
                password_hash=hash_password(password),
                email_verified=True,
            )
            db.add(user)
        user.is_platform_admin = True
        db.commit()
        print(f"Platform admin ready: {user.email}")
    finally:
        db.close()


def _generate_keys() -> None:
    from app.core.crypto import generate_key

    print(f"SECRET_KEY={secrets.token_urlsafe(48)}")
    print(f"ENCRYPTION_KEYS=k{secrets.token_hex(2)}:{generate_key()}")


def _generate_vapid() -> None:
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid02

    vapid = Vapid02()
    vapid.generate_keys()
    public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    print(f"VAPID_PUBLIC_KEY={base64.urlsafe_b64encode(public).decode().rstrip('=')}")
    print(f"VAPID_PRIVATE_KEY={base64.urlsafe_b64encode(private).decode().rstrip('=')}")


DEMO_ANSWERS = [
    "Customer WhatsApp pe order bhejta hai. Phir main order details Excel register mein copy karta hoon. "
    "Uske baad payment screenshot check karta hoon. Phir customer ko confirmation message bhejta hoon. "
    "Phir staff order pack karta hai aur main TCS courier book karke tracking number customer ko bhejta hoon. "
    "Aakhir mein order deliver ho jata hai.",
    "Hafte mein taqreeban 40 orders aate hain.",
    "Excel mein copy karne mein 3 minute lagte hain, payment check mein 2 minute, confirmation bhejne mein 1 minute, "
    "packing 10 minute aur courier booking 5 minute.",
]
DEMO_ORDERS = [
    (
        "Ayesha",
        "923001234567",
        "Assalam o alaikum, mujhe 2 kurtay chahiye medium size black colour. Address: House 12, Street 5, Gulberg Lahore. Total Rs 4500",
    ),
    (
        "Bilal",
        "923211112233",
        "Mujhe 1 shirt chahiye large white. Address: Flat 3, Block B, Johar Town Lahore. Total Rs 2200",
    ),
    (
        "Sana",
        "923334445566",
        "AoA, 3 dupattay chahiye pink. Address: House 44, DHA Phase 5 Karachi. Total Rs 3600",
    ),
    (
        "Hamza",
        "923455556677",
        "I want 4 suits medium navy. Address: Street 9, F-10 Islamabad. Total Rs 18,000",
    ),
    (
        "Zara",
        "923016667788",
        "2 kurtis chahiye small maroon. Address: House 2, Model Town Lahore. Total Rs 3100",
    ),
    ("Usman", "923127778899", "Kurta ki price kya hai? Available hai?"),
]


def _demo(email: str, password: str) -> None:
    from app.core.config import get_settings
    from app.core.database import new_session
    from app.core.security import hash_password
    from app.models import ApprovalTask, Run, User
    from app.models.base import utcnow
    from app.models.enums import ApprovalStatus, ConnectionProvider, RunStatus
    from app.schemas.workspace import WorkspaceCreate
    from app.seeds.templates import seed_templates
    from app.services import approval_service, connection_service, workspace_service
    from app.services.ai_service import AIService
    from app.services.automation_builder import AutomationBuilder
    from app.services.interview_agent import InterviewAgent
    from app.services.opportunity_analyzer import OpportunityAnalyzer
    from app.services.process_mapper import ProcessMapper
    from app.services.webhook_gateway import ingest_whatsapp
    from app.services.webhooks import build_whatsapp_payload, sign
    from app.worker.celery_app import celery_app

    celery_app.conf.task_always_eager = True  # run everything in-process for the demo
    db = new_session()
    try:
        seed_templates(db)
        if db.scalar(select(User).where(User.email == email)):
            print(f"Demo user {email} already exists; nothing to do.")
            return
        owner = User(
            full_name="Ayesha Khan",
            email=email,
            phone="+923001234567",
            password_hash=hash_password(password),
            email_verified=True,
        )
        db.add(owner)
        db.commit()
        workspace, _ = workspace_service.create_workspace(
            db,
            owner,
            WorkspaceCreate(
                name="Ayesha Boutique",
                business_type="Online clothing seller",
                language_pref="roman-ur",
            ),
        )
        for provider in (
            ConnectionProvider.WHATSAPP,
            ConnectionProvider.GOOGLE_SHEETS,
            ConnectionProvider.GMAIL,
        ):
            connection_service.create_sandbox(db, workspace, owner, provider)

        ai = AIService(db, workspace)
        agent = InterviewAgent(db, workspace, ai)
        session = agent.start(owner, "Order process")
        for answer in DEMO_ANSWERS:
            session = agent.answer(session, answer)
        process_map = ProcessMapper(db, ai).build(session, owner)
        OpportunityAnalyzer(db).analyze(process_map, workspace.approval_threshold)
        db.commit()
        db.refresh(process_map)

        opportunity = next(
            o
            for o in db.scalars(
                select(Opportunity_cls()).where(Opportunity_cls().map_id == process_map.id)
            )
            if o.template and o.template.code == "whatsapp_order_entry"
        )
        builder = AutomationBuilder(db, workspace, owner, ai)
        automation = builder.generate_from_opportunity(opportunity)
        builder.test(automation, {"text": DEMO_ORDERS[0][2], "name": DEMO_ORDERS[0][0]})
        builder.activate(automation)

        whatsapp = next(
            c
            for c in connection_service.list_connections(db, workspace.id)
            if c.provider == ConnectionProvider.WHATSAPP
        )
        secret = get_settings().whatsapp_app_secret
        rounds = 3
        for round_no in range(rounds):
            for name, phone, text in DEMO_ORDERS:
                raw = build_whatsapp_payload(
                    phone_number_id=whatsapp.config_json["phone_number_id"],
                    wa_id=phone,
                    name=name,
                    text=text,
                    message_id=f"wamid.DEMO{uuid.uuid4().hex}",
                )
                ingest_whatsapp(raw, sign(raw, secret))
            # approve most of what is waiting, leave the last round pending for the PWA demo
            if round_no < rounds - 1:
                db.expire_all()
                pending_ids = db.scalars(
                    select(ApprovalTask.id).where(
                        ApprovalTask.workspace_id == workspace.id,
                        ApprovalTask.status == ApprovalStatus.PENDING,
                    )
                ).all()
                for task_id in pending_ids:
                    db.expire_all()
                    task = db.get_one(ApprovalTask, task_id)
                    if task.status == ApprovalStatus.PENDING:
                        approval_service.decide(db, task, owner, "approve")
                        db.expire_all()
                        # big orders open a second approval: approve it too
                        for follow in db.scalars(
                            select(ApprovalTask).where(
                                ApprovalTask.run_id == task.run_id,
                                ApprovalTask.status == ApprovalStatus.PENDING,
                            )
                        ).all():
                            approval_service.decide(db, follow, owner, "approve")
                            db.expire_all()
        # spread finished runs across the last week so the chart has a shape (clearly demo data)
        db.expire_all()
        finished = db.scalars(
            select(Run).where(
                Run.workspace_id == workspace.id,
                Run.is_test.is_(False),
                Run.status == RunStatus.SUCCEEDED,
            )
        ).all()
        rng = random.Random(7)  # noqa: S311 - spreads demo timestamps, not security related
        for run in finished:
            shift = timedelta(days=rng.randint(0, 6), hours=rng.randint(0, 8))
            run.created_at = run.created_at - shift
            run.started_at = run.created_at
            run.finished_at = (run.finished_at or utcnow()) - shift
        db.commit()
        print("Demo workspace ready.")
        print(f"  Sign in at {get_settings().frontend_url}/login with {email} / {password}")
    finally:
        db.close()


def Opportunity_cls() -> type[Any]:  # noqa: N802 - tiny indirection keeps the import local
    from app.models import Opportunity

    return Opportunity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    admin = sub.add_parser("create-admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", default="Platform Admin")
    admin.add_argument("--password", required=True)
    sub.add_parser("generate-keys")
    sub.add_parser("generate-vapid")
    demo = sub.add_parser("demo")
    demo.add_argument("--email", default="demo@intelliflow.pk")
    demo.add_argument("--password", default="Demo12345")
    args = parser.parse_args(argv)
    if args.command == "seed":
        _seed()
    elif args.command == "create-admin":
        _create_admin(args.email, args.name, args.password)
    elif args.command == "generate-keys":
        _generate_keys()
    elif args.command == "generate-vapid":
        _generate_vapid()
    elif args.command == "demo":
        _demo(args.email.lower(), args.password)
    return 0


if __name__ == "__main__":
    sys.exit(main())
