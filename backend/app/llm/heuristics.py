"""Lightweight English / Roman Urdu / Urdu text heuristics used by the FakeLLMClient.

They let the full product run offline and deterministically (tests, demos, CI) by
approximating what the language model returns. They are not used when a real
provider is configured.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

ROMAN_URDU_MARKERS = frozenset(
    [
        "hai",
        "hain",
        "hoon",
        "hun",
        "karta",
        "karti",
        "karte",
        "mein",
        "main",
        "ko",
        "ka",
        "ki",
        "ke",
        "phir",
        "fir",
        "aur",
        "nahi",
        "kya",
        "se",
        "par",
        "pe",
        "jata",
        "jati",
        "jaate",
        "wala",
        "wali",
        "bhejta",
        "bhejti",
        "bhejte",
        "bhej",
        "mujhe",
        "humein",
        "apna",
        "apni",
        "taqreeban",
        "hafte",
        "hafta",
        "roz",
        "din",
        "lagte",
        "lagta",
        "baad",
        "pehle",
        "uske",
        "us",
        "aata",
        "aate",
        "aati",
        "liye",
        "kitne",
        "kitna",
        "kaun",
        "hota",
        "hoti",
        "chahiye",
        "karna",
        "karke",
        "deta",
        "deti",
        "dete",
        "leta",
        "leti",
        "lete",
        "ho",
        "gaya",
        "gayi",
        "jaata",
    ]
)
_ARABIC_SCRIPT = re.compile(r"[؀-ۿ]")
_WORD = re.compile(r"[a-z0-9&]+")

ROMAN_NUMBERS = {
    "ek": 1,
    "do": 2,
    "teen": 3,
    "char": 4,
    "chaar": 4,
    "paanch": 5,
    "panch": 5,
    "chay": 6,
    "chhe": 6,
    "saat": 7,
    "aath": 8,
    "nau": 9,
    "das": 10,
    "bees": 20,
    "tees": 30,
    "chalees": 40,
    "pachas": 50,
    "pachaas": 50,
    "sau": 100,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
}


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def tokens(text: str) -> list[str]:
    return _WORD.findall(normalize(text))


def detect_language(text: str) -> str:
    if _ARABIC_SCRIPT.search(text):
        return "ur"
    words = tokens(text)
    if not words:
        return "en"
    hits = sum(1 for w in words if w in ROMAN_URDU_MARKERS)
    return "roman-ur" if hits >= 2 and hits / len(words) >= 0.08 else "en"


def has_any(words: list[str], stems: set[str] | frozenset[str]) -> bool:
    for word in words:
        for stem in stems:
            if word == stem or (len(stem) >= 6 and word.startswith(stem)):
                return True
    return False


# --------------------------------------------------------------------------- clauses
_SPLIT = re.compile(
    r"(?:\n+|(?<=[.!?;])\s+|\s*(?:->|→)\s*|^\s*\d+[.)]\s+|\s+\d+[.)]\s+"
    r"|\b(?:then|after that|afterwards|next|finally|phir|fir|uske baad|us ke baad|is ke baad|iske baad"
    r"|baad mein|aakhir mein|akhir mein|aakhir me|last mein)\b[,]?\s*"
    r"|\b(?:aur|and)\s+(?=(?:main|mein|hum|phir|fir|then|i|we|staff|customer|my)\b))",
    re.IGNORECASE,
)


def split_clauses(text: str) -> list[str]:
    parts = [p.strip(" ,.;:-") for p in _SPLIT.split(text) if p and p.strip(" ,.;:-")]
    return [p for p in parts if len(p) >= 3]


# --------------------------------------------------------------------------- numbers
def _num(value: str) -> float | None:
    value = value.replace(",", "").strip()
    if value in ROMAN_NUMBERS:
        return float(ROMAN_NUMBERS[value])
    try:
        return float(value)
    except ValueError:
        return None


_NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(ROMAN_NUMBERS, key=len, reverse=True)) + r")"
_DURATION = re.compile(
    _NUM
    + r"(?:\s*(?:-|to|se)\s*"
    + _NUM
    + r")?\s*(min(?:ute)?s?|mints?|minat|ghant[ae]y?|hours?|hrs?|sec(?:ond)?s?)\b",
    re.IGNORECASE,
)
_PERIOD = r"(day|din|daily|roz|rozana|week|weekly|hafta|hafte|haftay|month|monthly|mahina|mahine)"
_FREQ_AFTER = re.compile(
    _NUM
    + r"\s*(?:orders?|times?|baar|bar|dafa|martaba|messages?|customers?|payments?|parcels?|emails?|bookings?)?"
    r"\s*(?:a|per|every|each|har|in a|ek)?\s*" + _PERIOD + r"\b",
    re.IGNORECASE,
)
_FREQ_BEFORE = re.compile(
    r"\b"
    + _PERIOD
    + r"\s*(?:mein|me|main|ko|ke|bhar|bhar mein)?\s*(?:taqreeban|about|around|almost|lagbhag|approx\.?)?\s*"
    + _NUM,
    re.IGNORECASE,
)
_PER_WEEK = {
    "day": 7,
    "din": 7,
    "daily": 7,
    "roz": 7,
    "rozana": 7,
    "week": 1,
    "weekly": 1,
    "hafta": 1,
    "hafte": 1,
    "haftay": 1,
    "month": 12 / 52,
    "monthly": 12 / 52,
    "mahina": 12 / 52,
    "mahine": 12 / 52,
}


def extract_minutes(text: str) -> float | None:
    match = _DURATION.search(text)
    if not match:
        return None
    low = _num(match.group(1).lower())
    high = _num(match.group(2).lower()) if match.group(2) else None
    if low is None:
        return None
    value = (low + high) / 2 if high else low
    unit = match.group(3).lower()
    if unit.startswith(("ghant", "hour", "hr")):
        value *= 60
    elif unit.startswith("sec"):
        value /= 60
    return round(value, 1)


def extract_runs_per_week(text: str) -> int | None:
    for pattern, num_group, period_group in ((_FREQ_AFTER, 1, 2), (_FREQ_BEFORE, 2, 1)):
        match = pattern.search(text)
        if match:
            count = _num(match.group(num_group).lower())
            factor = _PER_WEEK.get(match.group(period_group).lower(), 1)
            if count is not None:
                return max(1, round(count * factor))
    return None


def strip_quantities(text: str) -> str:
    text = _DURATION.sub(" ", text)
    text = _FREQ_AFTER.sub(" ", text)
    return _FREQ_BEFORE.sub(" ", text)


# --------------------------------------------------------------------------- semantics
APP_KEYWORDS: list[tuple[str, frozenset[str]]] = [
    ("whatsapp", frozenset({"whatsapp", "whats", "wa"})),
    ("excel", frozenset({"excel", "xls", "xlsx"})),
    ("google_sheets", frozenset({"google", "sheet", "sheets", "spreadsheet"})),
    ("gmail", frozenset({"gmail", "email", "e-mail", "mail", "inbox"})),
    ("paper", frozenset({"register", "notebook", "copy", "kaghaz", "diary", "rajister", "khata"})),
    (
        "courier",
        frozenset({"courier", "tcs", "leopards", "trax", "postex", "rider", "m&p", "callcourier"}),
    ),
    ("bank", frozenset({"bank", "jazzcash", "easypaisa", "raast", "transfer"})),
    ("phone", frozenset({"call", "phone", "fone"})),
    ("webform", frozenset({"form", "website", "site", "shopify", "daraz"})),
]

ACTOR_KEYWORDS: list[tuple[str, frozenset[str]]] = [
    ("Customer", frozenset({"customer", "customers", "client", "clients", "gahak", "buyer"})),
    (
        "Staff",
        frozenset(
            {"staff", "worker", "employee", "ladka", "assistant", "helper", "bhai", "munshi"}
        ),
    ),
    ("Courier", frozenset({"rider", "courier"})),
    ("Owner", frozenset({"main", "mein", "i", "me", "myself", "khud", "hum", "we", "owner", "my"})),
]

MONEY = frozenset(
    {
        "payment",
        "payments",
        "paisay",
        "paise",
        "paisa",
        "rs",
        "rupay",
        "rupees",
        "rupaye",
        "amount",
        "jazzcash",
        "easypaisa",
        "bank",
        "price",
        "total",
        "invoice",
        "bill",
        "raqam",
        "screenshot",
        "cod",
    }
)
SEND_VERBS = frozenset(
    {
        "send",
        "sends",
        "sending",
        "sent",
        "bhej",
        "bhejta",
        "bhejti",
        "bhejte",
        "bhejna",
        "bhejne",
        "reply",
        "replies",
        "jawab",
        "confirm",
        "confirmation",
        "message",
        "msg",
        "notify",
        "inform",
        "batata",
        "batati",
        "tracking",
    }
)
CUSTOMER_WORDS = frozenset({"customer", "customers", "client", "unko", "usko", "gahak", "buyer"})
HUMAN_ONLY = frozenset(
    {
        "pack",
        "packing",
        "packs",
        "stitch",
        "silai",
        "cook",
        "pakana",
        "deliver by hand",
        "visit",
        "physically",
        "measure",
        "naap",
        "cut",
        "iron",
        "press",
        "dhulai",
        "bake",
        "repair",
    }
)
AUTOMATED = frozenset({"automatically", "automatic", "auto", "khud-ba-khud"})


@dataclass(slots=True)
class StepKind:
    code: str
    title: str
    requires_all: tuple[frozenset[str], ...]
    default_minutes: float
    step_type: str = "manual"


KINDS: list[StepKind] = [
    StepKind(
        "receive_order",
        "Receive order on {app}",
        (
            frozenset({"order", "orders", "aarder"}),
            frozenset(
                {
                    "bhejta",
                    "bhejti",
                    "bhejte",
                    "aata",
                    "aate",
                    "aati",
                    "deta",
                    "deti",
                    "dete",
                    "sends",
                    "send",
                    "receive",
                    "receives",
                    "places",
                    "place",
                    "milta",
                    "milte",
                    "comes",
                    "come",
                    "arrive",
                }
            ),
        ),
        0,
        "start",
    ),
    StepKind(
        "check_payment",
        "Check payment screenshot against the order total",
        (
            frozenset(
                {
                    "payment",
                    "paisay",
                    "paise",
                    "screenshot",
                    "jazzcash",
                    "easypaisa",
                    "transfer",
                    "raqam",
                }
            ),
            frozenset(
                {
                    "check",
                    "checks",
                    "checking",
                    "verify",
                    "verifies",
                    "match",
                    "dekh",
                    "dekhta",
                    "dekhti",
                    "tasdeeq",
                    "milata",
                    "confirm",
                    "confirms",
                }
            ),
        ),
        2,
    ),
    StepKind(
        "record_order",
        "Copy order details into {app}",
        (
            frozenset(
                {
                    "copy",
                    "likh",
                    "likhta",
                    "likhti",
                    "note",
                    "entry",
                    "enter",
                    "record",
                    "darj",
                    "save",
                    "type",
                    "copies",
                    "writes",
                    "write",
                }
            ),
        ),
        3,
    ),
    StepKind(
        "send_confirmation",
        "Send order confirmation to the customer",
        (frozenset({"confirmation", "confirm", "confirmed", "tasdeeq", "shukriya"}),),
        1.5,
    ),
    StepKind(
        "pack",
        "Pack the order",
        (frozenset({"pack", "packs", "packing", "parcel", "packed"}),),
        10,
        "human_only",
    ),
    StepKind(
        "courier",
        "Book courier",
        (
            frozenset(
                {
                    "courier",
                    "tcs",
                    "leopards",
                    "trax",
                    "postex",
                    "rider",
                    "booking",
                    "dispatch",
                    "book",
                }
            ),
        ),
        4,
    ),
    StepKind("tracking", "Send tracking number to the customer", (frozenset({"tracking"}),), 1.5),
    StepKind("invoice", "Prepare invoice", (frozenset({"invoice", "bill", "receipt"}),), 3),
    StepKind("stock", "Update stock register", (frozenset({"stock", "inventory", "maal"}),), 3),
    StepKind(
        "reply_email",
        "Reply to customer e-mail",
        (frozenset({"email", "gmail", "mail"}), frozenset({"reply", "jawab", "answer", "respond"})),
        3,
    ),
    StepKind(
        "deliver",
        "Order delivered to the customer",
        (
            frozenset(
                {"deliver", "delivered", "delivery", "pohanch", "pohanchta", "receives", "mil"}
            ),
        ),
        0,
        "end",
    ),
]
KIND_BY_CODE = {k.code: k for k in KINDS}

APP_LABEL = {
    "whatsapp": "WhatsApp",
    "excel": "Excel",
    "google_sheets": "Google Sheets",
    "gmail": "Gmail",
    "paper": "the register",
    "courier": "the courier",
    "bank": "the bank app",
    "phone": "the phone",
    "webform": "the website form",
    "other": "the system",
    "none": "—",
}


def detect_kind(text: str) -> StepKind | None:
    words = tokens(text)
    for kind in KINDS:
        if all(has_any(words, group) for group in kind.requires_all):
            return kind
    return None


def detect_app(text: str) -> str:
    words = tokens(text)
    for app, stems in APP_KEYWORDS:
        if has_any(words, stems):
            return app
    return "other"


_OBJECT_AFTER = frozenset({"ko", "se", "ke", "kay", "ki", "tak"})
_OBJECT_BEFORE = frozenset({"to", "the", "for", "from", "with"})
_OWNER_PRONOUNS = frozenset({"main", "i", "me", "myself", "khud", "hum", "we", "owner"})


def detect_actor(text: str) -> str | None:
    """Best-effort subject detection; 'customer ko' / 'to the customer' are objects."""
    words = tokens(text)
    staff = next(s for a, s in ACTOR_KEYWORDS if a == "Staff")
    customers = next(s for a, s in ACTOR_KEYWORDS if a == "Customer")
    if any(w in staff for w in words):
        return "Staff"
    if any(w in _OWNER_PRONOUNS for w in words):
        return "Owner"
    for i, word in enumerate(words):
        if word in customers:
            after = words[i + 1] if i + 1 < len(words) else ""
            before = words[i - 1] if i > 0 else ""
            if after not in _OBJECT_AFTER and before not in _OBJECT_BEFORE:
                return "Customer"
    if words and words[0] in {"rider", "courier"}:
        return "Courier"
    return None


def involves_money(text: str) -> bool:
    return has_any(tokens(text), MONEY)


def involves_customer_messaging(text: str) -> bool:
    words = tokens(text)
    return has_any(words, SEND_VERBS) and (
        has_any(words, CUSTOMER_WORDS) or "tracking" in words or "confirmation" in words
    )


def is_human_only(text: str) -> bool:
    return has_any(tokens(text), HUMAN_ONLY)


def sentence_case(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", text).strip(" .,")
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


@dataclass(slots=True)
class DraftStep:
    title: str
    actor: str
    action: str
    step_type: str
    app: str
    kind: str | None
    minutes_per_run: float | None = None
    runs_per_week: int | None = None
    customer_messaging: bool = False
    money: bool = False
    sources: list[str] = field(default_factory=list)


def clause_to_step(clause: str) -> DraftStep:
    kind = detect_kind(clause)
    app = detect_app(clause)
    if (
        kind
        and app == "other"
        and kind.code in {"check_payment", "send_confirmation", "tracking", "receive_order"}
    ):
        app = "whatsapp"  # SME default: screenshots, confirmations and orders travel over WhatsApp
    title = kind.title if kind else sentence_case(strip_quantities(clause), 80)
    if "{app}" in title:
        title = title.format(
            app=APP_LABEL.get(app, "the system") if app != "other" else "the register"
        )
    if kind and kind.code == "courier" and "tracking" in clause.lower():
        title = "Book courier and send tracking number"
    detected = detect_actor(clause)
    if kind and kind.code == "receive_order":
        actor = "Customer" if detected in {None, "Customer"} else detected
    elif kind and kind.code == "deliver":
        actor = detected if detected in {"Courier", "Staff"} else "Courier"
    else:
        actor = detected if detected and detected != "Customer" else "Owner"
    step_type = kind.step_type if kind else "manual"
    if step_type == "manual" and is_human_only(clause):
        step_type = "human_only"
    if has_any(tokens(clause), AUTOMATED):
        step_type = "automated"
    return DraftStep(
        title=title,
        actor=actor,
        action=sentence_case(clause, 300),
        step_type=step_type,
        app=app,
        kind=kind.code if kind else None,
        minutes_per_run=extract_minutes(clause),
        runs_per_week=extract_runs_per_week(clause),
        customer_messaging=actor != "Customer"
        and step_type not in {"start", "end"}
        and (
            involves_customer_messaging(clause)
            or bool(kind and kind.code in {"send_confirmation", "tracking"})
        ),
        money=involves_money(clause) and not (kind and kind.code in {"pack", "deliver"}),
        sources=[clause],
    )


def is_attribute_clause(clause: str) -> bool:
    """True when a clause mostly carries numbers ('5 minute lagte hain')."""
    has_numbers = extract_minutes(clause) is not None or extract_runs_per_week(clause) is not None
    if not has_numbers:
        return False
    remainder = [
        w for w in tokens(strip_quantities(clause)) if w not in ROMAN_URDU_MARKERS and len(w) > 2
    ]
    filler = {
        "takes",
        "take",
        "lagte",
        "lagta",
        "lagti",
        "about",
        "around",
        "taqreeban",
        "minutes",
        "time",
        "waqt",
        "orders",
        "order",
        "aate",
        "aata",
        "come",
        "get",
        "receive",
        "almost",
        "usually",
        "normally",
    }
    return len([w for w in remainder if w not in filler]) <= 2


def split_attribute_segments(text: str) -> list[str]:
    return [
        s.strip()
        for s in re.split(r",|;|\baur\b|\band\b|\bphir\b", text, flags=re.IGNORECASE)
        if s.strip()
    ]


def extract_steps(user_texts: list[str]) -> tuple[list[DraftStep], int | None]:
    """Turn the owner's answers into ordered draft steps plus a global runs/week."""
    steps: list[DraftStep] = []
    global_runs: int | None = None
    for answer_index, answer in enumerate(user_texts):
        for clause in split_clauses(answer):
            kind = detect_kind(clause)
            known = {s.kind for s in steps if s.kind}
            numbers_only = is_attribute_clause(clause)
            if (
                numbers_only
                or (kind and kind.code in known)
                or (answer_index > 0 and kind is None and _has_numbers(clause))
            ):
                global_runs = _apply_attributes(steps, clause, global_runs)
                continue
            if kind is None and (answer_index > 0 and len(tokens(clause)) < 4):
                continue
            step = clause_to_step(clause)
            if step.runs_per_week and len(steps) <= 1 and step.kind == "receive_order":
                global_runs = global_runs or step.runs_per_week
            if steps and steps[-1].step_type == "end":
                steps.insert(len(steps) - 1, step)
            else:
                steps.append(step)
    return steps, global_runs


def _has_numbers(text: str) -> bool:
    return extract_minutes(text) is not None or extract_runs_per_week(text) is not None


def _apply_attributes(steps: list[DraftStep], clause: str, global_runs: int | None) -> int | None:
    for segment in split_attribute_segments(clause) or [clause]:
        minutes = extract_minutes(segment)
        runs = extract_runs_per_week(segment)
        if minutes is None and runs is None:
            continue
        kind = detect_kind(segment)
        target = next((s for s in steps if kind and s.kind == kind.code), None)
        if target is None:
            app = detect_app(segment)
            target = next(
                (s for s in steps if app != "other" and s.app == app and s.step_type != "start"),
                None,
            )
        if runs is not None and (target is None or target.step_type == "start"):
            global_runs = runs
            if target is None:
                continue
        if target is None and minutes is not None:
            manual = [
                s
                for s in steps
                if s.step_type in {"manual", "human_only"} and s.minutes_per_run is None
            ]
            target = manual[0] if manual else None
        if target is not None:
            if minutes is not None:
                target.minutes_per_run = minutes
            if runs is not None:
                target.runs_per_week = runs
    return global_runs
