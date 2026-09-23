"""Shift logging + AI-generated handover."""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from .. import data
from .weather import get_forecast


def get_shift_summary(operator_id: str, machine_id: str, date: Optional[str] = None) -> Dict[str, Any]:
    date = date or data.TODAY
    shift = next((s for s in data.shifts if s["shift_date"] == date and s["operator_id"] == operator_id and s["machine_id"] == machine_id), None)
    tasks = sorted([t for t in data.tasks if t["date"] == date and t["operator_id"] == operator_id and t["machine_id"] == machine_id],
                   key=lambda t: t["scheduled_start"])
    incidents = [i for i in data.incidents if i["date"] == date and i["operator_id"] == operator_id and i["machine_id"] == machine_id]
    operator = data.get_operator(operator_id)
    machine = data.get_machine(machine_id)

    completed = [t for t in tasks if t["task_status"] == "Completed"]
    delayed = [t for t in tasks if t["task_status"] == "Delayed"]
    pending = [t for t in tasks if t["task_status"] in ("Scheduled", "In Progress")]

    return {
        "shift": shift, "operator": operator, "machine": machine, "tasks": tasks,
        "completed": completed, "delayed": delayed, "pending": pending, "incidents": incidents,
        "metrics": {
            "fuel": shift["fuel_used_l"] if shift else 0,
            "idle": shift["idle_time_min"] if shift else 0,
            "loadCycles": shift["load_cycles"] if shift else 0,
            "safetyAlerts": shift["safety_alerts"] if shift else 0,
            "seatbeltViolations": shift["seatbelt_violations"] if shift else 0,
        },
    }


def generate_handover(operator_id: str, machine_id: str, notes: Optional[List[Dict[str, Any]]] = None, date: Optional[str] = None) -> str:
    notes = notes or []
    s = get_shift_summary(operator_id, machine_id, date)
    parts: List[str] = []

    if s["completed"]:
        types = list(dict.fromkeys(t["task_type"] for t in s["completed"]))
        parts.append("%s%s were completed successfully." % (", ".join(types[:3]), " and other tasks" if len(types) > 3 else ""))
    if s["delayed"]:
        d = s["delayed"][0]
        parts.append("%s in %s was delayed, coinciding with %s conditions." % (d["task_type"], d["zone"], d["weather_condition"].lower()))
    if s["metrics"]["safetyAlerts"]:
        n = s["metrics"]["safetyAlerts"]
        t = next((i for i in s["incidents"] if i["incident_type"] == "Safety alert"), None)
        parts.append("%d safety alert%s recorded%s — the next operator should review before continuing." % (
            n, "s were" if n > 1 else " was", (" at %s" % t["timestamp"][11:16]) if t else ""))
    if s["pending"]:
        parts.append("%s in %s remains incomplete and should be prioritised." % (s["pending"][0]["task_type"], s["pending"][0]["zone"]))
    if s["machine"]:
        fc = get_forecast(s["machine"]["site_id"])
        rain = next((w for w in fc if w["weather_condition"] in ("Rainy", "Storm")), None)
        if rain:
            parts.append("Rain is expected around %02d:00 — recommend completing weather-sensitive work before then." % rain["hour"])
    for n in notes:
        if n.get("category") == "task_delay" and n.get("task"):
            parts.append("Operator noted %s ran slower%s." % (n["task"].lower(), (" due to %s" % n["reason"].lower()) if n.get("reason") else ""))
        elif n.get("note"):
            parts.append('Operator note: "%s"' % n["note"])

    return " ".join(parts) if parts else "No significant events recorded this shift."
