"""Central cloud platform (mock) for CAT Operator Copilot.

A standalone FastAPI service backed by PostgreSQL. It receives store-and-forward
events synced from edge devices and aggregates them across the fleet. Ingest is
idempotent (ON CONFLICT DO NOTHING), so re-syncs never duplicate.

Run:  uvicorn cloud_app:cloud --port 9000
"""
from __future__ import annotations
import json
import os
from typing import Any, Dict, List

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

DATABASE_URL = os.environ.get("CLOUD_DATABASE_URL", "postgresql://%s@localhost:5432/cat_cloud" % os.environ.get("USER", "postgres"))

cloud = FastAPI(title="CAT Operator Copilot — Cloud")


def _conn():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id    TEXT PRIMARY KEY,
                device_id   TEXT,
                operator_id TEXT,
                machine_id  TEXT,
                shift_id    TEXT,
                type        TEXT,
                payload     JSONB,
                created_at  TIMESTAMPTZ,
                received_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        c.commit()


init_db()


@cloud.get("/cloud/health")
def health():
    try:
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT 1")
        return {"ok": True, "db": "postgres"}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=503)


@cloud.post("/cloud/ingest")
async def ingest(request: Request):
    body = await request.json()
    events: List[Dict[str, Any]] = body.get("events", [])
    acked: List[str] = []
    with _conn() as c, c.cursor() as cur:
        for e in events:
            cur.execute(
                """
                INSERT INTO events(event_id,device_id,operator_id,machine_id,shift_id,type,payload,created_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (e.get("event_id"), e.get("device_id"), e.get("operator_id"), e.get("machine_id"),
                 e.get("shift_id"), e.get("type"), json.dumps(e.get("payload")), e.get("created_at")),
            )
            acked.append(e.get("event_id"))  # idempotent: already-present ids ack too
        c.commit()
    return {"ok": True, "acked": acked, "count": len(acked)}


@cloud.get("/cloud/events")
def events(limit: int = 100):
    with _conn() as c, c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM events ORDER BY received_at DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
        cur.execute("SELECT COUNT(*) n, COUNT(DISTINCT device_id) d, COUNT(DISTINCT operator_id) o FROM events")
        agg = cur.fetchone()
    for r in rows:
        for k in ("created_at", "received_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
    return {"events": rows, "totals": agg}


@cloud.get("/cloud/reference")
def reference():
    tables = ["operators", "machines", "weather", "tasks", "telemetry", "shifts", "incidents", "sites"]
    counts = {}
    with _conn() as c, c.cursor() as cur:
        for t in tables:
            try:
                cur.execute("SELECT COUNT(*) FROM ref_%s" % t)
                counts[t] = cur.fetchone()[0]
            except Exception:
                counts[t] = 0
                c.rollback()
    return {"reference": counts}


@cloud.get("/", response_class=HTMLResponse)
def dashboard():
    return CLOUD_HTML


CLOUD_HTML = """<!DOCTYPE html><html><head><meta charset=utf-8><title>CAT Cloud — Fleet Events</title>
<meta name=viewport content="width=device-width, initial-scale=1">
<style>
:root{--bg:#0d1b12;--panel:#12251a;--line:#1f4030;--yellow:#FFCD11;--text:#E8F0EA;--gray:#7d9488}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,Arial,sans-serif}
header{display:flex;align-items:center;gap:14px;padding:20px 28px;border-bottom:1px solid var(--line)}
.badge{width:40px;height:40px;border-radius:10px;background:#1a7f45;display:grid;place-items:center;font-weight:800;color:#fff}
h1{font-size:20px;margin:0}.sub{color:var(--gray);font-size:13px}
.wrap{padding:24px 28px;max-width:1100px;margin:0 auto}
.stats{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px 22px;min-width:130px}
.stat .n{font-size:30px;font-weight:800;color:var(--yellow)}.stat .l{font-size:12px;color:var(--gray);text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:14px;overflow:hidden}
th,td{text-align:left;padding:11px 14px;font-size:14px;border-bottom:1px solid var(--line)}
th{color:var(--gray);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
tr:last-child td{border-bottom:none}
.pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:700;background:#1a7f4533;color:#5fd48b}
.live{display:inline-flex;align-items:center;gap:6px;color:#5fd48b;font-size:12px}.dot{width:8px;height:8px;border-radius:99px;background:#5fd48b;animation:b 1.2s infinite}@keyframes b{50%{opacity:.3}}
.mono{color:var(--gray);font-size:12px}
</style></head><body>
<header><div class=badge>☁</div><div><h1>CAT Operator Copilot — Central Cloud</h1>
<div class=sub>PostgreSQL fleet event store · <span class=live><span class=dot></span>live</span></div></div></header>
<div class=wrap>
<div class=stats>
<div class=stat><div class=n id=t-events>0</div><div class=l>Events</div></div>
<div class=stat><div class=n id=t-devices>0</div><div class=l>Edge devices</div></div>
<div class=stat><div class=n id=t-ops>0</div><div class=l>Operators</div></div>
</div>
<div class=label style="color:var(--gray);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin:6px 0 8px">Reference data (master, synced from edge)</div>
<div id=refstats class=stats></div>
<div class=label style="color:var(--gray);font-size:11px;text-transform:uppercase;letter-spacing:.05em;margin:16px 0 8px">Operator events (store-and-forward)</div>
<table><thead><tr><th>Received</th><th>Type</th><th>Operator</th><th>Machine</th><th>Device</th><th>Detail</th></tr></thead>
<tbody id=rows><tr><td colspan=6 class=mono>Waiting for synced events…</td></tr></tbody></table>
</div>
<script>
async function tick(){
  try{
    const d=await fetch('/cloud/events?limit=60').then(r=>r.json());
    document.getElementById('t-events').textContent=d.totals.n||0;
    document.getElementById('t-devices').textContent=d.totals.d||0;
    document.getElementById('t-ops').textContent=d.totals.o||0;
    const rows=d.events.map(e=>{
      const p=e.payload||{}; let detail=p.note||p.status||p.category||'';
      if(typeof detail==='object')detail=JSON.stringify(detail);
      return `<tr><td class=mono>${(e.received_at||'').slice(11,19)}</td><td><span class=pill>${e.type}</span></td>
      <td>${e.operator_id||'—'}</td><td>${e.machine_id||'—'}</td><td class=mono>${e.device_id||'—'}</td><td>${detail||''}</td></tr>`;
    }).join('');
    document.getElementById('rows').innerHTML=rows||'<tr><td colspan=6 class=mono>Waiting for synced events…</td></tr>';
  }catch(e){}
}
async function refStats(){
  try{
    const d=await fetch('/cloud/reference').then(r=>r.json());
    const r=d.reference||{};
    document.getElementById('refstats').innerHTML=Object.keys(r).map(k=>
      `<div class=stat><div class=n>${r[k]}</div><div class=l>${k}</div></div>`).join('');
  }catch(e){}
}
refStats();
tick(); setInterval(tick,2000);
</script></body></html>"""
