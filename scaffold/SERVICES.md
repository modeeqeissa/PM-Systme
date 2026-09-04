# PMP Service Registry

Ports and databases per `CLAUDE.md` §"Services". Each service is an independently
deployable FastAPI app with its own `.venv`, Alembic history, `Dockerfile`, and
`openapi.yaml`.

`infra/docker-compose.yml` brings up **infrastructure only** (Postgres, Kafka,
Zookeeper, Redis, MinIO, Adminer). The application services run as host processes
in local dev (`cd <svc> && .venv/bin/uvicorn app.main:app --port <port>`) or from
their `Dockerfile` in a container platform — they are **not** in the compose file,
matching the established pattern.

| Service | Port | Database | Migration head | Status | FR / schema §§ |
|---|---|---|---|---|---|
| iam-service | 8001 | identity_db | 0002 | **built** | 4.1 / 9.3.1 |
| case-service | 8002 | case_db | 0002 | **built** | 4.2 / 9.3.2 |
| evidence-service | 8003 | evidence_db | 0002 | **built** | 4.3 / 9.3.3 |
| community-service | 8004 | community_db | 0001 | stub (schema only) | 4.4 / 9.3.4 |
| training-service | 8005 | training_db | 0001 | stub (schema only) | 4.5 / 9.3.5 |
| hr-service | 8006 | hr_db | 0001 | stub (schema only) | 4.6 / 9.3.6 |
| dashboard-service | 8007 | dashboard_db | 0001 | **built** (CQRS read models) | 4.7 / 9.3.7 |
| notification-service | 8008 | notification_db | 0001 | stub (schema only) | 4.8 / 9.3.8 |
| integration-gateway-service | 8009 | integration_db | 0001 | stub (schema only) | 4.9 / 9.3.9 |
| audit-service | 8010 | audit_db | 0001 | **built** (Kafka → hash-chained log) | 4.10 / 9.3.10 |

## Stub services (Phase 1)

`community`, `training`, `hr`, `notification`, `integration-gateway`.

Each has the full built-service top-level structure (`app/`, `alembic/`,
`Dockerfile`, `openapi.yaml`) but the implementation is **health-check only**:
`GET /health` → `{"status":"ok","service":"<name>"}`. The domain schema (docs
§9.3.4–9.3.6, §9.3.8–9.3.9) is migrated and verified — see each service's
`tests/test_schema.py` — so the databases are not empty, but nothing reads or
writes them yet. No business logic, no RBAC/JWT wiring, no event publishing or
consumption. `app/main.py` has the `app.include_router(...)` mount point marked
for Phase 1.

## Kafka topics (built services only)

Producers (transactional outbox → `app/events/relay.py`):
- case-service: `incident.reported`, `case.opened`, `case.status_changed`, `case.arrest_recorded`
- evidence-service: `evidence.logged`, `evidence.custody_recorded`, `evidence.hash_mismatch`

Consumers (idempotent on `event_id`):
- audit-service: all 7 topics → `audit_logs` (hash-chained)
- dashboard-service: all except `incident.reported` → `mv_*` projections

## Local dev

```
cd infra && docker compose up -d          # Postgres, Kafka, Redis, ...
cd <service> && .venv/bin/python -m alembic upgrade head
cd <service> && .venv/bin/python -m uvicorn app.main:app --port <port>
cd <service> && .venv/bin/python -m pytest -q
```
