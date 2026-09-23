#!/usr/bin/env bash
# Start the full CAT Operator Copilot stack: Postgres + cloud + edge app.
set -e
cd "$(dirname "$0")/.."

# 1. Postgres (Homebrew) — start if not running, ensure cat_cloud exists.
export PATH="/opt/homebrew/opt/postgresql@14/bin:$PATH"
pg_isready >/dev/null 2>&1 || pg_ctl -D /opt/homebrew/var/postgresql@14 -l /tmp/pg.log start
sleep 2
createdb cat_cloud 2>/dev/null || true
export CLOUD_DATABASE_URL="postgresql://$(whoami)@localhost:5432/cat_cloud"

# 2. Central cloud service (Postgres-backed) on :9000
uvicorn cloud_app:cloud --port 9000 &
CLOUD_PID=$!
sleep 3

# 2b. Seed reference/master data into the cloud DB (idempotent upsert)
python scripts/seed_cloud.py || true

# 3. Edge app (operator copilot) on :8000
uvicorn app:app --port 8000 &
EDGE_PID=$!

echo ""
echo "  Operator Copilot (edge):  http://localhost:8000"
echo "  Central Cloud dashboard:  http://localhost:9000"
echo ""
trap "kill $CLOUD_PID $EDGE_PID 2>/dev/null" INT TERM
wait
