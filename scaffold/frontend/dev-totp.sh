#!/usr/bin/env bash
# Print the current 6-digit TOTP code for a dev account, refreshing every second.
# Usage: ./dev-totp.sh [BASE32_SECRET]
# Default secret is the one PORTAL-1 was enrolled with in this session.
set -euo pipefail

SECRET="${1:-NXARXSZUZPILJCECZTIFD23F6I7256WX}"
PY="$(dirname "$0")/../iam-service/.venv/bin/python"

exec "$PY" - "$SECRET" <<'PY'
import sys, time, pyotp
t = pyotp.TOTP(sys.argv[1])
try:
    while True:
        left = 30 - int(time.time()) % 30
        print(f"\r  code: {t.now()}   (rolls in {left:2d}s)   Ctrl-C to stop ", end="", flush=True)
        time.sleep(1)
except KeyboardInterrupt:
    print()
PY
