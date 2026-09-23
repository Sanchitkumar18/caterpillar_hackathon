"""Store-and-forward synchronization: edge (SQLite outbox) -> central cloud.

Connectivity is treated as intermittent. Un-synced events accumulate locally and
are pushed to the cloud whenever it becomes reachable. Ingest is idempotent
(dedupe by event_id), so retries never duplicate.
"""
from __future__ import annotations
import os
from typing import Dict, Any, List
import httpx
from . import edge_db

CLOUD_URL = os.environ.get("CLOUD_URL", "http://localhost:9000")


def cloud_reachable() -> bool:
    try:
        r = httpx.get(CLOUD_URL + "/cloud/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def _serialise(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for e in events:
        out.append({
            "event_id": e["event_id"], "device_id": e["device_id"], "operator_id": e["operator_id"],
            "machine_id": e["machine_id"], "shift_id": e["shift_id"], "type": e["type"],
            "payload": e["payload"], "created_at": e["created_at"],
        })
    return out


def sync_now(limit: int = 200) -> Dict[str, Any]:
    pending = edge_db.unsynced_events(limit)
    if not pending:
        return {"ok": True, "synced": 0, "pending": 0, "cloud": cloud_reachable()}
    try:
        r = httpx.post(CLOUD_URL + "/cloud/ingest", json={"events": _serialise(pending)}, timeout=8.0)
        if r.status_code != 200:
            return {"ok": False, "error": "cloud returned %s" % r.status_code, "pending": edge_db.pending_count(), "cloud": True}
        acked = r.json().get("acked", [])
        edge_db.mark_synced(acked)
        edge_db.set_meta("last_sync", _now())
        return {"ok": True, "synced": len(acked), "pending": edge_db.pending_count(), "cloud": True}
    except Exception as e:
        return {"ok": False, "error": "cloud unreachable", "pending": edge_db.pending_count(), "cloud": False}


def status() -> Dict[str, Any]:
    return {
        "deviceId": edge_db.device_id(),
        "pending": edge_db.pending_count(),
        "total": edge_db.total_count(),
        "lastSync": edge_db.get_meta("last_sync"),
        "cloudUrl": CLOUD_URL,
    }


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
