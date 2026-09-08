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

**UPDATE 2026-09-05:** FR-IAM-05's notification half is done — notification-
service now consumes `account.locked_out` directly (`user_id` is already an
identity_db id, no lookup needed). See TD-004.

**FULLY CLOSED 2026-09-07:** the last two gaps are wired into the same
outbox path:
- `POST /users/{id}/password` → `UserPasswordChanged` (`user.password_changed`,
  payload `by_admin` distinguishes an admin reset from a self-service change;
  actor is the admin or the user accordingly) → audit `user`/`update`.
- `POST /roles` → `RoleCreated` (`role.created`) → audit `role`/`create`;
  `PUT /roles/{id}/permissions` on an actual change → `RolePermissionsChanged`
  (`role.permissions_changed`, carries previous/new code sets) → audit
  `role`/`update`.
Tests in `iam-service/tests/test_outbox.py` (self vs admin actor, role
create-then-grant, no event on a no-op permission set) and the audit
all-event-types mapping (now 48). Every runtime endpoint that mutates
identity_db under FR-IAM-06 now emits — nothing left silent. The auth *flow*
(login / MFA / refresh / logout) deliberately does NOT feed the hash chain —
see TD-006's auth-events note.

---

## TD-004 — notification-service ships with the DevChannel — a settled design, not an open gap

**Status: this is the intended pilot behaviour, deferred indefinitely by
product decision. There is no plan, timeline, or owner to "fix" — it is not
blocking anything and needs no periodic review.** It stays listed only so the
rationale is on record. Revisit *only if and when* a real messaging provider
is actually chosen and funded.

**Is:** notification-service (FR-NOTIF-01/03) consumes `hr.transfer_status_
changed`, `hr.leave_status_changed`, `training.officer_certification_status_
changed`, `community.follow_up_action_status_changed`, and `account.locked_
out`, and queues a `notifications` row per relevant transition (mapping in
`notification-service/app/events/mapping.py`). A background `DeliveryWorker`
(`app/services/delivery.py`) picks up queued rows and calls a pluggable
`NotificationChannel.send()` per row.

**Why this is honest, not a cut corner:** no email/SMS/push provider has been
chosen yet, so the only implementation is `DevChannel` (`app/services/
channels/dev.py`) — it logs and keeps an in-memory record of what would have
been sent, then marks the row `sent`. Every `channel` value (email/sms/push/
in_app) maps to the same `DevChannel` instance until a real one exists.
Separately — and this would still be true even with a chosen provider —
notification-service has no access to a recipient's actual email address or
phone number: that lives in identity_db, and CLAUDE.md rule 1 forbids
reading another service's database directly. A real integration needs both a
vendor decision AND a contact-detail resolution path (probably a small
read-only lookup exposed by iam-service, not direct DB access), neither of
which exists today.

**CLOSED 2026-09-06 (corrected SRS + migration 0003):** `notification_
templates` now has `subject`/`body` — rendered text is DB rows, editable
without a deploy. `notification_preferences` (FR-NOTIF-02) exists with
`GET`/`PUT /notification-preferences`; the delivery worker suppresses a
notification whose (recipient, channel) preference is disabled. Only the
default channel and the DevChannel below remain.

**UPDATE 2026-09-07 (migration 0005):** a suppressed notification now lands
in its own terminal status `suppressed` (added to the §9.3.8 status enum),
not `failed` — an intentional opt-out is no longer indistinguishable from a
real provider failure.

**Known ordering limitation:** the officer_id -> user_id lookup
(`app.models.OfficerUserMap`, fed by `hr.officer_created` /
`hr.officer_supervisor_changed`) depends on those events having been
consumed. Kafka only orders messages within one topic; the consumer now
sorts each poll batch by `occurred_at` (as dashboard-service does) which
makes it causal *within a batch*, but a message split across polls can
still land early on a cold backfill — the notification is then dropped with
a logged warning rather than retried. In steady state this is very
unlikely, since an officer's creation event will almost always be consumed
long before any
transfer/leave/certification/follow-up event references them.

**If a provider is ever adopted**, two pieces of work would follow: a real
`NotificationChannel` per medium (SMTP / SMS gateway / push), and a scoped
way to resolve a recipient's contact details without touching identity_db
directly (rule 1) — likely a small read-only lookup exposed by iam-service.
Neither is scheduled.

---

## TD-005 — integration-gateway-service adapters are stubs — nothing real to call

**Is:** integration-gateway-service (FR-INT-01..05) is built as a real
framework — correlation-id middleware (`app/services/correlation.py`,
`X-Correlation-Id` on every request), `integration_configs` seeded with the
four systems docs §9.3.9 names (CAD, NCDB, COURTS, JAIL) with a per-system
kill switch, `external_system_logs` capturing an inbound + outbound pair per
call, and every mutating endpoint enqueuing a domain event
(`IntegrationConfigUpdated`, `ExternalSystemCallLogged`) that audit-service
consumes into its hash-chained log (FR-INT-05 + FR-AUD-01).

**What's stubbed:** `POST /adapters/{system_name}/call` logs a well-formed
request/response pair and returns a response explicitly marked `mock: true`
— there is no outbound HTTP to any real endpoint. The SRS gives only a
one-line functional description per system, not a request/response contract,
so the adapter passes the request body through and echoes it rather than
validating against invented field names (CLAUDE.md rule 5).

**Resolve when:** each external system's real contract is available — then
per-system request/response schemas, an actual outbound client, auth/mTLS to
that system, and error/retry handling replace the stub in
`app/services/adapters.py`. One TD line, four independent unblocks (CAD,
NCDB, COURTS, JAIL).

---

## TD-006 — consistency-audit findings (2026-09-07)

A pass over all 10 services against the standing rules (audit event on every
mutating write / RBAC least-privilege / append-only where specified /
idempotency where relevant). Append-only (evidence `custody_events`, audit
`audit_logs`) is solidly enforced — REVOKE + BEFORE UPDATE/DELETE triggers
that block even the owner. RBAC is uniform (every mutating route has a
`.write`/`.approve` code). Open items:

- **Fixed now:** iam `PATCH /users/{id}` changing `full_name` / `email` /
  `station_id` (or a non-deactivation `status`) emitted nothing — a gap
  against rule 3 / FR-IAM-06 ("reassign user accounts ... every action
  written to the audit log"), and `station_id` is RBAC-scoping data. Now
  emits `UserUpdated` (`user.updated` -> audit `user`/`update`). The
  deactivation transition keeps its own richer `UserDeactivated` and isn't
  double-reported.
- **DONE 2026-09-07 (reopened + closed TD-003):** iam `POST /users/{id}/password`
  now emits `UserPasswordChanged` (with `by_admin`), and `POST /roles` /
  `PUT /roles/{id}/permissions` emit `RoleCreated` / `RolePermissionsChanged`
  — all through the existing outbox, mapped in audit-service. Every runtime
  FR-IAM-06 endpoint that writes identity_db now audits. See TD-003.
- **Decided 2026-09-07 — NOT a gap: successful logins / logouts / token
  refreshes stay out of the hash-chained audit trail.** Reasoning:
  FR-AUD-01 / SRS §5.8 scope the tamper-evident `audit_db.audit_logs` to
  *sensitive-record access and administrative actions* — immutable,
  oversight-facing, low-volume. A routine shift-start login (or a 15-minute
  token refresh) is neither: it is high-cardinality telemetry with little
  per-event forensic value, and folding it into the hash chain dilutes the
  trail's signal and inflates its size. The security-relevant transition —
  repeated failures leading to a lockout — is *already* captured as
  `AccountLockedOut`. CJIS-style authentication logging is a real
  requirement, but it belongs in a **separate operational security-event
  stream** (structured logs → SIEM, with its own retention), not this
  chain. **Recommended future work (own ticket, not this slice):** emit
  login-success / login-failure / logout / refresh to such a stream. No
  change to `audit_db`.
- **DONE 2026-09-07 (rule 6):** `POST /cases/{id}/statements`,
  `POST /cases/{id}/arrests` and `POST /evidence` now accept an optional
  `Idempotency-Key` and dedupe on it (nullable UNIQUE `client_sync_id`,
  case-service migration 0003 / evidence-service migration 0003), same
  200-with-original-record semantics as `POST /incidents`. Optional rather
  than required (rule 6 says "accept ... and dedupe"; required would break
  web-portal's existing forms). Field-PWA slice 2 uses them.
- **Judged not a gap:** `PUT /notification-preferences` emits no audit event.
  notification_db isn't in rule 3's scope ("case, evidence, HR/discipline,
  or IAM data"), it's a user's own self-service preference, and
  notification-service has no outbox wiring. Left as-is.
- **Minor, not changed:** `PUT /users/{id}/roles` is gated on
  `iam.role.write` where `iam.user.write` would read more naturally (it
  mutates a user, not a role definition). Defensible either way; left alone
  to avoid churn.

---

## Build order
Phase 0 pilot: **iam ✅ → case ✅ → evidence ✅ → Kafka + transactional outbox
✅ → audit-service ✅ → dashboard-service read models ✅**. Full event pipeline
(write → outbox → Kafka → audit hash chain + dashboard projections) verified
end-to-end, including `evidence.hash_mismatch` (verify-with-mismatch → audit
`read` entry + `mv_evidence_integrity.hash_mismatch_count`).

Phase 1 **complete (2026-09-06)** — all 10 services fully built:
hr (FR-HR-01..07), training (FR-TRAIN-01..03), community (FR-COMM-01..04),
notification (FR-NOTIF-01/02/03, TD-004), integration-gateway (FR-INT-01..05
framework, TD-005), plus dashboard `mv_unit_readiness` (FR-DASH-02). 42
event types flow into audit-service's hash chain.

**Schema-gap follow-up done 2026-09-06** (corrected SRS pulled first):
community migration 0003 (meetings.attendee_summary, concerns.description
NOT NULL + raised_by, follow_up_actions.description NOT NULL); hr migration
0006 (officers.supervisor_id, self-ref FK) + `OfficerSupervisorChanged`
event; notification migration 0003 (notification_templates.subject/body —
text now DB rows; notification_preferences + `GET`/`PUT
/notification-preferences`, delivery worker honours a disabled channel).
FR-COMM-04's supervisor-notification path is wired end to end and
live-verified: an overdue follow-up now produces a `FOLLOWUP_OVERDUE`
record for the assignee AND a `FOLLOWUP_OVERDUE_SUPERVISOR` record for the
assignee's supervisor.

**FR-CASE-07 done 2026-09-06** (the last deferred case-service piece):
`case_officers` (docs §9.3.2, table existed unused since migration 0001) is
now served — `GET`/`POST /cases/{id}/officers`, `DELETE
/cases/{id}/officers/{officer_id}`. POST upserts (201 assign / 200 re-role);
DELETE is a hard delete of the junction row (no §9.3.2 status column; case
history is untouched, FR-CASE-09 unaffected). Mutations require
`case.approve`, not `case.write` — staffing an investigation is a command
decision (docs §2.3, Station Commander); the SRS enumerates case actions as
read/write/approve/export, so no `case.assign` was invented. `CaseOfficer
Assigned` / `CaseOfficerUnassigned` events flow through the outbox:
audit-service records both (`case_officer` create/delete — 44 event types
now), notification-service turns `CaseOfficerAssigned` into a
`CASE_OFFICER_ASSIGNED` notification for the assigned officer (migration
0004 seeds the template). Live-verified across iam + case + notification +
audit: Patrol Officer opens a case -> Station Commander assigns an officer
-> notification row for that officer delivered (status `sent`) + audit
`case_officer/create`; unassign -> audit `case_officer/delete`, no
notification; a `case.write`-only token gets 403. **case-service's entire
original schema (docs §9.3.2) is now implemented.**

**Post-Phase-1 hardening — `pwa-debt-k8s` slice, all 3 phases complete
(2026-09-07):**
- **Phase 1 — offline field writes + idempotency ✅** (`972292f`, `cd257e3`).
  case-service migration 0003 and evidence-service migration 0003 add a
  nullable UNIQUE `client_sync_id`; `POST /cases/{id}/statements`,
  `POST /cases/{id}/arrests`, `POST /evidence` accept an optional
  `Idempotency-Key` and replay to 200-with-original-record, no duplicate
  event (see TD-006 rule-6 note). OpenAPI updated for all three. Tests:
  case 94→102, evidence 35→39. field-pwa gained statement / arrest /
  evidence offline capture — outbox in IndexedDB (file as base64 string,
  not Blob — flagged: `fake-indexeddb` + WebView/Safari Blob-in-IDB
  reliability), background sync on reconnect with the stored key,
  storage-quota surfacing. Idempotency helper extracted to `@pmp/core`.
  Live-verified: incident + evidence filed offline, queued, auto-synced on
  reconnect, server-computed SHA-256 matched, replay returned 200 with no
  duplicate row.
- **Phase 2 — audit-log debt ✅** (`ad80f79`). Folded into TD-003 /
  TD-006 above: iam password-change and role/permission mutations now
  audit; `PATCH /users/{id}` non-deactivation changes now emit
  `UserUpdated`; auth-success logging decided out of the hash chain (own
  future ticket). notification `suppressed` status split from `failed`
  (migration 0005) for the preference-disabled path. TD-004 reworded as a
  settled design decision, not an open gap; TD-005 untouched.
- **Phase 3 — Kubernetes manifests ✅** (`841ebf4`). `infra/k8s/` —
  generic, portable, **not cloud-specific and not deployed**. Plain YAML +
  Kustomize (no Helm), one dir per service per §3.6: Deployment (alembic
  initContainer + uvicorn, restricted PodSecurity), ClusterIP Service
  (never public, §3.5), ConfigMap, `secret.template.yaml` (REPLACE_ME keys
  only), HPA (CPU 70%; commented Kafka-lag External metric for the 3
  consumers per NFR-SCALE-01), per-namespace ResourceQuota, NetworkPolicy
  (ingress only from the gateway namespace). `cluster/` has the 12
  namespaces + per-namespace default-deny; evidence + hr are
  `pmp.gov/tier: sensitive` with a dedicated encryption-key Secret slot and
  stricter egress. Probes hit `/health`. Env-var names, DB names and ports
  cross-checked against each `app/config.py`, `init-databases.sql` and
  CLAUDE.md. **Validated, not deployed:** `kubectl kustomize infra/k8s |
  kubeconform -strict -kubernetes-version 1.29.0` → 92 resources, all
  valid, 0 errors; nothing applied to a cluster. `infra/k8s/README.md`
  lists everything a real deployment must still supply (images, secret
  values + manager, data plane, ingress/TLS, sizing — all placeholders).

**Open, flagged (not forgotten):** TD-004, TD-005 above. Plus:
- FR-TRAIN-04 style summary-reporting FR is deferred as
  reporting-over-existing-data (dashboard-service territory), not new
  domain state. (FR-COMM-05 / FR-HR-08 built in the must/should closeout.)

**FR-AUD-04 retention — the "keep indefinitely" domains (2026-09-08):**
case-service, evidence-service and audit-service have **no delete path** —
no purge job, and no `DELETE` against `cases` / `incidents` / `arrests` /
`statements` / `evidence_items` / `custody_events` / `audit_logs` in app
code or migrations (evidence `custody_events` and `audit_logs` are
additionally REVOKE + trigger append-only). Each config carries an
explicit `RETENTION_DAYS[_MINIMUM]` constant (env-overridable, default ~10
years) that documents the retention **floor** so it can't be silently
shortened. Only `notification_db.notifications` (90d) and
`integration_db.external_system_logs` (180d) have real scheduled purge
jobs (`app/services/retention.py` in each), per docs §9.6.

**Phase 5 — admin-editable per-service settings (2026-09-08):** the
operational knobs that were env-only are now runtime-editable by "ICT Admin"
(docs §2.3 platform administration), each behind its own service:
- **iam-service** `iam_settings` (migration 0011) + `GET`/`PATCH
  /iam-settings` — the full FR-IAM-07 password policy (min length, the four
  complexity toggles, history depth, max age). `IAM_PASSWORD_*` env vars are
  now the seed/default; a row overrides one at runtime. `app.security.
  passwords` reads a process-global cache (`app.services.settings`) reloaded
  on startup and after every PATCH — the same shape as the JWKS cache.
  Emits `IamSettingsUpdated` (`iam.settings_updated`) → audit
  `iam_settings`/`update`.
- **notification-service** `notification_settings` (migration 0007) +
  `GET`/`PATCH /notification-settings` — the retention window
  (`retention_days`, seeded from `NOTIFICATION_RETENTION_DAYS`). The
  retention worker reads the effective value each pass. No event:
  notification_db has no outbox and isn't in rule 3's audit scope (same call
  as `PUT /notification-preferences`, TD-006).
- **integration-gateway-service** `integration_settings` (migration 0004) +
  `GET`/`PATCH /integration-settings` — the `external_system_logs` retention
  window (`log_retention_days`, seeded from
  `INTEGRATION_GATEWAY_LOG_RETENTION_DAYS`). Emits `IntegrationSettings
  Updated` (`integration.settings_updated`) → audit
  `integration_settings`/`update` (this service already has outbox wiring,
  FR-INT-05).
- Six permission codes — `{iam,notification,integration}.settings.{read,
  write}` — seeded and granted to "ICT Admin" by **iam migration 0011**
  (one migration, all three services' codes). Deliberately NOT a single
  coarse `settings.write`, and deliberately NO `audit.settings.*`: the
  audit-service retention floor and the "keep indefinitely" domains above
  stay env-only compliance values, not operational knobs. The
  delivery-*failure* (365d) and audit floors are likewise left out of the
  editable set.
- audit-service maps both new event types (77 event types now). Tests:
  iam `test_settings.py` (7), notification `test_settings.py` (8),
  integration `test_settings.py` (8), audit consumer all-event-types
  updated.
