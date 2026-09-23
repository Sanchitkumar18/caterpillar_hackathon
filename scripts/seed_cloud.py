"""Load the reference/seed dataset (operators, machines, weather, tasks,
telemetry, shifts, incidents, sites) into the central cloud PostgreSQL.

This makes the cloud the full system of record: master/reference data +
store-and-forward operator events. In production this reference data would be
served from the cloud down to the edge; here we seed it once.

Uses the SAME connection string as the cloud service (CLOUD_DATABASE_URL).

Run:  python scripts/seed_cloud.py
"""
from __future__ import annotations
import json
import os

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except Exception:
    pass

import psycopg2
import psycopg2.extras

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(BASE, "data")
DATABASE_URL = os.environ.get("CLOUD_DATABASE_URL", "postgresql://%s@localhost:5432/cat_cloud" % os.environ.get("USER", "postgres"))

# dataset -> (json file, primary-key function)
DATASETS = {
    "sites": ("sites.json", lambda r: r["site_id"]),
    "operators": ("operators.json", lambda r: r["operator_id"]),
    "machines": ("machines.json", lambda r: r["machine_id"]),
    "tasks": ("tasks.json", lambda r: r["task_id"]),
    "telemetry": ("telemetry.json", lambda r: r["telemetry_id"]),
    "shifts": ("shifts.json", lambda r: r["shift_id"]),
    "incidents": ("incidents.json", lambda r: r["incident_id"]),
    "weather": ("weather.json", lambda r: "%s|%s" % (r["site_id"], r["timestamp"])),
}


def load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    for table, (fname, pk) in DATASETS.items():
        cur.execute(
            "CREATE TABLE IF NOT EXISTS ref_%s (id TEXT PRIMARY KEY, data JSONB, loaded_at TIMESTAMPTZ DEFAULT now())" % table
        )
        rows = load(fname)
        # operators: never store the (already hashed) PINs here — reference only
        payload = [(pk(r), json.dumps(r)) for r in rows]
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO ref_%s (id, data) VALUES %%s ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, loaded_at = now()" % table,
            payload,
        )
        print("  ref_%-10s %d rows" % (table, len(rows)))
    conn.commit()
    cur.close()
    conn.close()
    print("Reference data loaded into PostgreSQL (cat_cloud).")


if __name__ == "__main__":
    print("Seeding cloud reference data ->", DATABASE_URL)
    main()
