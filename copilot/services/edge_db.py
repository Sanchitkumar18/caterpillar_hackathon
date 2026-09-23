"""Durable on-device (edge) store — SQLite.

This is the local system of record that lets the operator keep working with no
internet. Every locally-generated change is written as an APPEND-ONLY event with
a UUID (the "outbox"), so syncing to the central cloud is idempotent and
conflict-free: ship un-synced events, dedupe by event_id.
"""
from __future__ import annotations
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_DB_PATH = os.environ.get("EDGE_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "data", "edge.db"))


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id    TEXT PRIMARY KEY,
                seq         INTEGER,
                device_id   TEXT,
                operator_id TEXT,
                machine_id  TEXT,
                shift_id    TEXT,
                type        TEXT,
                payload     TEXT,
                created_at  TEXT,
                synced_at   TEXT
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE INDEX IF NOT EXISTS idx_events_unsynced ON events(synced_at);
            CREATE INDEX IF NOT EXISTS idx_events_shift ON events(shift_id, type);
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_meta(key: str) -> Optional[str]:
    with _conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


def set_meta(key: str, value: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=?", (key, value, value))


def device_id() -> str:
    did = get_meta("device_id")
    if not did:
        did = "EDGE-" + uuid.uuid4().hex[:8].upper()
        set_meta("device_id", did)
    return did


def append_event(type: str, payload: Dict[str, Any], operator_id: Optional[str] = None,
                 machine_id: Optional[str] = None, shift_id: Optional[str] = None) -> Dict[str, Any]:
    ev = {
        "event_id": uuid.uuid4().hex,
        "seq": int(time.time() * 1000),
        "device_id": device_id(),
        "operator_id": operator_id,
        "machine_id": machine_id,
        "shift_id": shift_id,
        "type": type,
        "payload": json.dumps(payload),
        "created_at": _now(),
        "synced_at": None,
    }
    with _conn() as c:
        c.execute(
            "INSERT INTO events(event_id,seq,device_id,operator_id,machine_id,shift_id,type,payload,created_at,synced_at) "
            "VALUES(:event_id,:seq,:device_id,:operator_id,:machine_id,:shift_id,:type,:payload,:created_at,:synced_at)", ev)
    ev["payload"] = payload
    return ev


def events_for_shift(shift_id: str, type: Optional[str] = None) -> List[Dict[str, Any]]:
    q = "SELECT * FROM events WHERE shift_id=?"
    args: List[Any] = [shift_id]
    if type:
        q += " AND type=?"
        args.append(type)
    q += " ORDER BY seq ASC"
    with _conn() as c:
        return [_row_to_event(r) for r in c.execute(q, args).fetchall()]


def latest_event(shift_id: str, type: str) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        r = c.execute("SELECT * FROM events WHERE shift_id=? AND type=? ORDER BY seq DESC LIMIT 1", (shift_id, type)).fetchone()
        return _row_to_event(r) if r else None


def unsynced_events(limit: int = 200) -> List[Dict[str, Any]]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM events WHERE synced_at IS NULL ORDER BY seq ASC LIMIT ?", (limit,)).fetchall()
        return [_row_to_event(r) for r in rows]


def mark_synced(event_ids: List[str]) -> None:
    if not event_ids:
        return
    ts = _now()
    with _conn() as c:
        c.executemany("UPDATE events SET synced_at=? WHERE event_id=?", [(ts, eid) for eid in event_ids])


def pending_count() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) n FROM events WHERE synced_at IS NULL").fetchone()["n"]


def total_count() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) n FROM events").fetchone()["n"]


def _row_to_event(r: sqlite3.Row) -> Dict[str, Any]:
    d = dict(r)
    try:
        d["payload"] = json.loads(d["payload"])
    except Exception:
        pass
    return d


init()
