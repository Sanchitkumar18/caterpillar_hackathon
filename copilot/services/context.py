"""Resolves the 'current' operational context — the single source of truth the
assistant reasons over. The LLM never invents these values."""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from .. import data
from ..data import to_minutes, NOW_MINUTES
from .weather import get_weather_context
from .safety import get_safety_status

DEFAULT_OPERATOR = "OP1001"
DEFAULT_MACHINE = "EXC001"


def get_today_tasks(operator_id: str, machine_id: str) -> List[Dict[str, Any]]:
    tasks = [t for t in data.tasks if t["date"] == data.TODAY and t["operator_id"] == operator_id and t["machine_id"] == machine_id]
    return sorted(tasks, key=lambda t: to_minutes(t["scheduled_start"]))


def get_current_task(tasks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    inprog = next((t for t in tasks if t["task_status"] == "In Progress"), None)
    if inprog:
        return inprog
    return next((t for t in tasks if to_minutes(t["scheduled_start"]) <= NOW_MINUTES < to_minutes(t["scheduled_end"]) and t["task_status"] != "Cancelled"), None)


def get_next_task(tasks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    upcoming = [t for t in tasks if t["task_status"] == "Scheduled" and to_minutes(t["scheduled_start"]) > NOW_MINUTES]
    upcoming.sort(key=lambda t: to_minutes(t["scheduled_start"]))
    return upcoming[0] if upcoming else None


def task_progress(task: Optional[Dict[str, Any]]) -> int:
    if not task:
        return 0
    s = to_minutes(task["scheduled_start"])
    e = to_minutes(task["scheduled_end"])
    if task["task_status"] in ("Completed", "Delayed"):
        return 100
    if NOW_MINUTES <= s:
        return 0
    return min(100, round((NOW_MINUTES - s) / max(1, e - s) * 100))


def build_context(operator_id: str = DEFAULT_OPERATOR, machine_id: str = DEFAULT_MACHINE) -> Dict[str, Any]:
    operator = data.get_operator(operator_id)
    machine = data.get_machine(machine_id)
    site = data.get_site(machine["site_id"])
    tasks = get_today_tasks(operator_id, machine_id)
    current_task = get_current_task(tasks)
    next_task = get_next_task(tasks)
    shift = next((s for s in data.shifts if s["shift_date"] == data.TODAY and s["operator_id"] == operator_id and s["machine_id"] == machine_id), None)
    weather = get_weather_context(machine["site_id"])
    safety = get_safety_status(operator_id, machine_id)

    return {
        "now": data.NOW, "today": data.TODAY, "operator": operator, "machine": machine, "site": site,
        "shift": shift, "tasks": tasks, "currentTask": current_task, "nextTask": next_task,
        "progress": task_progress(current_task), "weather": weather, "safety": safety,
        "counts": {
            "tasks": len(tasks),
            "delayed": sum(1 for t in tasks if t["task_status"] == "Delayed"),
            "completed": sum(1 for t in tasks if t["task_status"] == "Completed"),
            "safetyEvents": safety["todayAlerts"],
        },
    }


def context_digest(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "operator": ctx["operator"]["operator_name"],
        "machine": "%s · %s" % (ctx["machine"]["machine_model"], ctx["machine"]["machine_id"]),
        "site": ctx["site"]["name"],
        "currentTask": ("%s (%s)" % (ctx["currentTask"]["task_type"], ctx["currentTask"]["zone"])) if ctx["currentTask"] else None,
        "nextTask": ("%s @ %s" % (ctx["nextTask"]["task_type"], ctx["nextTask"]["scheduled_start"])) if ctx["nextTask"] else None,
        "shift": ctx["operator"]["shift_type"],
        "weather": ctx["weather"]["summary"],
    }
