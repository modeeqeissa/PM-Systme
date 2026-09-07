#!/usr/bin/env bash
# Dev-only helper for exercising the web-portal against real backends.
# Local dev only — this MFA key and these passwords are throwaway, on the same
# footing as infra/docker-compose.yml's pmp_dev_only credentials.
#
#   ./dev-portal.sh up               # migrate + start iam/case/dashboard/hr/training/community
#   ./dev-portal.sh seed             # create PORTAL-* users, enroll MFA, save + print secrets
#   ./dev-portal.sh code PW-HR   # current 6-digit TOTP code for one account
#   ./dev-portal.sh codes            # current TOTP code for every seeded account
#   ./dev-portal.sh down             # stop the services this script started
#
# MFA (TOTP) is mandatory in iam-service by design (FR-IAM-01) and can't be
# switched off. To avoid re-entering a code all day, `up` starts iam-service
# with a 12h access-token TTL (dev only) so one sign-in lasts a work day.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCAFFOLD="$(cd "$HERE/.." && pwd)"
PIDDIR="$HERE/.dev-portal-pids"
SECRETS="$HERE/.dev-portal-secrets"        # gitignored; BADGE=BASE32SECRET lines
mkdir -p "$PIDDIR"

# Fixed so enrolled MFA secrets survive an iam-service restart. Dev only.
export IAM_MFA_ENC_KEY="${IAM_MFA_ENC_KEY:-h2QidqCUNaGOeo9g-OiLJRfUfKWCmVdRLr4EDzG-TL0=}"
export EVENTS_KAFKA_BOOTSTRAP="${EVENTS_KAFKA_BOOTSTRAP:-localhost:29092}"
# Dev only: one sign-in lasts ~12h so you don't re-do badge+password+TOTP all day.
export IAM_ACCESS_TOKEN_TTL="${IAM_ACCESS_TOKEN_TTL:-43200}"

PW='Portal!Passw0rd'
PY="$SCAFFOLD/iam-service/.venv/bin/python"

SERVICES=(iam-service:8001 case-service:8002 dashboard-service:8007
          hr-service:8006 training-service:8005 community-service:8004)

# badge : iam role (grants the permissions the matching nav section needs).
# Override the prefix if these collide: PORTAL_PREFIX=PW2 ./dev-portal.sh seed
P="${PORTAL_PREFIX:-PW}"
USERS=(
  "$P-HR:HR Officer"
  "$P-TRAIN:Training Officer"
  "$P-COMM:Community Liaison Officer"
  "$P-CMD:Station Commander"
)

up() {
  ( cd "$SCAFFOLD/infra" && docker compose up -d >/dev/null )
  for entry in "${SERVICES[@]}"; do
    svc="${entry%%:*}"; port="${entry##*:}"; dir="$SCAFFOLD/$svc"; py="$dir/.venv/bin/python"
    [ -x "$py" ] || { echo "!! $svc/.venv missing — skipping"; continue; }
    ( cd "$dir" && "$py" -m alembic upgrade head >/dev/null )
    if lsof -ti tcp:"$port" >/dev/null 2>&1; then echo "== $svc already on :$port"; continue; fi
    ( cd "$dir" && nohup "$py" -m uvicorn app.main:app --host 127.0.0.1 --port "$port" \
        --log-level warning >"$PIDDIR/$svc.log" 2>&1 & echo $! >"$PIDDIR/$svc.pid" )
    echo "== started $svc on :$port"
  done
  for _ in $(seq 1 40); do
    curl -sf http://127.0.0.1:8001/health >/dev/null && { echo "iam-service ready"; return; }
    sleep 0.5
  done
  echo "!! iam-service did not start — see $PIDDIR/iam-service.log"; exit 1
}

seed() {
  : > "$SECRETS"; chmod 600 "$SECRETS"
  for entry in "${USERS[@]}"; do
    badge="${entry%%:*}"; role="${entry##*:}"
    ( cd "$SCAFFOLD/iam-service" && "$PY" -m scripts.create_user \
        --badge "$badge" --password "$PW" --name "$badge" --roles "$role" >/dev/null 2>&1 ) \
      && echo "created $badge ($role)" || echo "$badge exists — reusing"
    secret="$("$PY" - "$badge" "$PW" <<'PYEOF'
import sys, httpx
badge, pw = sys.argv[1], sys.argv[2]
c = httpx.Client(base_url="http://127.0.0.1:8001", timeout=10)
mfa = c.post("/api/v1/auth/login", json={"badge_number": badge, "password": pw}).json()["mfa_token"]
r = c.post("/api/v1/auth/mfa/enroll", headers={"Authorization": f"Bearer {mfa}"}).json()
print(r["secret"] if "secret" in r else "")
PYEOF
)"
    [ -n "$secret" ] && echo "$badge=$secret" >> "$SECRETS"
  done
  echo
  printf '%-13s %-18s %s\n' BADGE PASSWORD "TOTP SECRET (base32)"
  while IFS='=' read -r b s; do printf '%-13s %-18s %s\n' "$b" "$PW" "$s"; done < "$SECRETS"
  echo
  echo "Sign in at http://localhost:5180 with badge + password + the code from:"
  echo "  ./dev-portal.sh code PW-HR"
}

code() {
  b="${1:?usage: dev-portal.sh code <BADGE>}"
  [ -f "$SECRETS" ] || { echo "run './dev-portal.sh seed' first"; exit 1; }
  s="$(grep "^$b=" "$SECRETS" | cut -d= -f2-)"
  [ -n "$s" ] || { echo "no secret saved for $b"; exit 1; }
  "$PY" -c "import pyotp,sys; print(pyotp.TOTP('$s').now())"
}

codes() {
  [ -f "$SECRETS" ] || { echo "run './dev-portal.sh seed' first"; exit 1; }
  while IFS='=' read -r b s; do
    [ -n "$b" ] || continue
    printf '%-13s %s\n' "$b" "$("$PY" -c "import pyotp; print(pyotp.TOTP('$s').now())")"
  done < "$SECRETS"
}

down() {
  for f in "$PIDDIR"/*.pid; do
    [ -e "$f" ] || continue
    kill "$(cat "$f")" 2>/dev/null && echo "stopped $(basename "$f" .pid)"; rm -f "$f"
  done
}

case "${1:-}" in
  up) up ;; seed) seed ;; code) shift; code "$@" ;; codes) codes ;; down) down ;;
  *) echo "usage: $0 {up|seed|code <BADGE>|codes|down}"; exit 1 ;;
esac
