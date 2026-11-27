# IntelliFlow

**AI-powered workflow discovery and automation for small and medium enterprises.**
The owner tells IntelliFlow how the business runs — in English, Urdu or Roman Urdu — and IntelliFlow
draws the process, shows what to automate first, and then automates it safely, with a person
approving anything risky.

> Final Year Project prototype · FYP-BSCSM-F26-099 · Department of Computer Science, The Superior University, Lahore.
> Built to the design in the project report (Chapters 1–5): same stack, data model, algorithms and business rules.

| Flow Mapper: interview → process map | Ranked automation opportunities |
| --- | --- |
| ![Flow Mapper](docs/screenshots/flow-mapper.jpg) | ![Opportunities](docs/screenshots/opportunities.jpg) |
| **Automation Builder** | **Operations dashboard** |
| ![Builder](docs/screenshots/builder.jpg) | ![Dashboard](docs/screenshots/dashboard.jpg) |
| **Integrations (sandbox Orders sheet)** | **Approvals PWA on a phone** |
| ![Integrations](docs/screenshots/integrations.jpg) | <img src="docs/screenshots/approvals-phone.jpg" alt="Approvals on a phone" width="280"> |

---

## What this prototype covers

This is a working prototype of roughly half of the system specified in the report: the FYP-I milestone
(Flow Mapper, release v0.1) plus most of the FYP-II core platform, runnable end to end. Every external
app works in **sandbox mode**, which behaves like the real app but records what it would do, so the whole
journey — interview, map, opportunity, automation, test, activation, a real signed webhook, approval,
dashboard — runs on a laptop with no API keys and no cost.

| Feature (Section 2.4) | Status | Notes |
| --- | --- | --- |
| **AC** Accounts & workspaces | ✅ | Register + e-mail verification, Argon2id, lockout after 5 failures for 15 min, 30-min reset links, Owner/Staff roles, invitations. *AC-7 Google sign-in: not yet.* |
| **FM** Interview & flow mapping | ✅ | Chat interview in English/Urdu/Roman Urdu, ≤ 12 questions, schema-validated map with ≤ 2 regenerations, editable flowchart, immutable versions, transcript. *FM-3 voice: browser speech recognition; WhatsApp voice-note transcription is FYP-II.* |
| **OA** Opportunity analysis | ✅ | Algorithm 5.2 exactly, template matching, top 3 with time saved per day/week and a one-line reason, dismiss → re-rank, "not yet supported" steps. |
| **IN** Integrations | 🟡 | Sandbox for WhatsApp, Gmail, Google Sheets and web forms; signed per-form webhook URLs (JSON + form data); tokens AES-256-GCM encrypted; refresh → "needs attention"; disconnect pauses dependants. Live WhatsApp Cloud API (manual connect / Meta test number) and Google OAuth + Sheets/Gmail clients are implemented but **not exercised against real accounts** in this build. *Meta Embedded Signup: FYP-II.* |
| **AB** AI automation builder | ✅ | Algorithm 5.3: template + LLM fill, JSON-schema + business-rule validation, ≤ 2 automatic repairs, plain-language errors, per-step editor, sandbox test run showing every step's input/output, activation gate, versions + rollback, create from template. |
| **WE** Workflow engine | ✅ | Algorithm 5.5 on Celery + Redis: blocks via Strategy pattern, retries 10 s/60 s/5 min, idempotent runs, masked step logs, encrypted run context, auto-pause after 5 failures, WhatsApp 24-hour window with template fallback, minutes saved. Gmail trigger by polling. |
| **AP** Human-in-the-loop approvals | ✅ | Approve / edit / reject (only whitelisted fields editable), immutable decisions, reminder at 2 h, expiry at 24 h, in-app + e-mail + Web Push, installable PWA usable at 360 px. |
| **DR** Dashboard & reports | 🟡 | KPIs, hours saved per day, automations table, run drill-down, live updates over SSE, CSV export. *PDF export: FYP-II.* |
| **PA** Platform administration | 🟡 | Usage, failure rate and LLM cost, AI credit limits (80% warning, pause at 100%), suspend/reactivate, template versioning and publishing, audit log. *Visual template editor: FYP-II (API only).* |

**Safety & security requirements** — SAF-1 customer messages always need approval (auto-send unlocks after 20
clean approvals) · SAF-2 kill switch · SAF-3 no delete operations exist · SAF-4 100 messages/hour/automation ·
SAF-5 test runs are sandboxed · SAF-6 uncertain extraction goes to a person · SEC-1 Argon2id · SEC-2 AES-256-GCM
with key rotation and row-bound associated data · SEC-4 RBAC + every query scoped by workspace · SEC-5 HMAC-SHA256
webhook verification · SEC-7 validated input, parameterised queries, rate-limited sign-in, CSP · SEC-8 personal
data masked in logs, 30-day purge · SEC-9 customer text is data, never code (no `eval`; whitelist expression interpreter).

## The algorithms in code (Section 5.1)

| Algorithm | Where |
| --- | --- |
| 5.1 Process interview & map generation | [`interview_agent.py`](backend/app/services/interview_agent.py), [`process_mapper.py`](backend/app/services/process_mapper.py) |
| 5.2 Opportunity scoring & ranking | [`opportunity_analyzer.py`](backend/app/services/opportunity_analyzer.py) — `score = weekly_minutes × fit × (1 − 0.5 × min(risk, 1))` |
| 5.3 Automation generation with validation & repair | [`automation_builder.py`](backend/app/services/automation_builder.py), [`workflow_validator.py`](backend/app/services/workflow_validator.py) |
| 5.4 Webhook handling | [`webhook_gateway.py`](backend/app/services/webhook_gateway.py) |
| 5.5 Workflow execution with retries & approvals | [`workflow_engine.py`](backend/app/engine/workflow_engine.py), [`blocks/`](backend/app/engine/blocks) |

Process maps and workflows are validated against [`process_map.schema.json`](backend/app/jsonschemas/process_map.schema.json)
and [`workflow.schema.json`](backend/app/jsonschemas/workflow.schema.json); the shared template library (including
Listing 5.1, *Order entry from WhatsApp*) is in [`seeds/templates.py`](backend/app/seeds/templates.py).

## Architecture (Section 4.1)

```mermaid
flowchart LR
  subgraph Presentation
    WEB["Next.js web app"]
    PWA["Approvals PWA<br/>service worker + Web Push"]
  end
  subgraph API["API layer — FastAPI"]
    REST["REST /api/v1<br/>auth · RBAC"]
    GW["Webhook gateway<br/>HMAC · de-dupe"]
    SSE["Server-Sent Events"]
  end
  subgraph Services["Service layer"]
    FM["Interview & mapping"] --- OA["Opportunity analysis"] --- AB["Builder & validator"]
    APS["Approvals & notifications"] --- CS["Connections"] --- REP["Reporting"]
  end
  subgraph Execution["Execution layer"]
    Q[("Redis 7<br/>queue · locks")] --> W["Celery workers<br/>workflow engine"]
    BEAT["Celery Beat"] --> Q
  end
  DB[("PostgreSQL 16")]
  EXT["WhatsApp Cloud API · Gmail · Google Sheets · LLM"]
  WEB & PWA --> REST
  WEB -.-> SSE
  REST --> Services
  GW --> Q
  Services --> DB
  W --> DB
  W --> EXT
  EXT -->|webhooks| GW
```

The LLM sits behind a provider-agnostic `LLMClient` ([`app/llm`](backend/app/llm)). Two implementations ship:
`AnthropicLLMClient` (Claude via the official SDK, structured outputs constrained to the JSON schema) and
`FakeLLMClient`, a deterministic offline stand-in that understands the English and Roman Urdu demo
scenarios, so tests and demos are repeatable and free.

## Stack (Table 5.1)

| Layer | Technology |
| --- | --- |
| Frontend | Next.js 16 (App Router), React 19, TypeScript (strict), Tailwind CSS 4, React Flow, TanStack Query, Zod, Recharts, Workbox service worker + Web Push |
| Backend | Python 3.12, FastAPI, Uvicorn, Pydantic 2, SQLAlchemy 2 + Alembic, PostgreSQL 16, Celery + Redis 7, jsonschema, httpx, google-auth + Google API client, cryptography, argon2-cffi, PyJWT, pywebpush, Anthropic SDK |
| Quality | pytest, Playwright, Locust, Ruff, Black, mypy, ESLint, Prettier, GitHub Actions |

## Run it

### Option A — Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Then load the demo workspace (optional) and open <http://localhost:3000>:

```bash
docker compose exec api python -m app.cli demo
```

### Option B — locally

Requires Python 3.12+, Node 20.9+, PostgreSQL 16 and Redis 7 (both optional for a quick look: without
`DATABASE_URL` the API uses SQLite, and without Redis it falls back to an in-memory store).

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/python -m app.cli seed
.venv/bin/uvicorn app.main:app --reload
```

```bash
cd backend && .venv/bin/celery -A app.worker.celery_app:celery_app worker -Q intelliflow --loglevel=INFO
```

```bash
cd backend && .venv/bin/celery -A app.worker.celery_app:celery_app beat --loglevel=INFO
```

```bash
cd frontend && npm install && npm run dev
```

(Set `CELERY_TASK_ALWAYS_EAGER=true` to run tasks inside the API process instead of a worker.)

### Demo data and accounts

```bash
cd backend && .venv/bin/python -m app.cli demo
```

This creates **demo@intelliflow.pk / Demo12345** with the *Ayesha Boutique* workspace: a Roman Urdu order-process
interview, its map and opportunities, an active *Order entry from WhatsApp* automation and a week of runs,
some waiting for approval. In development, verification e-mails are kept in an outbox — the sign-up page
shows the link directly. A platform admin can be created with
`python -m app.cli create-admin --email … --password …`.

### Try the journey yourself

1. Register, then create a workspace.
2. **Flow Mapper** → *Order process* → answer in Roman Urdu or English → **Done — draw my map**.
3. **Integrations** → *Use sandbox* for WhatsApp and Google Sheets.
4. Back on the map → **Automate this** on *Copy order details into Excel* → **Test** → **Activate**.
5. **Integrations → WhatsApp → Simulate a customer message** — it goes through the real signed-webhook
   gateway and the worker, or use `python scripts/webhook_simulator.py --phone-number-id <id> --sample-orders`.
6. **Approvals** (best on a phone) → approve or edit the drafted Roman Urdu reply. Watch the dashboard update live.

### Real services

| Setting | Effect |
| --- | --- |
| `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` | Use Claude (default model `claude-opus-5-5`, change with `LLM_MODEL`). |
| `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN` | Meta webhook signature and subscription handshake (`/api/v1/webhooks/whatsapp`). |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google OAuth for Gmail and Sheets (redirect URI `<API_PUBLIC_URL>/api/v1/oauth/google/callback`). |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | Web Push for approvals (`python -m app.cli generate-vapid`). |
| `EMAIL_BACKEND=smtp`, `SMTP_*` | Send real e-mails instead of the development outbox. |
| `SECRET_KEY`, `ENCRYPTION_KEYS` | Required outside development (`python -m app.cli generate-keys`); the API refuses to start with the dev defaults. |

API documentation (OpenAPI) is served at <http://localhost:8000/api/docs>.

## Tests and measured results

| Suite | Command | Result in this build |
| --- | --- | --- |
| Backend unit + API tests | `cd backend && .venv/bin/python -m pytest --cov=app` | 77 tests pass on SQLite and on PostgreSQL 16 (`TEST_DATABASE_URL=…`); 83% coverage (gate: 70%); core modules 84–97% |
| Static checks | `ruff check app tests && black --check app tests && mypy app` · `npm run lint && npm run typecheck` | clean |
| Migrations | `alembic upgrade head && alembic check && alembic downgrade base` | round trip clean, no model drift |
| End to end | `cd frontend && npm run test:e2e` (API on :8000, web on :3000) | owner journey (desktop) and approvals PWA (360 px phone) pass against a real Celery worker |
| Load | `locust -f loadtests/locustfile.py --host http://localhost:8000 --users 50 --headless --run-time 2m` | 50 users, 1,150 requests, 0 failures; p95: dashboard 220 ms, automations 190 ms, approvals 740 ms, runs 1.2 s (PERF-1: < 2 s); webhook acknowledgement p95 **61 ms** (PERF-2 target: < 1 s) — single VM shared by API, worker, database and web |

## Project structure

```
backend/
  app/
    api/v1/          REST endpoints (auth, workspaces, interviews, process maps, automations,
                     runs & approvals, connections, dashboard, notifications, webhooks, admin)
    services/        domain logic (interview, mapping, opportunities, builder, validator,
                     approvals, connections, webhook gateway, reporting, notifications)
    engine/          workflow engine, safe expressions, block library (Strategy pattern)
    connectors/      WhatsApp, Gmail, Google Sheets, web forms (Adapter pattern) + sandbox stores
    llm/             LLMClient, Claude adapter, FakeLLMClient, prompts, output schemas
    models/          SQLAlchemy models — the data dictionary of Section 4.3
    jsonschemas/     process-map and workflow JSON Schemas
    worker/          Celery app, tasks and Beat schedule
    seeds/           template library
  alembic/           migrations
  tests/             unit and API tests
  scripts/           webhook simulator
frontend/
  src/app/           pages: auth, onboarding, dashboard, flow mapper, automations, approvals,
                     runs, integrations, settings, admin
  src/components/    UI kit, process map, chat, builder, approval card, charts
  src/lib/           API client, query hooks, session, SSE, push, Zod schemas
  sw/                Workbox service worker source
  e2e/               Playwright tests
loadtests/           Locust scenarios
docs/screenshots/
```

## Known limitations (next steps for FYP-II)

- Live WhatsApp, Gmail and Google Sheets calls are implemented but were only exercised in sandbox mode here;
  Meta Embedded Signup and Tech Provider onboarding are not built yet (manual connect with the Meta test number works).
- WhatsApp voice notes and payment screenshots are not transcribed/read yet; the interview accepts voice through the browser's speech recognition.
- The offline `FakeLLMClient` is tuned for the demo scenarios (English and Roman Urdu); Urdu-script answers need the real LLM.
- Not yet built: Google sign-in (REQ-AC-7), PDF reports (REQ-DR-5), a visual template editor for admins, staging/production deployment configs (Vercel, Render/Railway).
- The pilot with a real SME and the ≥ 90% extraction-accuracy evaluation (Objective 7) are FYP-II work.

## Conventions

Conventional Commits, `main` / `develop` / `feature/*` branches, PEP 8 via Ruff + Black, mypy, strict TypeScript with
ESLint + Prettier, schema changes only through Alembic, every query scoped by `workspace_id` (Section 5.5–5.6).
