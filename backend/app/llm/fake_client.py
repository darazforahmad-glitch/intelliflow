"""FakeLLMClient: deterministic, offline stand-in for the language model (Section 5.2 stubs).

It answers every task from the structured request context using the heuristics in
`app.llm.heuristics`, so the platform works end to end with no API key, no cost and
repeatable results. Recorded responses can be supplied for specific prompts.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from app.llm import heuristics as h
from app.llm.base import LLMClient, LLMRequest, LLMResponse, LLMTask

# ----------------------------------------------------------------------------- interview copy
QUESTIONS: dict[str, dict[str, str]] = {
    "en": {
        "opening": "Assalam o Alaikum! Please describe your {process} step by step, from the moment it starts until it is finished. Who does each step, and which app or tool do you use?",
        "steps": "Thank you! What happens after that? Please tell me the remaining steps, in order, until the {process} is complete.",
        "frequency": "How often does this happen? For example, how many orders do you get in a normal day or week?",
        "duration": "Roughly how many minutes does each step take? For example: {examples}.",
        "app": "Which app or tool do you use for “{step}”? For example WhatsApp, Excel, a register or Gmail.",
        "actor": "Who does “{step}” — you, a staff member, or someone else?",
        "done": "Thank you! I have enough detail to draw your process map. Press “Done” to see it.",
    },
    "roman-ur": {
        "opening": "Assalam o Alaikum! Apna {process} shuru se aakhir tak step by step batayein. Har step kaun karta hai aur kaun si app ya tool use hoti hai?",
        "steps": "Shukriya! Is ke baad kya hota hai? Baqi steps tarteeb se batayein jab tak {process} mukammal na ho jaye.",
        "frequency": "Shukriya! Yeh kaam din ya hafte mein taqreeban kitni baar hota hai? Maslan hafte mein kitne orders aate hain?",
        "duration": "Har step mein taqreeban kitne minute lagte hain? Maslan: {examples}.",
        "app": "“{step}” ke liye aap kaun si app ya tool use karte hain? Maslan WhatsApp, Excel, register ya Gmail.",
        "actor": "“{step}” kaun karta hai — aap khud, staff ya koi aur?",
        "done": "Bohat shukriya! Process map banane ke liye kaafi maloomat mil gayi hai. “Done” dabayein.",
    },
    "ur": {
        "opening": "السلام علیکم! اپنا {process} شروع سے آخر تک مرحلہ وار بتائیں۔ ہر مرحلہ کون کرتا ہے اور کون سی ایپ استعمال ہوتی ہے؟",
        "steps": "شکریہ! اس کے بعد کیا ہوتا ہے؟ باقی مراحل ترتیب سے بتائیں۔",
        "frequency": "یہ کام دن یا ہفتے میں تقریباً کتنی بار ہوتا ہے؟",
        "duration": "ہر مرحلے میں تقریباً کتنے منٹ لگتے ہیں؟ مثلاً: {examples}",
        "app": "“{step}” کے لیے آپ کون سی ایپ یا ٹول استعمال کرتے ہیں؟",
        "actor": "“{step}” کون کرتا ہے؟",
        "done": "بہت شکریہ! نقشہ بنانے کے لیے کافی معلومات مل گئی ہیں۔ “Done” دبائیں۔",
    },
}
# Phrases that identify which topic an earlier question asked about.
_TOPIC_SIGNATURES = {
    "steps": ("what happens after", "is ke baad kya", "اس کے بعد"),
    "frequency": ("how often", "kitni baar", "کتنی بار"),
    "duration": ("how many minutes", "kitne minute", "کتنے منٹ"),
    "app": ("which app", "kaun si app", "کون سی ایپ"),
    "actor": ("who does", "kaun karta hai", "کون کرتا"),
}


def _asked_topics(history: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for message in history:
        if message["sender"] != "ai":
            continue
        text = message["content"].lower()
        for topic, signatures in _TOPIC_SIGNATURES.items():
            if any(sig.lower() in text for sig in signatures):
                counts[topic] = counts.get(topic, 0) + 1
    return counts


def _interview_turn(ctx: dict[str, Any]) -> dict[str, Any]:
    history: list[dict[str, str]] = ctx["history"]
    answers = [m["content"] for m in history if m["sender"] == "user"]
    pref = ctx.get("language_pref") or "en"
    language = (
        h.detect_language(" ".join(answers)) if answers else (pref if pref in QUESTIONS else "en")
    )
    copy_ = QUESTIONS[language]
    process = ctx.get("process_name") or "process"
    if not answers:
        return {
            "status": "need_more_detail",
            "question": copy_["opening"].format(process=process),
            "language": language,
            "missing": ["steps"],
        }

    steps, global_runs = h.extract_steps(answers)
    work = [s for s in steps if s.step_type not in {"start", "end"}]
    asked = _asked_topics(history)
    missing: list[str] = []
    if len(work) < 2:
        missing.append("steps")
    if global_runs is None and not all(s.runs_per_week for s in work):
        missing.append("frequency")
    no_minutes = [s for s in work if s.minutes_per_run is None]
    if no_minutes:
        missing.append("duration")
    no_app = [s for s in work if s.app == "other" and s.step_type == "manual"]
    if no_app:
        missing.append("app")

    for topic in missing:
        limit = 2 if topic == "steps" else 1
        if asked.get(topic, 0) >= limit:
            continue
        if topic == "steps":
            question = copy_["steps"].format(process=process)
        elif topic == "frequency":
            question = copy_["frequency"]
        elif topic == "duration":
            examples = ", ".join(s.title.lower() for s in no_minutes[:3])
            question = copy_["duration"].format(examples=examples)
        else:
            question = copy_["app"].format(step=no_app[0].title)
        return {
            "status": "need_more_detail",
            "question": question,
            "language": language,
            "missing": missing,
        }
    return {
        "status": "enough_detail",
        "question": copy_["done"],
        "language": language,
        "missing": [],
    }


def _process_map(ctx: dict[str, Any]) -> dict[str, Any]:
    answers = [m["content"] for m in ctx["transcript"] if m["sender"] == "user"]
    language = ctx.get("language") or h.detect_language(" ".join(answers))
    steps, global_runs = h.extract_steps(answers)
    result: dict[str, Any] = {
        "process_name": ctx.get("process_name") or "Process",
        "language": language,
        "steps": [],
    }
    if not steps:
        return result
    if steps[0].step_type != "start":
        steps.insert(
            0,
            h.DraftStep(
                title=f"{result['process_name']} starts",
                actor="Customer",
                action="The process is triggered.",
                step_type="start",
                app=steps[0].app,
                kind=None,
            ),
        )
    if steps[-1].step_type != "end":
        steps.append(
            h.DraftStep(
                title=f"{result['process_name']} complete",
                actor="Owner",
                action="The process is finished.",
                step_type="end",
                app="none",
                kind=None,
            )
        )
    runs_default = (
        global_runs or next((s.runs_per_week for s in steps if s.runs_per_week), None) or 20
    )
    previous: str | None = None
    for index, step in enumerate(steps, start=1):
        key = f"s{index}"
        is_event = step.step_type in {"start", "end"}
        kind = h.KIND_BY_CODE.get(step.kind or "")
        minutes = (
            0.0
            if is_event
            else (
                step.minutes_per_run
                if step.minutes_per_run is not None
                else (kind.default_minutes if kind else 2.0)
            )
        )
        result["steps"].append(
            {
                "key": key,
                "title": step.title[:150],
                "actor": step.actor,
                "action": step.action[:1000],
                "step_type": step.step_type,
                "app": step.app if step.app in _APPS else "other",
                "minutes_per_run": float(minutes),
                "runs_per_week": int(step.runs_per_week or runs_default),
                "predecessor": previous,
                "involves_customer_messaging": bool(step.customer_messaging),
                "involves_money": bool(step.money),
            }
        )
        previous = key
    return result


_APPS = {
    "whatsapp",
    "excel",
    "google_sheets",
    "gmail",
    "paper",
    "phone",
    "webform",
    "website",
    "bank",
    "courier",
    "pos",
    "other",
    "none",
}

# ----------------------------------------------------------------------------- classification
_LEXICON: dict[str, set[str]] = {
    "order": {
        "order",
        "chahiye",
        "chahye",
        "chaiye",
        "bhejdo",
        "book",
        "buy",
        "kharidna",
        "want",
        "need",
        "size",
        "qty",
        "quantity",
        "piece",
        "pcs",
        "kurta",
        "kurtay",
        "kurti",
        "shirt",
        "suit",
        "dress",
        "address",
        "cod",
        "item",
        "items",
        "deliver",
        "parcel",
        "medium",
        "large",
        "small",
    },
    "question": {
        "kya",
        "kitne",
        "kitna",
        "price",
        "rate",
        "available",
        "kab",
        "when",
        "how",
        "what",
        "kaise",
        "kahan",
        "details",
        "info",
        "information",
        "batayein",
        "bataen",
        "hai?",
    },
    "inquiry": {
        "kya",
        "kitne",
        "price",
        "rate",
        "available",
        "details",
        "info",
        "information",
        "quote",
        "question",
    },
    "complaint": {
        "complaint",
        "shikayat",
        "kharab",
        "damaged",
        "wrong",
        "ghalat",
        "late",
        "der",
        "refund",
        "return",
        "wapas",
        "problem",
        "masla",
        "broken",
        "missing",
    },
    "payment": {
        "payment",
        "paid",
        "transfer",
        "jazzcash",
        "easypaisa",
        "screenshot",
        "receipt",
        "raqam",
        "paisay",
        "bhej",
        "diye",
        "sent",
        "tid",
        "trx",
    },
    "spam": {"lottery", "prize", "win", "winner", "click", "offer", "free", "congratulations"},
}


def _classify(ctx: dict[str, Any]) -> dict[str, Any]:
    text = str(ctx.get("text") or "")
    words = set(h.tokens(text))
    labels: list[str] = ctx["labels"]
    scores: dict[str, float] = {}
    for label in labels:
        lexicon = _LEXICON.get(label, set()) | {label}
        score = float(len(words & lexicon))
        if label == "question" and "?" in text:
            score += 1.5
        if (
            label == "order"
            and re.search(r"\b\d+\s*(?:x\s*)?[a-z]+", text.lower())
            and words & _LEXICON["order"]
        ):
            score += 1
        scores[label] = score
    best = max(labels, key=lambda label: (scores[label], -labels.index(label)))
    if scores[best] == 0:
        best = "other" if "other" in labels else labels[-1]
        return {"label": best, "confidence": 0.5, "reason": "No strong signal for any label."}
    confidence = min(0.97, 0.6 + 0.1 * scores[best])
    return {
        "label": best,
        "confidence": round(confidence, 2),
        "reason": f"Matched {int(scores[best])} '{best}' signal(s).",
    }


# ----------------------------------------------------------------------------- extraction
_COLOURS = {
    "black": "Black",
    "kala": "Black",
    "kaala": "Black",
    "white": "White",
    "safaid": "White",
    "safed": "White",
    "red": "Red",
    "laal": "Red",
    "lal": "Red",
    "blue": "Blue",
    "neela": "Blue",
    "nila": "Blue",
    "green": "Green",
    "hara": "Green",
    "yellow": "Yellow",
    "peela": "Yellow",
    "pink": "Pink",
    "gulabi": "Pink",
    "maroon": "Maroon",
    "grey": "Grey",
    "gray": "Grey",
    "brown": "Brown",
    "purple": "Purple",
    "orange": "Orange",
    "beige": "Beige",
    "navy": "Navy",
    "golden": "Golden",
    "silver": "Silver",
    "skin": "Skin",
}
_SIZES = {
    "xs": "XS",
    "s": "S",
    "small": "S",
    "m": "M",
    "medium": "M",
    "l": "L",
    "large": "L",
    "xl": "XL",
    "xxl": "XXL",
    "extra large": "XL",
}
_CITIES = [
    "Lahore",
    "Karachi",
    "Islamabad",
    "Rawalpindi",
    "Faisalabad",
    "Multan",
    "Peshawar",
    "Quetta",
    "Sialkot",
    "Gujranwala",
    "Hyderabad",
    "Bahawalpur",
    "Sargodha",
    "Abbottabad",
]
_ITEM_FILLER = {
    "chahiye",
    "chahye",
    "chaiye",
    "chahiyen",
    "bhej",
    "bhejdo",
    "do",
    "dein",
    "please",
    "plz",
    "hai",
    "hain",
}
_ITEM_STOP = {
    "rs",
    "rupay",
    "rupees",
    "rupaye",
    "pkr",
    "min",
    "minute",
    "minutes",
    "din",
    "days",
    "day",
    "baje",
    "hafte",
    "week",
    "size",
    "number",
    "no",
    "house",
    "street",
    "gali",
    "block",
    "sector",
    "phase",
}


def _money(text: str) -> float | None:
    patterns = [
        r"(?:total|amount|price|bill|payment|raqam)\s*(?:is|hai|:|-|=|of)?\s*(?:rs\.?|pkr)?\s*(\d[\d,]*(?:\.\d+)?)",
        r"(?:rs\.?|pkr)\s*(\d[\d,]*(?:\.\d+)?)",
        r"(\d[\d,]*(?:\.\d+)?)\s*(?:rs|rupay|rupees|rupaye|pkr|/-)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def _field_value(name: str, text: str, ctx: dict[str, Any]) -> Any:
    lower = text.lower()
    n = name.lower()
    if n in {"customer_name", "name", "full_name", "sender_name"}:
        match = re.search(
            r"(?:my name is|i am|i'm|mera naam|naam)\s*[:\-]?\s*([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)",
            text,
        )
        return match.group(1) if match else ctx.get("sender_name")
    if n in {"amount", "total", "price", "payment_amount", "order_total"}:
        return _money(text)
    if n in {"size"}:
        match = re.search(
            r"\b(extra large|xxl|xl|xs|small|medium|large|[sml])\b(?:\s*size)?", lower
        )
        if match and (
            match.group(1) not in {"s", "m", "l"}
            or re.search(r"\bsize\s*[:\-]?\s*[sml]\b|\b[sml]\s*size\b", lower)
        ):
            return _SIZES.get(match.group(1), match.group(1).upper())
        return None
    if n in {"colour", "color"}:
        for word in h.tokens(text):
            if word in _COLOURS:
                return _COLOURS[word]
        return None
    if n in {"address", "delivery_address", "customer_address"}:
        match = re.search(
            r"(?:address|adress|pata)\s*(?:is|hai|:|-)?\s*(.+?)(?:[.\n]|,?\s*(?:total|amount|rs\.?\s|phone|number|$))",
            text,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip(" ,:-")
        match = re.search(
            r"((?:house|h\s?#|flat|plot|street|gali)\b.+?)(?:[.\n]|,\s*(?:total|amount|rs)|$)",
            text,
            re.IGNORECASE,
        )
        return match.group(1).strip(" ,") if match else None
    if n in {"phone", "phone_number", "mobile", "contact"}:
        match = re.search(r"(?:\+?92|0)3\d{2}[\s-]?\d{7}", text)
        return match.group(0).replace(" ", "").replace("-", "") if match else None
    if n in {"email", "email_address"}:
        match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
        return match.group(0) if match else None
    if n in {"items", "item", "product", "products"}:
        match = re.search(
            r"\b(\d{1,3})\s*(?:x\s*)?([a-zA-Z][a-zA-Z]+(?:\s(?!size|colou?r|rang)[a-zA-Z]+)?)", text
        )
        if match and match.group(2).lower().split()[0] not in _ITEM_STOP:
            words = [
                w
                for w in match.group(2).split()
                if w.lower() not in _ITEM_FILLER
                and w.lower() not in _SIZES
                and w.lower() not in _COLOURS
            ]
            return f"{match.group(1)} {' '.join(words)}".strip()
        match = re.search(
            r"(?:mujhe|i want|i need|chahiye)\s+([a-zA-Z ]{3,40}?)(?:\s+chahiye|[,.]|$)",
            text,
            re.IGNORECASE,
        )
        return match.group(1).strip() if match else None
    if n in {"quantity", "qty"}:
        match = re.search(
            r"\b(\d{1,3})\s*(?:x\s*)?(?:pcs|pieces|piece|kurt|shirt|suit|dress|item|[a-z]{3,})",
            lower,
        )
        return int(match.group(1)) if match else None
    if n in {"order_id", "order_number"}:
        match = re.search(
            r"order\s*(?:id|no\.?|number|#)\s*[:\-#]?\s*([A-Za-z0-9-]{3,})", text, re.IGNORECASE
        )
        return match.group(1) if match else None
    if n in {"tracking_number", "tracking", "cn_number"}:
        match = re.search(
            r"(?:tracking|cn|consignment)\s*(?:no\.?|number|#|id)?\s*(?:is|hai|:|-)?\s*([A-Za-z0-9-]{6,})",
            text,
            re.IGNORECASE,
        )
        return match.group(1) if match else None
    if n in {"transaction_id", "tid", "trx_id"}:
        match = re.search(
            r"(?:tid|trx|transaction\s*(?:id|no\.?)?)\s*[:\-#]?\s*([A-Za-z0-9-]{6,})",
            text,
            re.IGNORECASE,
        )
        return match.group(1) if match else None
    if n in {"payment_method", "method"}:
        for method in (
            "jazzcash",
            "easypaisa",
            "bank transfer",
            "raast",
            "cod",
            "cash on delivery",
        ):
            if method in lower:
                return method.title() if method not in {"cod"} else "COD"
        return None
    if n == "city":
        return next((c for c in _CITIES if c.lower() in lower), None)
    if n in {"subject", "summary", "question", "message", "topic"}:
        first = re.split(r"(?<=[.!?])\s+", text.strip())[0]
        return first[:200] if first else None
    return None


def _coerce(value: Any, type_: str) -> Any:
    if value is None:
        return None
    try:
        if type_ == "number":
            return float(value)
        if type_ == "integer":
            return int(float(value))
        if type_ == "boolean":
            return bool(value)
    except (TypeError, ValueError):
        return None
    return str(value)


def _extract(ctx: dict[str, Any]) -> dict[str, Any]:
    text = str(ctx.get("text") or "")
    values: dict[str, Any] = {}
    missing: list[str] = []
    required = 0
    for field in ctx["fields"]:
        value = _coerce(_field_value(field["name"], text, ctx), field.get("type", "string"))
        values[field["name"]] = value
        if field.get("required"):
            required += 1
            if value in (None, ""):
                missing.append(field["name"])
    confidence = (
        0.95 if not required else round(0.55 + 0.4 * (required - len(missing)) / required, 2)
    )
    return {"fields": values, "missing": missing, "confidence": confidence}


# ----------------------------------------------------------------------------- replies & summaries
def _draft_reply(ctx: dict[str, Any]) -> dict[str, Any]:
    requested = ctx.get("language")
    language: str = (
        requested if isinstance(requested, str) and requested in {"en", "ur", "roman-ur"} else "en"
    )
    facts = {k: v for k, v in (ctx.get("facts") or {}).items() if v not in (None, "", "None")}
    name = facts.get("customer_name") or facts.get("name") or ""
    instructions = str(ctx.get("instructions") or "").lower()
    if "tracking" in instructions or "tracking_number" in facts:
        texts = {
            "roman-ur": f"Assalam o Alaikum {name}! Aap ka order courier ko de diya gaya hai. Tracking number: {facts.get('tracking_number', '-')}. Shukriya!",
            "en": f"Hi {name}, your order has been handed to the courier. Tracking number: {facts.get('tracking_number', '-')}. Thank you!",
            "ur": f"السلام علیکم {name}! آپ کا آرڈر کورئیر کے حوالے کر دیا گیا ہے۔ ٹریکنگ نمبر: {facts.get('tracking_number', '-')}۔ شکریہ!",
        }
    elif "item" in " ".join(facts) or "amount" in facts or "order" in instructions:
        parts = [str(facts[k]) for k in ("items", "size", "colour", "color") if k in facts]
        summary = ", ".join(parts)
        amount = facts.get("amount") or facts.get("total")
        amount_text = (
            f"{float(amount):,.0f}"
            if amount is not None
            and (isinstance(amount, int | float) or str(amount).replace(".", "", 1).isdigit())
            else amount
        )
        texts = {
            "roman-ur": f"Assalam o Alaikum {name}! Aap ka order mil gaya hai{': ' + summary if summary else ''}."
            + (f" Total Rs {amount_text}." if amount else "")
            + " Hum jald hi dispatch kar denge. Shukriya!",
            "en": f"Hi {name}, thank you for your order{': ' + summary if summary else ''}."
            + (f" Total: Rs {amount_text}." if amount else "")
            + " We will dispatch it soon.",
            "ur": f"السلام علیکم {name}! آپ کا آرڈر موصول ہو گیا ہے۔"
            + (f" کل رقم: {amount_text} روپے۔" if amount else "")
            + " شکریہ!",
        }
    else:
        texts = {
            "roman-ur": f"Assalam o Alaikum {name}! Aap ke message ka shukriya. Hum jald hi jawab denge.",
            "en": f"Hi {name}, thank you for your message. We will get back to you shortly.",
            "ur": f"السلام علیکم {name}! آپ کے پیغام کا شکریہ۔ ہم جلد جواب دیں گے۔",
        }
    return {
        "text": re.sub(r"\s{2,}", " ", texts[language]).replace(" !", "!").strip(),
        "language": language,
    }


def _summarize(ctx: dict[str, Any]) -> dict[str, Any]:
    raw = str(ctx.get("input_text") or "")
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError:
        rows = None
    if isinstance(rows, list):
        amounts = [
            _money(f"rs {r.get('Amount') or r.get('amount') or ''}")
            for r in rows
            if isinstance(r, dict)
        ]
        total = sum(a for a in amounts if a)
        return {"text": f"{len(rows)} record(s) today. Total amount: Rs {total:,.0f}."}
    return {"text": (raw[:300] + "…") if len(raw) > 300 else raw or "Nothing to report today."}


# ----------------------------------------------------------------------------- builder
def _workflow_fill(ctx: dict[str, Any]) -> dict[str, Any]:
    definition = copy.deepcopy(ctx["template_definition"])
    workspace = ctx.get("workspace") or {}
    step = ctx.get("step") or {}
    settings = definition.setdefault("settings", {})
    language = workspace.get("language_pref") or settings.get("language") or "en"
    threshold = float(
        workspace.get("approval_threshold") or settings.get("approval_threshold") or 10000
    )
    settings["language"] = language
    settings["approval_threshold"] = threshold
    if step.get("minutes_per_run"):
        settings["estimated_minutes_saved"] = round(
            float(step["minutes_per_run"]) * float(step.get("fit", 1)), 1
        )
    for block in definition.get("blocks", []):
        if block.get("type") == "approval" and block.get("kind") == "money" and block.get("when"):
            block["when"] = re.sub(r">\s*\d+(?:\.\d+)?", f"> {threshold:g}", block["when"])
        if block.get("type") == "ai.draft_reply":
            block["language"] = language
    return definition


def _workflow_repair(ctx: dict[str, Any]) -> dict[str, Any]:
    """Apply the deterministic fix for each known validator error code."""
    definition = copy.deepcopy(ctx["definition"])
    blocks: list[dict[str, Any]] = definition.get("blocks", [])
    threshold = float((ctx.get("workspace") or {}).get("approval_threshold") or 10000)
    for error in ctx.get("errors", []):
        code = error.get("code")
        details = error.get("details") or {}
        if code == "missing_money_approval":
            after = details.get("after")
            index = next(
                (i for i, b in enumerate(blocks) if b.get("key") == after), len(blocks) - 1
            )
            blocks.insert(
                index + 1,
                {
                    "key": f"{after}_amount_check" if after else "amount_check",
                    "type": "approval",
                    "kind": "money",
                    "title": "Large amount needs approval",
                    "when": f"{after}.{details.get('field', 'amount')} > {threshold:g}",
                    "message": "This order is above your approval amount. Please check it before it is saved.",
                },
            )
        elif code == "unguarded_customer_message":
            position = next(
                (i for i, b in enumerate(blocks) if b.get("key") == details.get("block")), None
            )
            if position is not None:
                action = blocks[position]
                blocks[position] = {
                    "key": action["key"],
                    "type": "approval",
                    "kind": "customer_message",
                    "title": action.get("title") or "Send message to customer?",
                    "proposed_action": {
                        "connector": action.get("connector"),
                        "operation": action.get("operation"),
                        "params": action.get("params", {}),
                    },
                    "editable": ["text"],
                }
        elif code == "duplicate_key":
            seen: set[str] = set()
            for block in blocks:
                key = block.get("key", "")
                while key in seen:
                    key = f"{key}_2"
                block["key"] = key
                seen.add(key)
        elif code == "unexpected_property":
            target: Any = definition
            path = list(error.get("path") or [])
            for part in path[:-1]:
                target = target[part] if isinstance(target, list | dict) else None
            if isinstance(target, dict) and path:
                target.pop(path[-1], None)
    definition["blocks"] = blocks
    return definition


_HANDLERS: dict[LLMTask, Callable[[dict[str, Any]], dict[str, Any]]] = {
    LLMTask.INTERVIEW_TURN: _interview_turn,
    LLMTask.PROCESS_MAP: _process_map,
    LLMTask.CLASSIFY: _classify,
    LLMTask.EXTRACT: _extract,
    LLMTask.DRAFT_REPLY: _draft_reply,
    LLMTask.SUMMARIZE: _summarize,
    LLMTask.WORKFLOW_FILL: _workflow_fill,
    LLMTask.WORKFLOW_REPAIR: _workflow_repair,
}


def recording_key(request: LLMRequest) -> str:
    raw = json.dumps(
        {"task": request.task.value, "messages": request.messages},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class FakeLLMClient(LLMClient):
    provider = "fake"
    model = "intelliflow-fake-1"

    def __init__(self, recordings: dict[str, dict[str, Any]] | None = None) -> None:
        self.recordings = recordings or {}
        self.calls: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        data = self.recordings.get(recording_key(request))
        if data is None:
            data = _HANDLERS[request.task](request.context)
        prompt_chars = len(request.system) + sum(len(m["content"]) for m in request.messages)
        return LLMResponse(
            data=copy.deepcopy(data),
            provider=self.provider,
            model=self.model,
            input_tokens=prompt_chars // 4,
            output_tokens=len(json.dumps(data, ensure_ascii=False)) // 4,
        )


ScriptItem = dict[str, Any] | Exception | Callable[[LLMRequest], dict[str, Any]]


class ScriptedLLMClient(LLMClient):
    """Test double: returns queued responses per task, falling back to FakeLLMClient."""

    provider = "scripted"
    model = "scripted-1"

    def __init__(self, script: dict[LLMTask, list[ScriptItem]] | None = None) -> None:
        self.script = {task: list(items) for task, items in (script or {}).items()}
        self.fallback = FakeLLMClient()
        self.calls: list[LLMRequest] = []

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        queue = self.script.get(request.task)
        if not queue:
            return self.fallback.generate(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        data = item(request) if callable(item) else item
        return LLMResponse(
            data=copy.deepcopy(data),
            provider=self.provider,
            model=self.model,
            input_tokens=10,
            output_tokens=10,
        )
