# PMP Front End

Monorepo per `CLAUDE.md` §"Monorepo layout":

```
frontend/
  apps/web-portal/     command web app (Vite + React 18 + TS + Tailwind 3)
  packages/ui/         shared Tailwind component library (@pmp/ui)
```

npm workspaces tie them together (`packages/ui` is consumed as `@pmp/ui`).

## Current scope — one real vertical slice

This is **not** the full portal. It is exactly:

1. **Login** — `/login`. Badge number + password → iam-service `/auth/login`, then
   the 6-digit TOTP code → `/auth/mfa/verify`. The returned RS256 access token is
   stored in `localStorage`. If the account has no authenticator yet, the screen
   shows the enrolment secret / `otpauth://` URI first.
2. **Case list** — `/cases`. `GET /api/v1/cases` on case-service with the bearer
   token, rendered as a table of **case number · status · lead officer**. Scope is
   enforced by the API: you see cases you lead, or every case if your role holds
   `case.approve`.
3. **File an incident** — `/incidents/new` (button on the case list). Form for
   `incident_type` / `description` / `station_id` (defaulted to the caller's
   station from the JWT) / `reported_at`; `reported_by` is the caller. `POST
   /api/v1/incidents` with a **client-generated `Idempotency-Key`** (UUID) that is
   **reused on every retry** of the same submission — this is the mechanism the
   offline field PWA will need. On success the new incident is shown with an
   **Escalate to a case** action (`POST /api/v1/cases`). Surfaces 422 (per-field),
   403 (missing `case.write`, explicit message), and a duplicate submit (server
   returns 200 with the original record — shown as "already filed", not an error).
   Online-only; no offline queue yet.
4. **Station dashboard** — `/dashboard` (link on the case list). Read-only
   `GET /api/v1/dashboard/kpis` on dashboard-service: open/closed case counts
   (`mv_station_case_kpis`) and a crime-trend breakdown by `incident_type`
   (`mv_crime_trends`), defaulted to the caller's own station and the current
   month, with a station-id + date-range filter (the endpoint supports both —
   checked its real response shape before wiring this up). No
   `mv_unit_readiness` — hr/training-service don't exist yet, so it has nothing
   to show. Requires `dashboard.view`; 403 is surfaced, not swallowed. These
   numbers are refreshed purely by the Kafka event pipeline (case-service →
   outbox → dashboard-service's consumer) — the page never triggers a refresh.
5. **Route protection** — protected routes (and any unknown path) redirect to
   `/login` when there is no non-expired token; a `401` from the API clears the
   token and bounces to `/login`.

No other pages, no mock data — it runs against the real services.

**Idempotency key lifetime** (`src/lib/idempotency.ts`): one key per submission
intent, held in a ref so it survives re-renders; every retry (network failure,
422-fix-and-resubmit, double click) sends the *same* key; only "File another
incident" rotates it. `src/__tests__/IncidentPage.test.tsx` asserts each of these.

## Run it

```bash
cd frontend
npm install
npm run dev            # -> http://localhost:5180  (opens on /cases -> /login)
```

`npm run dev` starts Vite for `apps/web-portal`. Vite proxies same-origin paths
to each backend service (no CORS, no gateway needed in dev):

| browser path   | proxied to        | override env          |
|----------------|-------------------|------------------------|
| `/api/iam/*`   | `localhost:8001`  | `PMP_IAM_URL`          |
| `/api/case/*`  | `localhost:8002`  | `PMP_CASE_URL`         |
| `/api/dash/*`  | `localhost:8007`  | `PMP_DASHBOARD_URL`   |

In staging/prod the API gateway (SRS §3.5) does this routing instead.

### Backend services that must be up first

```bash
cd ../infra && docker compose up -d          # Postgres + Kafka + Zookeeper
cd ../iam-service       && .venv/bin/python -m alembic upgrade head && \
                           .venv/bin/python -m uvicorn app.main:app --port 8001
cd ../case-service      && .venv/bin/python -m alembic upgrade head && \
                           .venv/bin/python -m uvicorn app.main:app --port 8002
cd ../dashboard-service && .venv/bin/python -m alembic upgrade head && \
                           .venv/bin/python -m uvicorn app.main:app --port 8007
```

**iam-service (:8001)** and **case-service (:8002)** cover login/case-list/incident
filing. The **dashboard** screen additionally needs **dashboard-service (:8007)**,
Kafka (from docker-compose), and case-service's outbox relay actually running
(the default when you start it normally) — the KPI numbers only move because
dashboard-service consumes the `CaseOpened`/`CaseStatusChanged` events case-service
publishes.

### Users to log in with

The case list only shows cases the signed-in user leads, unless their role has
`case.approve` (which also grants `dashboard.view`, needed for `/dashboard`):

```bash
cd ../iam-service
# files/escalates incidents, sees only their own cases
.venv/bin/python -m scripts.create_user \
  --badge PORTAL-1 --password 'Portal!Passw0rd' --name 'Portal User' --roles 'Investigator'

# sees all cases at their station + the dashboard; give it the SAME --station as
# PORTAL-1 above if you want its dashboard to reflect PORTAL-1's cases
.venv/bin/python -m scripts.create_user \
  --badge PORTAL-CMD --password 'Portal!Passw0rd' --name 'Portal Commander' \
  --station <PORTAL-1's station_id> --roles 'Station Commander'
```

### The 6-digit code (MFA is real and required — FR-IAM-01)

First sign-in for a brand-new account: enter badge + password, and the screen
shows a **TOTP secret** — add it to an authenticator app (manual / "setup key"),
then enter the current code.

For a dev account whose secret you already have, skip the app:

```bash
./dev-totp.sh                       # live-refreshing code for PORTAL-1
./dev-totp.sh <YOUR_BASE32_SECRET>  # for a different account
```

or one-shot:

```bash
../iam-service/.venv/bin/python -c \
  "import pyotp; print(pyotp.TOTP('NXARXSZUZPILJCECZTIFD23F6I7256WX').now())"
```

(The code rotates every 30 s — type it promptly.)

## Test

```bash
npm test               # vitest (component + unit) for apps/web-portal
```

Covers: token decode/expiry/guard logic, `RequireAuth` redirect behaviour, the
login state machine (credentials → MFA → token, plus the 401/423/enrol paths),
and the case-list rendering / empty / 403 / 401 states. API calls are mocked in
these tests; the honest end-to-end check is opening it in a browser against the
running services.
