"""The demo workspace: a full order-entry journey built through the real code paths.

Creates demo@intelliflow.pk with the "Ayesha Boutique" workspace: a Roman Urdu interview,
its map and opportunities, an active "Order entry from WhatsApp" automation, three rounds
of signed WhatsApp orders through the webhook gateway, approvals for the first two
rounds and a week of run history (timestamps spread out; clearly demo data).
"""

from __future__ import annotations

import random
import uuid
from datetime import timedelta

from django.conf import settings

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


DEMO_PASSWORD = "Demo12345"  # noqa: S105 - the public demo account


def build_demo(email: str = "demo@intelliflow.pk", password: str = DEMO_PASSWORD) -> bool:
    """Returns False when the demo user already exists (nothing is changed)."""
    from config.celery import app as celery_app
    from intelliflow.accounts.models import User
    from intelliflow.approvals import services as approval_service
    from intelliflow.approvals.models import ApprovalTask
    from intelliflow.automations.builder import AutomationBuilder
    from intelliflow.automations.seeds import seed_templates
    from intelliflow.core.enums import ApprovalStatus, ConnectionProvider, RunStatus
    from intelliflow.core.models import utcnow
    from intelliflow.flowmapper.interview_agent import InterviewAgent
    from intelliflow.flowmapper.process_mapper import ProcessMapper
    from intelliflow.integrations import services as connection_service
    from intelliflow.integrations.gateway import ingest_whatsapp
    from intelliflow.integrations.webhooks import build_whatsapp_payload, sign
    from intelliflow.llm.service import AIService
    from intelliflow.opportunities.analyzer import OpportunityAnalyzer
    from intelliflow.opportunities.models import Opportunity
    from intelliflow.runs.models import Run
    from intelliflow.workspaces import services as workspace_service

    celery_app.conf.task_always_eager = True  # run everything in-process for the demo
    seed_templates()
    email = email.strip().lower()
    if User.objects.filter(email=email).exists():
        return False
    owner = User.objects.create_user(
        email, password, full_name="Ayesha Khan", phone="+923001234567", email_verified=True
    )
    workspace, _ = workspace_service.create_workspace(
        owner,
        {
            "name": "Ayesha Boutique",
            "business_type": "Online clothing seller",
            "language_pref": "roman-ur",
        },
    )
    for provider in (
        ConnectionProvider.WHATSAPP,
        ConnectionProvider.GOOGLE_SHEETS,
        ConnectionProvider.GMAIL,
    ):
        connection_service.create_sandbox(workspace, owner, provider)

    ai = AIService(workspace)
    agent = InterviewAgent(workspace, ai)
    session = agent.start(owner, "Order process")
    for answer in DEMO_ANSWERS:
        session = agent.answer(session, answer)
    process_map = ProcessMapper(ai).build(
        session,
        owner,
        on_stored=lambda pm: OpportunityAnalyzer().analyze(pm, workspace.approval_threshold),
    )
    opportunity = next(
        o
        for o in Opportunity.objects.filter(process_map=process_map).select_related("template")
        if o.template and o.template.code == "whatsapp_order_entry"
    )
    builder = AutomationBuilder(workspace, owner, ai)
    automation = builder.generate_from_opportunity(opportunity)
    builder.test(automation, {"text": DEMO_ORDERS[0][2], "name": DEMO_ORDERS[0][0]})
    builder.activate(automation)

    whatsapp = next(
        c
        for c in connection_service.list_connections(workspace.id)
        if c.provider == ConnectionProvider.WHATSAPP
    )
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
            ingest_whatsapp(raw, sign(raw, settings.WHATSAPP_APP_SECRET))
        # approve most of what is waiting, leave the last round pending for the PWA demo
        if round_no < rounds - 1:
            pending = ApprovalTask.objects.filter(
                workspace=workspace, status=ApprovalStatus.PENDING
            ).values_list("id", flat=True)
            for task_id in list(pending):
                task = ApprovalTask.objects.get(pk=task_id)
                if task.status != ApprovalStatus.PENDING:
                    continue
                approval_service.decide(task, owner, "approve")
                # big orders open a second approval: approve it too
                for follow in ApprovalTask.objects.filter(
                    run_id=task.run_id, status=ApprovalStatus.PENDING
                ):
                    approval_service.decide(follow, owner, "approve")

    # spread finished runs across the last week so the chart has a shape (clearly demo data)
    rng = random.Random(7)  # noqa: S311 - spreads demo timestamps, not security related
    for run in Run.objects.filter(workspace=workspace, is_test=False, status=RunStatus.SUCCEEDED):
        shift = timedelta(days=rng.randint(0, 6), hours=rng.randint(0, 8))
        run.created_at = run.created_at - shift
        run.started_at = run.created_at
        run.finished_at = (run.finished_at or utcnow()) - shift
        run.save(update_fields=["created_at", "started_at", "finished_at"])
    return True
