#!/usr/bin/env bash
# Start the full CAT Operator Copilot stack: (optional local Postgres) + cloud + edge app.
# Reads CLOUD_DATABASE_URL from .env — if it points to a remote cloud DB (e.g. Neon),
# the local Postgres step is skipped. The cloud service auto-seeds reference data.
set -e
cd "$(dirname "$0")/.."

# Read the configured cloud DB (if any) from .env without sourcing (URL may contain '&').
CLOUD_URL_LINE=$(grep -E '^CLOUD_DATABASE_URL=' .env 2>/dev/null | head -1 | cut -d= -f2- || true)

if [ -z "$CLOUD_URL_LINE" ] || echo "$CLOUD_URL_LINE" | grep -qE 'localhost|127\.0\.0\.1'; then
  echo "→ Using LOCAL PostgreSQL (Homebrew)."
  export PATH="/opt/homebrew/opt/postgresql@14/bin:$PATH"
  pg_isready >/dev/null 2>&1 || pg_ctl -D /opt/homebrew/var/postgresql@14 -l /tmp/pg.log start
  sleep 2
  createdb cat_cloud 2>/dev/null || true
  export CLOUD_DATABASE_URL="postgresql://$(whoami)@localhost:5432/cat_cloud"
else
  echo "→ Using REMOTE cloud database from .env (e.g. Neon). Skipping local Postgres."
  # cloud_app.py and seed load CLOUD_DATABASE_URL from .env via python-dotenv.
fi

# Central cloud service (:9000) — auto-seeds reference data on startup.
uvicorn cloud_app:cloud --port 9000 &
CLOUD_PID=$!

# Edge app (operator copilot) on :8000
uvicorn app:app --port 8000 &
EDGE_PID=$!

echo ""
echo "  Operator Copilot (edge):  http://localhost:8000"
echo "  Central Cloud dashboard:  http://localhost:9000"
echo ""
trap "kill $CLOUD_PID $EDGE_PID 2>/dev/null" INT TERM
wait
