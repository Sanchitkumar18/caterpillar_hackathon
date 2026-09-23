"""Weather-aware task optimizer + What-If simulator.
Reorders the day so weather-sensitive tasks avoid rain/storm windows while
respecting priority, and explains every change."""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from .. import data
from ..data import to_minutes, fmt_time, NOW_MINUTES
from .weather import get_forecast, weather_at_hour, weather_factor
from .task_prediction import predict_for_task

PRIORITY_RANK = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
SENSITIVITY = {"Grading": 1.0, "Trenching": 0.95, "Earth Excavation": 0.7, "Demolition": 0.6,
               "Site Preparation": 0.5, "Material Loading": 0.3, "Material Movement": 0.3}


def _schedule_from(task_list: List[Dict[str, Any]], start_min: int, site_id: str) -> List[Dict[str, Any]]:
    slots = []
    cursor = start_min
    for t in task_list:
        hour = cursor // 60
        w = weather_at_hour(site_id, hour)
        w_f = weather_factor(t["task_type"], w["weather_condition"], w["wind_speed"], w["rain_probability"]) if w else 1
        p = predict_for_task(t)
        dur = round(p["predicted"] * (w_f / (p["factors"]["weatherF"] or 1)))
        slots.append({"start": cursor, "task": t, "predicted": dur})
        cursor += dur + 12
    return slots


def _completion(slots: List[Dict[str, Any]]) -> int:
    if not slots:
        return 0
    last = slots[-1]
    return last["start"] + last["predicted"]


def _weather_penalty(slots: List[Dict[str, Any]], site_id: str) -> float:
    penalty = 0.0
    for s in slots:
        w = weather_at_hour(site_id, s["start"] // 60)
        if not w:
            continue
        if w["weather_condition"] in ("Rainy", "Storm"):
            penalty += SENSITIVITY.get(s["task"]["task_type"], 0.4) * (w["rain_probability"] / 100) * 10
    return penalty


def _serialise(s: Dict[str, Any]) -> Dict[str, Any]:
    t = s["task"]
    return {
        "task_id": t["task_id"], "task_type": t["task_type"], "zone": t["zone"], "priority": t["priority"],
        "start": fmt_time(s["start"]), "end": fmt_time(s["start"] + s["predicted"]), "predicted_min": s["predicted"],
    }


def optimize_day(tasks: List[Dict[str, Any]], site_id: str, start_min: int = NOW_MINUTES) -> Dict[str, Any]:
    fixed = [t for t in tasks if t["task_status"] != "Scheduled"]
    movable = [t for t in tasks if t["task_status"] == "Scheduled"]
    anchor = max([start_min, 8 * 60] + [to_minutes(t["scheduled_end"]) for t in fixed])

    original = _schedule_from(sorted(movable, key=lambda t: to_minutes(t["scheduled_start"])), anchor, site_id)

    forecast = get_forecast(site_id)
    now_hour = anchor // 60
    rain_window = next((w for w in forecast if w["hour"] >= now_hour and w["weather_condition"] in ("Rainy", "Storm")), None)

    def sort_key(t):
        sens = SENSITIVITY.get(t["task_type"], 0.4)
        prio = PRIORITY_RANK.get(t["priority"], 2)
        # primary weight: sensitivity (negated so higher sens sorts first) when rain expected
        sens_key = -sens if rain_window else 0
        return (sens_key, prio, to_minutes(t["scheduled_start"]))

    candidate = sorted(movable, key=sort_key)
    optimized = _schedule_from(candidate, anchor, site_id)

    changes = []
    orig_by_id = {o["task"]["task_id"]: o for o in original}
    for slot in optimized:
        orig = orig_by_id[slot["task"]["task_id"]]
        if orig["start"] != slot["start"]:
            sens = SENSITIVITY.get(slot["task"]["task_type"], 0.4)
            if slot["start"] < orig["start"] and rain_window and sens >= 0.7:
                reason = "Moved earlier — %s is weather-sensitive and rain is expected from %s." % (slot["task"]["task_type"], fmt_time(rain_window["hour"] * 60))
            elif slot["start"] > orig["start"]:
                reason = "Shifted later so a weather-sensitive, higher-priority task could use the clear window."
            else:
                reason = "Resequenced to reduce weather exposure."
            changes.append({
                "task": "%s (%s)" % (slot["task"]["task_type"], slot["task"]["zone"]),
                "from": fmt_time(orig["start"]), "to": fmt_time(slot["start"]), "reason": reason,
            })

    return {
        "rainExpected": rain_window is not None,
        "rainStartHour": rain_window["hour"] if rain_window else None,
        "original": [_serialise(s) for s in original],
        "optimized": [_serialise(s) for s in optimized],
        "changes": changes,
        "completionOriginal": fmt_time(_completion(original)),
        "completionOptimized": fmt_time(_completion(optimized)),
        "weatherPenaltyOriginal": round(_weather_penalty(original, site_id)),
        "weatherPenaltyOptimized": round(_weather_penalty(optimized, site_id)),
    }


def what_if(tasks: List[Dict[str, Any]], site_id: str, rain_start_hour: int, start_min: int = NOW_MINUTES) -> Dict[str, Any]:
    movable = sorted([t for t in tasks if t["task_status"] == "Scheduled"], key=lambda t: to_minutes(t["scheduled_start"]))
    anchor = max(start_min, 8 * 60)

    # Baseline keeps each task at its actual scheduled position so a hypothetical
    # rain hour lands on the tasks that really run then.
    baseline = [{"start": to_minutes(t["scheduled_start"]), "task": t, "predicted": predict_for_task(t)["predicted"]}
                for t in movable]

    def simulate_and_cascade(slots, from_anchor):
        """Apply rain penalty to tasks running at/after the rain hour, then push
        any downstream task that would overlap (delay propagation)."""
        out = []
        cursor = None
        for s in slots:
            start = s["start"] if cursor is None else max(s["start"], cursor)
            dur = s["predicted"]
            if start // 60 >= rain_start_hour:
                dur = round(dur * weather_factor(s["task"]["task_type"], "Rainy", 15, 80))
            out.append({**s, "start": start, "predicted": dur})
            cursor = start + dur + 12
        return out

    with_rain = simulate_and_cascade(baseline, anchor)

    # Optimized: sequence weather-sensitive work before the rain hour, packed from now.
    opt = optimize_day(tasks, site_id, start_min)
    movable_by_id = {m["task_id"]: m for m in movable}
    opt_slots = [{"start": to_minutes(o["start"]), "task": movable_by_id[o["task_id"]], "predicted": o["predicted_min"]}
                 for o in opt["optimized"]]
    with_rain_opt = simulate_and_cascade(opt_slots, anchor)

    return {
        "rainStartHour": rain_start_hour,
        "completionNoRain": fmt_time(_completion(baseline)),
        "completionWithRain": fmt_time(_completion(with_rain)),
        "completionOptimized": fmt_time(_completion(with_rain_opt)),
        "affected": sorted(set(s["task"]["task_type"] for s in with_rain if s["start"] // 60 >= rain_start_hour)),
        "baseline": [_serialise(s) for s in baseline],
        "withRain": [_serialise(s) for s in with_rain],
        "optimized": [_serialise(s) for s in with_rain_opt],
    }
