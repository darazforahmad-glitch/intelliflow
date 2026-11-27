"""Test settings: SQLite in memory by default (fast), PostgreSQL when TEST_DATABASE_URL is
set (CI does this). Celery runs eagerly and the FakeLLMClient answers, so the whole
suite is deterministic and costs nothing."""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ["LLM_PROVIDER"] = "fake"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["EMAIL_BACKEND"] = "console"
os.environ["REDIS_URL"] = ""
os.environ["LOGIN_RATE_LIMIT_PER_MINUTE"] = "1000"

import dj_database_url  # noqa: E402

from config.settings import *  # noqa: E402, F403

DATABASES = {
    "default": dj_database_url.parse(
        os.environ.get("TEST_DATABASE_URL", "sqlite://:memory:").replace("+psycopg", "")
    )
}
CELERY_TASK_ALWAYS_EAGER = True
LOGGING["root"]["level"] = "WARNING"  # noqa: F405
