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
3. **Route protection** — `/cases` (and any unknown path) redirects to `/login`
   when there is no non-expired token; a `401` from the API clears the token and
   bounces to `/login`.

No other pages, no mock data — it runs against the real services.

## Run it

```bash
cd frontend
npm install
npm run dev            # -> http://localhost:5180  (opens on /cases -> /login)
```

`npm run dev` starts Vite for `apps/web-portal`. Vite proxies same-origin paths
to each backend service (no CORS, no gateway needed in dev):

| browser path   | proxied to        | override env      |
|----------------|-------------------|-------------------|
| `/api/iam/*`   | `localhost:8001`  | `PMP_IAM_URL`     |
| `/api/case/*`  | `localhost:8002`  | `PMP_CASE_URL`    |

In staging/prod the API gateway (SRS §3.5) does this routing instead.

### Backend services that must be up first

```bash
cd ../infra && docker compose up -d          # Postgres (+ Kafka etc.)
cd ../iam-service   && .venv/bin/python -m alembic upgrade head && \
                       .venv/bin/python -m uvicorn app.main:app --port 8001
cd ../case-service  && .venv/bin/python -m alembic upgrade head && \
                       .venv/bin/python -m uvicorn app.main:app --port 8002
```

Only **iam-service (:8001)** and **case-service (:8002)** are needed for this
slice (plus the Postgres from docker-compose). Kafka/audit/dashboard/etc. are not
on the path.

### A user to log in with

The case list only shows cases the signed-in user leads (unless their role has
`case.approve`). Create a user and some cases led by them:

```bash
cd ../iam-service
.venv/bin/python -m scripts.create_user \
  --badge PORTAL-1 --password 'Portal!Passw0rd' --name 'Portal User' --roles 'Investigator'
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
