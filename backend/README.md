# IntelliFlow backend

FastAPI REST API, webhook gateway, workflow engine and Celery workers. See the repository
[README](../README.md) for the architecture, setup and the requirement-by-requirement status.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head          # PostgreSQL schema
.venv/bin/python -m app.cli seed        # template library
.venv/bin/uvicorn app.main:app --reload # http://localhost:8000/api/docs
.venv/bin/python -m pytest              # 70%+ coverage gate
```
