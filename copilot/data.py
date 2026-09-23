"""Central synthetic-data access layer. Loads generated JSON at import time."""
from __future__ import annotations
import json
import os
from typing import Optional, List, Dict, Any

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _load(name: str):
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)


sites: List[Dict[str, Any]] = _load("sites.json")
machines: List[Dict[str, Any]] = _load("machines.json")
operators: List[Dict[str, Any]] = _load("operators.json")
weather: List[Dict[str, Any]] = _load("weather.json")
tasks: List[Dict[str, Any]] = _load("tasks.json")
telemetry: List[Dict[str, Any]] = _load("telemetry.json")
shifts: List[Dict[str, Any]] = _load("shifts.json")
incidents: List[Dict[str, Any]] = _load("incidents.json")
meta: Dict[str, Any] = _load("meta.json")

TODAY: str = meta["today"]
NOW: str = meta["now"]


def _now_minutes() -> int:
    hhmm = NOW[11:16].split(":")
    return int(hhmm[0]) * 60 + int(hhmm[1])


NOW_MINUTES = _now_minutes()


def to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def fmt_time(minutes: int) -> str:
    return "%02d:%02d" % (minutes // 60, round(minutes % 60))


def get_operator(oid: str) -> Optional[Dict[str, Any]]:
    return next((o for o in operators if o["operator_id"] == oid), None)


def get_machine(mid: str) -> Optional[Dict[str, Any]]:
    return next((m for m in machines if m["machine_id"] == mid), None)


def get_site(sid: str) -> Optional[Dict[str, Any]]:
    return next((s for s in sites if s["site_id"] == sid), None)
