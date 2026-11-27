"""Django settings for IntelliFlow (twelve-factor, Section 5.5).

Everything that differs between environments comes from environment variables (and,
for local runs, an optional `.env` file). The variable names are the same ones the
deployment, Docker Compose file and `.env.example` use. Secrets are never committed;
outside development the server refuses to start with the development defaults.
"""

from __future__ import annotations

import os
import warnings
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# --- Environment helpers -----------------------------------------------------------------
def _load_dotenv(*paths: Path) -> None:
    """Minimal .env reader for local runs. Real environment variables always win."""
    for path in paths:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if value[:1] in {'"', "'"} and value[-1:] == value[:1]:
                value = value[1:-1]
            elif " #" in value:
                value = value.split(" #", 1)[0].rstrip()
            os.environ.setdefault(key.strip(), value)


_load_dotenv(Path.cwd() / ".env", BASE_DIR / ".env", BASE_DIR.parent / ".env")


def env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def env_str(name: str, default: str) -> str:
    return env(name, default) or default


def env_int(name: str, default: int) -> int:
    value = env(name)
    try:
        return default if value is None else int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a whole number.") from exc


def env_float(name: str, default: float) -> float:
    value = env(name)
    try:
        return default if value is None else float(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be a number.") from exc


def env_bool(name: str, default: bool) -> bool:
    value = env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_choice(name: str, default: str, choices: set[str]) -> str:
    value = env_str(name, default).strip().lower()
    if value not in choices:
        raise ImproperlyConfigured(f"{name} must be one of: {', '.join(sorted(choices))}.")
    return value


# --- Runtime ---------------------------------------------------------------------------------
ENVIRONMENT = env_choice(
    "ENVIRONMENT", "development", {"development", "test", "staging", "production"}
)
IS_DEV_LIKE = ENVIRONMENT in {"development", "test"}
DEBUG = env_bool("DEBUG", ENVIRONMENT == "development")
LOG_LEVEL = env_str("LOG_LEVEL", "INFO").upper()
API_PUBLIC_URL = env_str("API_PUBLIC_URL", "http://localhost:8000").rstrip("/")
FRONTEND_URL = env_str("FRONTEND_URL", "http://localhost:3000").rstrip("/")
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in env_str("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]
CORS_ALLOW_HEADERS = ["authorization", "content-type", "x-request-id", "idempotency-key"]
CORS_EXPOSE_HEADERS = ["X-Request-ID"]
CORS_ALLOW_CREDENTIALS = False

_api_host = urlparse(API_PUBLIC_URL).hostname or "localhost"
ALLOWED_HOSTS = [
    host.strip()
    for host in env_str(
        "ALLOWED_HOSTS", "*" if IS_DEV_LIKE else f"{_api_host},localhost,127.0.0.1"
    ).split(",")
    if host.strip()
]
CSRF_TRUSTED_ORIGINS = [f"{urlparse(API_PUBLIC_URL).scheme}://{_api_host}"]
if not IS_DEV_LIKE:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# --- Security ----------------------------------------------------------------------------------
DEV_SECRET_KEY = (
    "change-me-dev-only-secret-key-at-least-32-chars"  # noqa: S105 - refused outside dev
)
DEV_ENCRYPTION_KEYS = "dev1:ZGV2LW9ubHktZW5jcnlwdGlvbi1rZXktMzItYnl0ZXM="
DEV_WHATSAPP_APP_SECRET = "dev-whatsapp-app-secret"  # noqa: S105 - refused outside dev

SECRET_KEY = env_str("SECRET_KEY", DEV_SECRET_KEY)
ENCRYPTION_KEYS = env_str("ENCRYPTION_KEYS", DEV_ENCRYPTION_KEYS)
if len(SECRET_KEY) < 32:
    raise ImproperlyConfigured("SECRET_KEY must be at least 32 characters long.")

ACCESS_TOKEN_TTL_MINUTES = env_int("ACCESS_TOKEN_TTL_MINUTES", 60)
REFRESH_TOKEN_TTL_DAYS = env_int("REFRESH_TOKEN_TTL_DAYS", 14)
EMAIL_TOKEN_TTL_HOURS = env_int("EMAIL_TOKEN_TTL_HOURS", 48)
PASSWORD_RESET_TTL_MINUTES = env_int("PASSWORD_RESET_TTL_MINUTES", 30)  # REQ-AC-6
INVITATION_TTL_DAYS = env_int("INVITATION_TTL_DAYS", 7)
MAX_FAILED_LOGINS = env_int("MAX_FAILED_LOGINS", 5)  # REQ-AC-2
LOCKOUT_MINUTES = env_int("LOCKOUT_MINUTES", 15)  # REQ-AC-2
LOGIN_RATE_LIMIT_PER_MINUTE = env_int("LOGIN_RATE_LIMIT_PER_MINUTE", 20)  # SEC-7 (per IP)

AUTH_USER_MODEL = "accounts.User"
# SEC-1: Argon2id through Django's password framework (argon2-cffi).
PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]

# --- Data services -------------------------------------------------------------------------------
DATABASE_URL = env_str("DATABASE_URL", f"sqlite:///{BASE_DIR / 'intelliflow.sqlite3'}")
# Accept SQLAlchemy-style URLs (postgresql+psycopg://) from older .env files.
_db_url = DATABASE_URL.replace("+psycopg", "").replace("+pysqlite", "")
DATABASES = {
    "default": dj_database_url.parse(
        _db_url,
        conn_max_age=0 if _db_url.startswith("sqlite") else 60,
        conn_health_checks=not _db_url.startswith("sqlite"),
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# An empty REDIS_URL means "no Redis": development and tests then use an in-memory store.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0") or None
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)

# --- LLM ----------------------------------------------------------------------------------------------
LLM_PROVIDER = env_choice("LLM_PROVIDER", "fake", {"fake", "anthropic"})
LLM_MODEL = env_str("LLM_MODEL", "claude-opus-5-5")
LLM_TIMEOUT_SECONDS = env_float("LLM_TIMEOUT_SECONDS", 90.0)
LLM_MAX_RETRIES = env_int("LLM_MAX_RETRIES", 2)
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
DEFAULT_AI_CREDIT_LIMIT = env_int("DEFAULT_AI_CREDIT_LIMIT", 2000)  # AI calls / workspace / month

# --- Product rules ---------------------------------------------------------------------------------
INTERVIEW_MAX_QUESTIONS = env_int("INTERVIEW_MAX_QUESTIONS", 12)  # REQ-FM-2
DEFAULT_APPROVAL_THRESHOLD = env_int("DEFAULT_APPROVAL_THRESHOLD", 10_000)  # BR-5 (PKR)
APPROVAL_REMINDER_MINUTES = env_int("APPROVAL_REMINDER_MINUTES", 120)  # REQ-AP-5
APPROVAL_TIMEOUT_MINUTES = env_int("APPROVAL_TIMEOUT_MINUTES", 1440)  # REQ-AP-5
AUTOMATION_FAILURE_THRESHOLD = env_int("AUTOMATION_FAILURE_THRESHOLD", 5)  # REQ-WE-7
MESSAGES_PER_HOUR_LIMIT = env_int("MESSAGES_PER_HOUR_LIMIT", 100)  # SAF-4
AUTO_SEND_MIN_CLEAN_APPROVALS = env_int("AUTO_SEND_MIN_CLEAN_APPROVALS", 20)  # SAF-1
WEBHOOK_DEDUPE_TTL_SECONDS = env_int("WEBHOOK_DEDUPE_TTL_SECONDS", 24 * 3600)  # Algorithm 5.4

# --- WhatsApp Cloud API -----------------------------------------------------------------------------
WHATSAPP_APP_SECRET = env_str("WHATSAPP_APP_SECRET", DEV_WHATSAPP_APP_SECRET)
WHATSAPP_VERIFY_TOKEN = env_str("WHATSAPP_VERIFY_TOKEN", "dev-verify-token")
WHATSAPP_GRAPH_API_VERSION = env_str("WHATSAPP_GRAPH_API_VERSION", "v23.0")
WHATSAPP_GRAPH_BASE_URL = env_str("WHATSAPP_GRAPH_BASE_URL", "https://graph.facebook.com")

# --- Google OAuth ---------------------------------------------------------------------------------------
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET")

# --- E-mail (every message is also kept in the email_messages outbox) ----------------------------------
_email_backend = env_str("EMAIL_BACKEND", "console")
EMAIL_BACKEND = {
    "console": "django.core.mail.backends.console.EmailBackend",
    "smtp": "django.core.mail.backends.smtp.EmailBackend",
}.get(_email_backend.lower(), _email_backend)
DEFAULT_FROM_EMAIL = env_str("EMAIL_FROM", "IntelliFlow <no-reply@intelliflow.local>")
EMAIL_HOST = env_str("SMTP_HOST", "localhost")
EMAIL_PORT = env_int("SMTP_PORT", 587)
EMAIL_HOST_USER = env_str("SMTP_USERNAME", "")
EMAIL_HOST_PASSWORD = env_str("SMTP_PASSWORD", "")
EMAIL_USE_TLS = EMAIL_PORT == 587
EMAIL_TIMEOUT = 20

# --- Web Push -------------------------------------------------------------------------------------------
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY")
VAPID_SUBJECT = env_str("VAPID_SUBJECT", "mailto:admin@intelliflow.local")

# --- Derived flags ---------------------------------------------------------------------------------------
IS_PRODUCTION = ENVIRONMENT == "production"
GOOGLE_OAUTH_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
WEB_PUSH_ENABLED = bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)

# --- Observability ---------------------------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN")

if ENVIRONMENT in {"staging", "production"}:
    if SECRET_KEY == DEV_SECRET_KEY or ENCRYPTION_KEYS == DEV_ENCRYPTION_KEYS:
        raise ImproperlyConfigured(
            "Refusing to start: development secrets are configured in a "
            f"{ENVIRONMENT} environment. Set SECRET_KEY and ENCRYPTION_KEYS."
        )
    if WHATSAPP_APP_SECRET == DEV_WHATSAPP_APP_SECRET:
        raise ImproperlyConfigured("Refusing to start: set WHATSAPP_APP_SECRET.")

# --- Django ----------------------------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "intelliflow.core",
    "intelliflow.accounts",
    "intelliflow.workspaces",
    "intelliflow.flowmapper",
    "intelliflow.opportunities",
    "intelliflow.automations",
    "intelliflow.integrations",
    "intelliflow.runs",
    "intelliflow.approvals",
    "intelliflow.notifications",
    "intelliflow.audit",
    "intelliflow.dashboard",
    "intelliflow.platform_admin",
]

MIDDLEWARE = [
    "intelliflow.core.middleware.RequestContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
APPEND_SLASH = False  # API paths have no trailing slash

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
# Static files are collected into the image at build time; locally the folder may not exist yet.
warnings.filterwarnings("ignore", message="No directory at", module="whitenoise.base")
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# --- Django REST Framework ---------------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["intelliflow.accounts.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "EXCEPTION_HANDLER": "intelliflow.core.api.exceptions.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=REFRESH_TOKEN_TTL_DAYS),
    "ROTATE_REFRESH_TOKENS": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "ISSUER": "intelliflow",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "sub",
    "TOKEN_TYPE_CLAIM": "typ",
    "JTI_CLAIM": "jti",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "IntelliFlow API",
    "DESCRIPTION": "AI-powered workflow discovery and automation for SMEs.",
    "VERSION": "0.6.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# --- Celery (Redis broker; Beat schedule lives in config/celery.py) ------------------------------------------
CELERY_BROKER_URL = REDIS_URL or "memory://"
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_EAGER_PROPAGATES = False
CELERY_TASK_ACKS_LATE = True  # a crashed worker's task is redelivered
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_DEFAULT_QUEUE = "intelliflow"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# --- Logging: structured JSON with request ids and masked personal data -------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "intelliflow.core.logging.JSONFormatter"}},
    "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["stdout"], "level": LOG_LEVEL},
    "loggers": {
        "django.server": {"level": "WARNING"},  # requests are logged by our middleware
        "django.request": {"level": "ERROR"},
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
        "googleapiclient.discovery_cache": {"level": "WARNING"},
        "anthropic": {"level": "WARNING"},
    },
}

if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=SENTRY_DSN, environment=ENVIRONMENT)
