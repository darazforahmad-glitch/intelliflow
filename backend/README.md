# IntelliFlow backend

Django 5.2 + Django REST Framework API, webhook gateway, workflow engine and Celery
workers; the Django admin site is the Platform Admin. See the repository
[README](../README.md) for the architecture, setup and requirement status.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python manage.py migrate            # schema (SQLite without DATABASE_URL)
.venv/bin/python manage.py seed               # template library
.venv/bin/python manage.py demo               # optional demo workspace
.venv/bin/python manage.py create_admin --email you@example.com --password ...
.venv/bin/python manage.py runserver          # http://localhost:8000/api/docs, /admin/
.venv/bin/python -m pytest                    # 70%+ coverage gate
```

| Path | What it holds |
| --- | --- |
| `config/` | settings (from environment variables), URLs, WSGI, Celery app and Beat schedule |
| `intelliflow/<app>/` | one Django app per report module: models, services, serializers, views, urls, admin, tasks |
| `intelliflow/engine/` | workflow engine and block library (Algorithm 5.5) |
| `intelliflow/llm/` | provider-agnostic LLM client, prompts, offline fake client |
