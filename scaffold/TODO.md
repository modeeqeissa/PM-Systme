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

## TD-003 — iam-service does not emit audit events for admin actions

**Status:** open
**Severity:** should-fix before pilot (FR-IAM-06 says admin actions are
audit-logged; FR-AUD-01)
**Violates:** CLAUDE.md rule 3 (IAM data), FR-IAM-06, FR-AUD-01

### What's missing
iam-service administrative writes are not published as domain events, so
audit-service has no record of them:
- `POST /api/v1/users` (create), `PATCH /api/v1/users/{id}` (deactivate /
  reassign / rename), `PUT /api/v1/users/{id}/roles`,
  `POST /api/v1/users/{id}/password`, role/permission changes.

FR-IAM-05 ("notify ICT/security on lockout") also needs the event bus +
notification-service.

### Definition of done
- [ ] `identity_db.outbox_events` + relay (reuse the `app/events/` module from
      case-service / evidence-service).
- [ ] Emit `UserCreated`, `UserStatusChanged`, `UserRolesChanged`,
      `UserPasswordChanged` (names TBC against a future SRS §3.4 revision — the
      current SRS only lists `OfficerTransferred` for the IAM/HR boundary).
- [ ] audit-service maps them to `entity_type = user`, appropriate action.
- [ ] Account-lockout emits an event notification-service can consume (deferred
      with notification-service itself).
- [ ] Integration test mirroring `test_outbox.py`.

---

## Build order
Phase 0 pilot: **iam-service ✅ → case-service ✅ → evidence-service ✅ →
Kafka + transactional outbox ✅ → audit-service ✅ → dashboard-service read
models ✅**. All five pilot services build, migrate, test, and run locally; the
full event pipeline (write → outbox → Kafka → audit-service hash chain +
dashboard-service projections) is verified end-to-end.

**Next:** close **TD-003** (iam-service admin actions emit no events), then
notification-service (FR-IAM-05 lockout alerts, FR-NOTIF), then the remaining
services (hr, training, community, integration-gateway).
