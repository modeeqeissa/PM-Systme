# Police Management Platform (PMP) — CLAUDE.md

Source of truth for architecture and requirements: `docs/PMP_SRS_Database_Design.docx`
(Sections 4 = functional requirements, 9 = database schema — always check there before
inventing a field, endpoint, or table that isn't already specified).

## Stack (fixed — do not substitute)
- API: FastAPI (Python 3.12), Pydantic v2, SQLAlchemy 2.0 async, Alembic migrations
- DB: PostgreSQL 16, **one database per service** (see "Services" below) — never add
  cross-service foreign keys; cross-service references are logical (UUID) only
- Front end: React 18 + TypeScript + TailwindCSS 3 + Vite, TanStack Query, Zustand
- Event bus: Kafka (topics named `<entity>.<event>`, e.g. `case.opened`)
- Auth: OAuth2/OIDC + JWT (15 min access / rotating refresh), MFA via TOTP
- Local dev: `docker-compose.yml` at repo root — `docker compose up` before anything else

## Monorepo layout
```
/services/<name>-service/       one folder per microservice, independently deployable
    app/
      main.py                   FastAPI app factory, router registration
      routers/                  one file per resource, thin — no business logic here
      models/                   SQLAlchemy ORM models (mirror docs Section 9 exactly)
      schemas/                  Pydantic request/response models
      services/                 business logic, saga/event handlers
      events/                   outbox publisher + Kafka consumer setup
      deps.py                   shared FastAPI dependencies (auth, db session, RBAC check)
    alembic/                    migrations, one linear history per service
    tests/                      pytest, mirrors app/ structure
    Dockerfile
/services/case-service/openapi.yaml   hand-maintained contract, FastAPI must match it
/frontend/
    apps/web-portal/            command web app
    apps/field-pwa/             offline-first field app
    packages/ui/                shared Tailwind component library used by both apps
/infra/
    docker-compose.yml
    k8s/                        Helm charts, one per service
/docs/
    PMP_SRS_Database_Design.docx
```

## Services (must match docs Section 3.3 / 9.3 exactly)
| Service | DB | Port (local) |
|---|---|---|
| iam-service | identity_db | 8001 |
| case-service | case_db | 8002 |
| evidence-service | evidence_db | 8003 |
| community-service | community_db | 8004 |
| training-service | training_db | 8005 |
| hr-service | hr_db | 8006 |
| dashboard-service | dashboard_db (read models only, no writes accepted) | 8007 |
| notification-service | notification_db | 8008 |
| integration-gateway-service | integration_db | 8009 |
| audit-service | audit_db (INSERT/SELECT only — no UPDATE/DELETE grants, ever) | 8010 |

## Non-negotiable rules
1. **No service reads or writes another service's database directly.** Cross-service
   data flows through the gateway (sync) or Kafka events (async) only.
2. **evidence_db.custody_events and audit_db.audit_logs are append-only.** Never write
   an UPDATE or DELETE statement against them, in migrations or app code. See docs
   Section 9.3.3 / 9.3.10 for the `REVOKE` statements this depends on.
3. **Every write to case, evidence, HR/discipline, or IAM data must emit an audit
   event.** Don't add a new mutating endpoint without also wiring the audit call.
4. **RBAC checks happen in `deps.py`, not per-router.** Reuse the shared
   `require_permission("case.write")`-style dependency; permission codes must match
   the `permissions.code` values already defined for identity_db.
5. **Every new field or table must trace back to docs Section 9.3** — if it's not
   there, either it needs adding to the SRS first (flag it, don't silently invent
   schema) or it belongs in a service-local, non-domain table (e.g. cache tables).
6. Field-originated write endpoints must accept an `Idempotency-Key` header and
   dedupe on it (supports offline sync — see FR-CASE-10).

## Dev workflow
- `docker compose up -d` → brings up all Postgres instances, Kafka, Redis, adminer
- Per service: `cd services/<name>-service && alembic upgrade head && uvicorn app.main:app --reload --port <port>`
- Run one service's tests: `cd services/<name>-service && pytest`
- Never commit `.env` — only `.env.example` with variable names, no values

## Current build phase
Phase 0 / pilot scope (build first): iam-service, case-service, evidence-service,
dashboard-service (read models for these three only). HR, training, community,
notification, integration-gateway, and audit are stubbed with health-check-only
endpoints until Phase 1 — do not fully implement them yet unless asked.
