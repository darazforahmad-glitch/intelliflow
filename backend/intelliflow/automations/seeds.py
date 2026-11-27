"""Template library shared by every workspace (Section 2.6 'Reuse', REQ-PA-1).

Each template is a complete, valid workflow definition built only from the approved
block library. `match` drives template matching in Algorithm 5.2: a step matches a
template when one of its keywords appears; it is an exact fit (1.0) when the step's
app is one the template works with, otherwise a partial fit (0.6).
"""

from __future__ import annotations

from typing import Any

from django.db import transaction

from intelliflow.automations.models import Template

ORDER_FIELDS = [
    {"name": "customer_name", "type": "string", "required": True, "description": "Customer's name"},
    {
        "name": "items",
        "type": "string",
        "required": True,
        "description": "Products and quantities ordered",
    },
    {"name": "size", "type": "string", "description": "Size, if mentioned"},
    {"name": "colour", "type": "string", "description": "Colour, if mentioned"},
    {"name": "address", "type": "string", "required": True, "description": "Delivery address"},
    {"name": "amount", "type": "number", "required": True, "description": "Order total in rupees"},
]

TEMPLATE_LIBRARY: list[dict[str, Any]] = [
    {
        "code": "whatsapp_order_entry",
        "name": "Order entry from WhatsApp",
        "category": "orders",
        "description": "Reads each WhatsApp order, adds it to your Orders sheet, flags large orders and drafts a confirmation you approve with one tap.",
        "required_connections": ["whatsapp", "google_sheets"],
        "match": {
            "apps": ["whatsapp", "excel", "google_sheets", "paper"],
            "keywords": [
                "copy",
                "entry",
                "enter",
                "record",
                "likh",
                "likhta",
                "note",
                "register",
                "darj",
                "excel",
                "sheet",
                "details",
            ],
        },
        "definition": {
            "schema_version": 1,
            "name": "Order entry from WhatsApp",
            "description": "Saves WhatsApp orders to the Orders sheet and confirms them with the customer.",
            "trigger": {
                "type": "whatsapp.message_received",
                "filters": {"message_types": ["text"]},
            },
            "blocks": [
                {
                    "key": "is_order",
                    "type": "ai.classify",
                    "title": "Is this an order?",
                    "input": "{{trigger.text}}",
                    "labels": ["order", "question", "other"],
                    "instructions": "An order names at least one product the customer wants to buy.",
                },
                {
                    "key": "only_orders",
                    "type": "condition",
                    "title": "Continue only for orders",
                    "if": "is_order.label == 'order'",
                    "else": "stop",
                },
                {
                    "key": "details",
                    "type": "ai.extract",
                    "title": "Read the order details",
                    "input": "{{trigger.text}}",
                    "fields": ORDER_FIELDS,
                },
                {
                    "key": "big_order",
                    "type": "approval",
                    "kind": "money",
                    "title": "Large order needs approval",
                    "when": "details.amount > 10000",
                    "message": "Order of Rs {{details.amount}} from {{details.customer_name}} is above your approval amount.",
                    "show": ["trigger.text", "details"],
                },
                {
                    "key": "save_row",
                    "type": "action",
                    "title": "Add to the Orders sheet",
                    "connector": "google_sheets",
                    "operation": "append_row",
                    "params": {
                        "sheet": "Orders",
                        "values": {
                            "Date": "{{run.date}}",
                            "Customer": "{{details.customer_name}}",
                            "Phone": "{{trigger.from}}",
                            "Items": "{{details.items}}",
                            "Size": "{{details.size}}",
                            "Colour": "{{details.colour}}",
                            "Address": "{{details.address}}",
                            "Amount": "{{details.amount}}",
                            "Status": "New",
                        },
                    },
                },
                {
                    "key": "reply",
                    "type": "ai.draft_reply",
                    "title": "Draft a confirmation",
                    "instructions": "Confirm the order politely, repeat the items and the total, and say it will be dispatched soon.",
                    "language": "auto",
                    "input": "{{trigger.text}}",
                    "facts": {
                        "customer_name": "{{details.customer_name}}",
                        "items": "{{details.items}}",
                        "size": "{{details.size}}",
                        "colour": "{{details.colour}}",
                        "amount": "{{details.amount}}",
                    },
                },
                {
                    "key": "confirm",
                    "type": "approval",
                    "kind": "customer_message",
                    "title": "Send this confirmation?",
                    "show": ["trigger.text", "details"],
                    "proposed_action": {
                        "connector": "whatsapp",
                        "operation": "send_text",
                        "params": {"to": "{{trigger.from}}", "text": "{{reply.text}}"},
                    },
                    "editable": ["text"],
                },
            ],
            "settings": {
                "estimated_minutes_saved": 3,
                "approval_threshold": 10000,
                "language": "en",
            },
        },
    },
    {
        "code": "payment_screenshot_check",
        "name": "Payment check from WhatsApp",
        "category": "payments",
        "description": "When a customer says they have paid, finds their order, asks you to confirm the amount and marks the order as paid.",
        "required_connections": ["whatsapp", "google_sheets"],
        "match": {
            "apps": ["whatsapp", "bank"],
            "keywords": [
                "payment",
                "screenshot",
                "jazzcash",
                "easypaisa",
                "transfer",
                "verify",
                "raqam",
                "paisay",
                "paid",
            ],
        },
        "definition": {
            "schema_version": 1,
            "name": "Payment check from WhatsApp",
            "trigger": {
                "type": "whatsapp.message_received",
                "filters": {"message_types": ["text", "image"]},
            },
            "blocks": [
                {
                    "key": "is_payment",
                    "type": "ai.classify",
                    "title": "Is this a payment message?",
                    "input": "{{trigger.text}}",
                    "labels": ["payment", "order", "question", "other"],
                },
                {
                    "key": "only_payments",
                    "type": "condition",
                    "title": "Continue only for payments",
                    "if": "is_payment.label == 'payment'",
                    "else": "stop",
                },
                {
                    "key": "payment",
                    "type": "ai.extract",
                    "title": "Read the payment details",
                    "input": "{{trigger.text}}",
                    "fields": [
                        {
                            "name": "amount",
                            "type": "number",
                            "required": True,
                            "description": "Amount paid in rupees",
                        },
                        {
                            "name": "payment_method",
                            "type": "string",
                            "description": "JazzCash, Easypaisa, bank transfer...",
                        },
                        {
                            "name": "transaction_id",
                            "type": "string",
                            "description": "Transaction or TID number",
                        },
                    ],
                },
                {
                    "key": "find_order",
                    "type": "action",
                    "title": "Find the customer's open order",
                    "connector": "google_sheets",
                    "operation": "find_rows",
                    "params": {
                        "sheet": "Orders",
                        "match": {"Phone": "{{trigger.from}}", "Status": "New"},
                    },
                },
                {
                    "key": "order_found",
                    "type": "condition",
                    "title": "Stop if no open order",
                    "if": "find_order.count > 0",
                    "else": "stop",
                },
                {
                    "key": "check_amount",
                    "type": "approval",
                    "kind": "money",
                    "title": "Confirm this payment?",
                    "message": "Customer says they paid Rs {{payment.amount}} ({{payment.payment_method}}). Order total: Rs {{find_order.first.Amount}}.",
                    "show": ["trigger.text", "payment", "find_order.first"],
                    "proposed_action": {
                        "connector": "google_sheets",
                        "operation": "update_row",
                        "params": {
                            "sheet": "Orders",
                            "row_number": "{{find_order.first.row_number}}",
                            "values": {
                                "Status": "Paid",
                                "Paid": "{{payment.amount}}",
                                "Transaction": "{{payment.transaction_id}}",
                            },
                        },
                    },
                },
                {
                    "key": "thanks",
                    "type": "ai.draft_reply",
                    "title": "Draft a thank-you",
                    "instructions": "Thank the customer and confirm the payment was received.",
                    "language": "auto",
                    "facts": {"amount": "{{payment.amount}}"},
                },
                {
                    "key": "send_thanks",
                    "type": "approval",
                    "kind": "customer_message",
                    "title": "Send this message?",
                    "proposed_action": {
                        "connector": "whatsapp",
                        "operation": "send_text",
                        "params": {"to": "{{trigger.from}}", "text": "{{thanks.text}}"},
                    },
                    "editable": ["text"],
                },
            ],
            "settings": {
                "estimated_minutes_saved": 2,
                "approval_threshold": 10000,
                "language": "en",
            },
        },
    },
    {
        "code": "order_confirmation_reply",
        "name": "Order confirmation message",
        "category": "customer messages",
        "description": "Drafts a polite confirmation for every WhatsApp order, ready for you to send with one tap.",
        "required_connections": ["whatsapp"],
        "match": {
            "apps": ["whatsapp"],
            "keywords": ["confirmation", "confirm", "tasdeeq", "reply", "jawab", "shukriya"],
        },
        "definition": {
            "schema_version": 1,
            "name": "Order confirmation message",
            "trigger": {
                "type": "whatsapp.message_received",
                "filters": {"message_types": ["text"]},
            },
            "blocks": [
                {
                    "key": "is_order",
                    "type": "ai.classify",
                    "title": "Is this an order?",
                    "input": "{{trigger.text}}",
                    "labels": ["order", "question", "other"],
                },
                {
                    "key": "only_orders",
                    "type": "condition",
                    "title": "Continue only for orders",
                    "if": "is_order.label == 'order'",
                    "else": "stop",
                },
                {
                    "key": "details",
                    "type": "ai.extract",
                    "title": "Read the order",
                    "input": "{{trigger.text}}",
                    "fields": [
                        {"name": "customer_name", "type": "string"},
                        {"name": "items", "type": "string", "required": True},
                        {"name": "amount", "type": "number"},
                    ],
                },
                {
                    "key": "reply",
                    "type": "ai.draft_reply",
                    "title": "Draft a confirmation",
                    "instructions": "Confirm the order politely and repeat what was ordered.",
                    "language": "auto",
                    "facts": {
                        "customer_name": "{{details.customer_name}}",
                        "items": "{{details.items}}",
                        "amount": "{{details.amount}}",
                    },
                },
                {
                    "key": "confirm",
                    "type": "approval",
                    "kind": "customer_message",
                    "title": "Send this confirmation?",
                    "show": ["trigger.text"],
                    "proposed_action": {
                        "connector": "whatsapp",
                        "operation": "send_text",
                        "params": {"to": "{{trigger.from}}", "text": "{{reply.text}}"},
                    },
                    "editable": ["text"],
                },
            ],
            "settings": {"estimated_minutes_saved": 1.5, "language": "en"},
        },
    },
    {
        "code": "courier_tracking_update",
        "name": "Courier tracking update",
        "category": "delivery",
        "description": "Reads courier booking e-mails, updates the order in your sheet and sends the tracking number to the customer.",
        "required_connections": ["gmail", "google_sheets", "whatsapp"],
        "match": {
            "apps": ["courier", "whatsapp", "gmail"],
            "keywords": [
                "tracking",
                "courier",
                "dispatch",
                "tcs",
                "leopards",
                "trax",
                "postex",
                "booking",
                "cn",
            ],
        },
        "definition": {
            "schema_version": 1,
            "name": "Courier tracking update",
            "trigger": {
                "type": "gmail.message_received",
                "filters": {"subject_contains": "booking"},
            },
            "blocks": [
                {
                    "key": "booking",
                    "type": "ai.extract",
                    "title": "Read the booking e-mail",
                    "input": "{{trigger.subject}}\n{{trigger.body}}",
                    "fields": [
                        {"name": "tracking_number", "type": "string", "required": True},
                        {
                            "name": "phone",
                            "type": "string",
                            "required": True,
                            "description": "Customer phone number",
                        },
                        {"name": "customer_name", "type": "string"},
                    ],
                },
                {
                    "key": "find_order",
                    "type": "action",
                    "title": "Find the order",
                    "connector": "google_sheets",
                    "operation": "find_rows",
                    "params": {"sheet": "Orders", "match": {"Phone": "{{booking.phone}}"}},
                },
                {
                    "key": "order_found",
                    "type": "condition",
                    "title": "Stop if the order is not in the sheet",
                    "if": "find_order.count > 0",
                    "else": "stop",
                },
                {
                    "key": "mark_dispatched",
                    "type": "action",
                    "title": "Mark the order as dispatched",
                    "connector": "google_sheets",
                    "operation": "update_row",
                    "params": {
                        "sheet": "Orders",
                        "row_number": "{{find_order.first.row_number}}",
                        "values": {
                            "Status": "Dispatched",
                            "Tracking": "{{booking.tracking_number}}",
                        },
                    },
                },
                {
                    "key": "reply",
                    "type": "ai.draft_reply",
                    "title": "Draft the tracking message",
                    "instructions": "Tell the customer their order is dispatched and give the tracking number.",
                    "language": "auto",
                    "facts": {
                        "customer_name": "{{booking.customer_name}}",
                        "tracking_number": "{{booking.tracking_number}}",
                    },
                },
                {
                    "key": "notify_customer",
                    "type": "approval",
                    "kind": "customer_message",
                    "title": "Send the tracking number?",
                    "proposed_action": {
                        "connector": "whatsapp",
                        "operation": "send_text",
                        "params": {
                            "to": "{{booking.phone}}",
                            "text": "{{reply.text}}",
                            "fallback_template": "order_dispatched",
                            "template_variables": [
                                "{{booking.customer_name}}",
                                "{{booking.tracking_number}}",
                            ],
                        },
                    },
                    "editable": ["text"],
                },
            ],
            "settings": {"estimated_minutes_saved": 4, "language": "en"},
        },
    },
    {
        "code": "email_inquiry_log",
        "name": "Log e-mail inquiries",
        "category": "customer messages",
        "description": "Sorts new e-mails, logs inquiries in a sheet and drafts replies for your approval.",
        "required_connections": ["gmail", "google_sheets"],
        "match": {
            "apps": ["gmail"],
            "keywords": ["email", "mail", "inquiry", "query", "reply", "jawab", "inbox"],
        },
        "definition": {
            "schema_version": 1,
            "name": "Log e-mail inquiries",
            "trigger": {"type": "gmail.message_received"},
            "blocks": [
                {
                    "key": "kind",
                    "type": "ai.classify",
                    "title": "What kind of e-mail is it?",
                    "input": "{{trigger.subject}}\n{{trigger.body}}",
                    "labels": ["inquiry", "order", "complaint", "spam", "other"],
                },
                {
                    "key": "not_spam",
                    "type": "condition",
                    "title": "Ignore spam",
                    "if": "kind.label != 'spam'",
                    "else": "stop",
                },
                {
                    "key": "info",
                    "type": "ai.extract",
                    "title": "Summarise the e-mail",
                    "input": "{{trigger.body}}",
                    "fields": [
                        {"name": "customer_name", "type": "string"},
                        {"name": "summary", "type": "string", "required": True},
                        {"name": "phone", "type": "string"},
                    ],
                },
                {
                    "key": "log_row",
                    "type": "action",
                    "title": "Log it in the Inquiries sheet",
                    "connector": "google_sheets",
                    "operation": "append_row",
                    "params": {
                        "sheet": "Inquiries",
                        "values": {
                            "Date": "{{run.date}}",
                            "From": "{{trigger.from}}",
                            "Subject": "{{trigger.subject}}",
                            "Type": "{{kind.label}}",
                            "Summary": "{{info.summary}}",
                        },
                    },
                },
                {
                    "key": "reply",
                    "type": "ai.draft_reply",
                    "title": "Draft a reply",
                    "instructions": "Thank them for the e-mail and answer briefly; say the team will follow up.",
                    "language": "auto",
                    "input": "{{trigger.body}}",
                    "facts": {"customer_name": "{{info.customer_name}}"},
                },
                {
                    "key": "send_reply",
                    "type": "approval",
                    "kind": "customer_message",
                    "title": "Send this reply?",
                    "proposed_action": {
                        "connector": "gmail",
                        "operation": "send_email",
                        "params": {
                            "to": "{{trigger.from}}",
                            "subject": "Re: {{trigger.subject}}",
                            "body": "{{reply.text}}",
                        },
                    },
                    "editable": ["body", "subject"],
                },
            ],
            "settings": {"estimated_minutes_saved": 3, "language": "en"},
        },
    },
    {
        "code": "webform_lead_capture",
        "name": "Website form leads",
        "category": "leads",
        "description": "Saves every website form submission to a Leads sheet and prepares a WhatsApp welcome message.",
        "required_connections": ["webform", "google_sheets", "whatsapp"],
        "match": {
            "apps": ["webform", "website"],
            "keywords": ["form", "lead", "website", "registration", "appointment", "signup"],
        },
        "definition": {
            "schema_version": 1,
            "name": "Website form leads",
            "trigger": {"type": "webform.submitted"},
            "blocks": [
                {
                    "key": "save_lead",
                    "type": "action",
                    "title": "Add to the Leads sheet",
                    "connector": "google_sheets",
                    "operation": "append_row",
                    "params": {
                        "sheet": "Leads",
                        "values": {
                            "Date": "{{run.date}}",
                            "Name": "{{trigger.fields.name}}",
                            "Phone": "{{trigger.fields.phone}}",
                            "Email": "{{trigger.fields.email}}",
                            "Message": "{{trigger.fields.message}}",
                        },
                    },
                },
                {
                    "key": "welcome",
                    "type": "ai.draft_reply",
                    "title": "Draft a welcome message",
                    "instructions": "Welcome the new lead and say the team will contact them soon.",
                    "language": "auto",
                    "facts": {"customer_name": "{{trigger.fields.name}}"},
                },
                {
                    "key": "send_welcome",
                    "type": "approval",
                    "kind": "customer_message",
                    "title": "Send the welcome message?",
                    "proposed_action": {
                        "connector": "whatsapp",
                        "operation": "send_text",
                        "params": {
                            "to": "{{trigger.fields.phone}}",
                            "text": "{{welcome.text}}",
                            "fallback_template": "lead_welcome",
                            "template_variables": ["{{trigger.fields.name}}"],
                        },
                    },
                    "editable": ["text"],
                },
            ],
            "settings": {"estimated_minutes_saved": 3, "language": "en"},
        },
    },
    {
        "code": "daily_order_summary",
        "name": "Daily order summary",
        "category": "reports",
        "description": "Every evening, e-mails you a short summary of the day's orders from your sheet.",
        "required_connections": ["google_sheets", "gmail"],
        "match": {
            "apps": ["excel", "google_sheets", "paper"],
            "keywords": [
                "summary",
                "report",
                "hisaab",
                "hisab",
                "daily",
                "count",
                "tally",
                "end of day",
            ],
        },
        "definition": {
            "schema_version": 1,
            "name": "Daily order summary",
            "trigger": {"type": "schedule.daily", "at": "21:00"},
            "blocks": [
                {
                    "key": "today",
                    "type": "action",
                    "title": "Read today's orders",
                    "connector": "google_sheets",
                    "operation": "read_rows",
                    "params": {"sheet": "Orders", "match": {"Date": "{{run.date}}"}},
                },
                {
                    "key": "summary",
                    "type": "ai.summarize",
                    "title": "Summarise the day",
                    "input": "{{today.rows_json}}",
                    "instructions": "Summarise today's orders: how many, the total amount and anything unusual.",
                },
                {
                    "key": "email_owner",
                    "type": "action",
                    "title": "E-mail the summary to you",
                    "connector": "gmail",
                    "operation": "notify_owner",
                    "params": {
                        "subject": "Today's orders ({{run.date}})",
                        "body": "{{summary.text}}",
                    },
                },
            ],
            "settings": {"estimated_minutes_saved": 10, "language": "en"},
        },
    },
]


@transaction.atomic
def seed_templates() -> int:
    """Insert missing template versions (idempotent). Returns the number inserted."""
    inserted = 0
    for spec in TEMPLATE_LIBRARY:
        if Template.objects.filter(code=spec["code"], version=1).exists():
            continue
        Template.objects.create(
            code=spec["code"],
            name=spec["name"],
            category=spec["category"],
            description=spec["description"],
            definition_json=spec["definition"],
            version=1,
            is_active=True,
            match_json=spec["match"],
            required_connections=spec["required_connections"],
        )
        inserted += 1
    return inserted
