# PMP — Tracked Technical Debt & Deferred Scope

Items here are **known and deliberately deferred**, not forgotten. Each must be
resolved before the owning service is considered pilot-ready.

---

## TD-001 — case-service audit events — ✅ RESOLVED (2026-09-03)

**Was:** case-service mutating endpoints persisted domain data without recording
an independent audit entry (CLAUDE.md rule 3, FR-AUD-01, SRS §5.8).

**Resolution:** the transactional outbox pattern (SRS §3.4 / §9.4) now runs in
case-service:
- `case_db.outbox_events` is written in the same transaction as the domain
  write; `app/events/relay.py` publishes to Kafka and marks rows sent.
- `POST /incidents` → `IncidentReported` (`incident.reported`, not re-emitted on
  an idempotent replay), `POST /cases` → `CaseOpened` (`case.opened`),
  `PATCH /cases/{id}/status` → `CaseStatusChanged` (`case.status_changed`),
  `POST /cases/{id}/arrests` → `ArrestRecorded` (`case.arrest_recorded`).
- **audit-service** consumes these and writes hash-chained rows to
  `audit_db.audit_logs` (append-only: no UPDATE/DELETE grants for the app role +
  BEFORE UPDATE/DELETE triggers).
- Tests: `case-service/tests/test_outbox.py` (same-transaction enqueue, atomic
  rollback on 409, relay→Kafka), `audit-service/tests/test_consumer.py`
  (event→entry mapping, idempotency, chain), `audit-service/tests/test_hashchain.py`.
- `TODO(TD-001)` markers removed from `case-service/app/routers/{incidents,cases}.py`.

### Still open (was "related deferred work", now its own item)
- **TD-003** below.

---

## TD-002 — evidence-service audit events — ✅ RESOLVED (2026-09-03)

**Was:** `POST /evidence` and `POST /evidence/{id}/custody` (and the automatic
`collected` event) persisted domain data without an independent audit entry.
`custody_events` being append-only is the service's own domain record, not the
independent Audit Log entry SRS §5.8 requires.

**Resolution:** same transactional-outbox mechanism now runs in evidence-service:
- `evidence_db.outbox_events` (the least-privilege `evidence_service_app` role
  has SELECT/INSERT/UPDATE here, still only INSERT/SELECT on `custody_events`).
- `POST /evidence` → `EvidenceLogged` (`evidence.logged`);
  `POST /evidence/{id}/custody` → `CustodyEventRecorded`
  (`evidence.custody_recorded`).
- audit-service consumes both (`entity_type` = `evidence_item` / `custody_event`).
- Tests: `evidence-service/tests/test_outbox.py` (incl. proof the app role
  cannot DELETE outbox rows), plus the audit-service consumer tests.
- `TODO(TD-002)` markers removed from `evidence-service/app/routers/{evidence,custody}.py`.

---

## TD-003 — iam-service admin / lockout audit events — ✅ RESOLVED (2026-09-04)

**Was:** iam-service administrative writes (FR-IAM-06) and account lockout
(FR-IAM-05) published nothing, so audit-service had no record of them
(CLAUDE.md rule 3, FR-AUD-01).

**Resolution:** the transactional-outbox module now runs in iam-service too
(`app/events/`, migration `0003_outbox.py`, relay spawned in `main.py` lifespan):
- `POST /users` → `UserCreated` (`user.created`)
- `PATCH /users/{id}` transitioning **into** `deactivated` → `UserDeactivated`
  (`user.deactivated`) — not emitted for `suspended` or a no-op re-deactivate
- `PUT /users/{id}/roles` when the role set actually changes → `UserRoleReassigned`
  (`user.role_reassigned`), payload carries `previous_roles` / `new_roles`
- account lockout (FR-IAM-05) → `AccountLockedOut` (`account.locked_out`),
  enqueued in the same transaction as the `failed_login_count` bump, at the
  lockout **transition** only — the already-locked check short-circuits earlier
  attempts, so it fires **exactly once per lockout** (`actor_role: "system"`,
  no admin actor).
- **audit-service** consumes all four (added to `_BASE_TOPICS`, one consumer):
  `UserCreated` → `user`/`create`, `UserDeactivated` → `user`/`delete`
  (soft-delete/status change per SRS §9.3.10), `UserRoleReassigned` &
  `AccountLockedOut` → `user`/`update`.
- Tests: `iam-service/tests/test_outbox.py` (domain change + event, deactivate
  emits once only on the transition, roles emit only on change, lockout emits
  exactly once and not per failed attempt, relay → Kafka),
  `audit-service/tests/test_consumer.py` (mapping of all four).
- No `TODO(TD-003)` code markers existed; none to remove.

### Still deferred with notification-service
- FR-IAM-05's *notification* half ("notify ICT/security"): notification-service
  will consume `account.locked_out` once it is built.
- iam-service `POST /users/{id}/password` and role/permission-definition changes
  don't emit yet — add when Phase 1 revisits iam.

---

## Build order
Phase 0 pilot: **iam ✅ → case ✅ → evidence ✅ → Kafka + transactional outbox
✅ → audit-service ✅ → dashboard-service read models ✅**. Full event pipeline
(write → outbox → Kafka → audit hash chain + dashboard projections) verified
end-to-end, including `evidence.hash_mismatch` (verify-with-mismatch → audit
`read` entry + `mv_evidence_integrity.hash_mismatch_count`).

Phase 1 **stubs scaffolded** (health-check only, schema migrated + verified,
no logic/RBAC/events): community (8004), training (8005), hr (8006),
notification (8008), integration-gateway (8009). See `SERVICES.md`.

**Next:** fill in the Phase 1 services (start with notification-service — it can
consume `account.locked_out` for the FR-IAM-05 alert half, plus FR-NOTIF).
