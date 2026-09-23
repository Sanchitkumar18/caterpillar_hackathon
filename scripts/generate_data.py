"""
CAT Operator Copilot — deterministic synthetic dataset generator (Python).

All values are SYNTHETIC hackathon data. Internally consistent and
trend-realistic, but they do NOT represent real Caterpillar operating
thresholds, policies, or specifications.

Usage: python scripts/generate_data.py
Output: ./data/*.json
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timedelta

OUT = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(OUT, exist_ok=True)


# ---------- Seeded PRNG (mulberry32, matches the original JS generator) ----------
class Rng:
    def __init__(self, seed: int):
        self.a = seed & 0xFFFFFFFF

    def next(self) -> float:
        self.a = (self.a + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.a
        t = (t ^ (t >> 15)) * (t | 1) & 0xFFFFFFFF
        t ^= (t + ((t ^ (t >> 7)) * (t | 61) & 0xFFFFFFFF)) & 0xFFFFFFFF
        t &= 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296


SEED = 20250501
rng = Rng(SEED)


def rand(lo, hi):
    return lo + rng.next() * (hi - lo)


def randi(lo, hi):
    return int(rand(lo, hi + 1))


def pick(arr):
    return arr[int(rng.next() * len(arr))]


def rnd1(n, d=1):
    return round(n, d)


def chance(p):
    return rng.next() < p


# ---------- Reference dimensions ----------
TODAY = "2026-09-23"
DAYS = 8


def date_str(offset_days: int) -> str:
    d = datetime.fromisoformat(TODAY) + timedelta(days=offset_days)
    return d.date().isoformat()


DATE_LIST = [date_str(-(DAYS - 1 - i)) for i in range(DAYS)]

SITES = [
    {"site_id": "SITE-A", "name": "North Ridge Quarry", "zones": ["Zone A", "Zone B", "Zone C"]},
    {"site_id": "SITE-B", "name": "Riverside Roadworks", "zones": ["Zone D", "Zone E"]},
]

MACHINES = [
    {"machine_id": "EXC001", "machine_type": "Excavator", "machine_model": "CAT 320", "base_hours": 1520.5, "age": 2, "site_id": "SITE-A"},
    {"machine_id": "EXC002", "machine_type": "Excavator", "machine_model": "CAT 336", "base_hours": 3110.0, "age": 4, "site_id": "SITE-A"},
    {"machine_id": "EXC003", "machine_type": "Excavator", "machine_model": "CAT 320", "base_hours": 780.2, "age": 1, "site_id": "SITE-B"},
    {"machine_id": "LOD001", "machine_type": "Wheel Loader", "machine_model": "CAT 966", "base_hours": 2450.7, "age": 3, "site_id": "SITE-A"},
    {"machine_id": "LOD002", "machine_type": "Wheel Loader", "machine_model": "CAT 950", "base_hours": 5300.1, "age": 6, "site_id": "SITE-B"},
    {"machine_id": "DOZ001", "machine_type": "Dozer", "machine_model": "CAT D6", "base_hours": 4020.4, "age": 5, "site_id": "SITE-A"},
    {"machine_id": "DOZ002", "machine_type": "Dozer", "machine_model": "CAT D5", "base_hours": 990.9, "age": 1, "site_id": "SITE-B"},
]

OPERATORS = [
    {"operator_id": "OP1001", "operator_name": "Arjun Mehta", "experience_years": 8, "skill_level": "Expert", "preferred_language": "en-IN", "training_level": "Advanced", "shift_type": "Day", "safety": 0.97, "speed": 1.0},
    {"operator_id": "OP1002", "operator_name": "Priya Nair", "experience_years": 5, "skill_level": "Intermediate", "preferred_language": "hi-IN", "training_level": "Standard", "shift_type": "Day", "safety": 0.9, "speed": 1.08},
    {"operator_id": "OP1003", "operator_name": "Ravi Kumar", "experience_years": 2, "skill_level": "Beginner", "preferred_language": "hi-IN", "training_level": "Basic", "shift_type": "Day", "safety": 0.78, "speed": 1.22},
    {"operator_id": "OP1004", "operator_name": "Sofia Alvarez", "experience_years": 11, "skill_level": "Expert", "preferred_language": "es-ES", "training_level": "Advanced", "shift_type": "Day", "safety": 0.98, "speed": 0.96},
    {"operator_id": "OP1005", "operator_name": "Daniel Okafor", "experience_years": 4, "skill_level": "Intermediate", "preferred_language": "en-IN", "training_level": "Standard", "shift_type": "Night", "safety": 0.88, "speed": 1.05},
    {"operator_id": "OP1006", "operator_name": "Meera Iyer", "experience_years": 6, "skill_level": "Intermediate", "preferred_language": "ta-IN", "training_level": "Standard", "shift_type": "Day", "safety": 0.92, "speed": 1.02},
]

TASK_TYPES = ["Earth Excavation", "Trenching", "Material Loading", "Grading", "Demolition", "Site Preparation", "Material Movement"]
TASK_MACHINE = {
    "Earth Excavation": ["Excavator"],
    "Trenching": ["Excavator"],
    "Material Loading": ["Wheel Loader"],
    "Material Movement": ["Wheel Loader"],
    "Grading": ["Dozer"],
    "Site Preparation": ["Dozer", "Excavator"],
    "Demolition": ["Excavator", "Dozer"],
}
TASK_BASE_MIN = {"Earth Excavation": 60, "Trenching": 45, "Material Loading": 30, "Grading": 35, "Demolition": 90, "Site Preparation": 40, "Material Movement": 25}
SKILL_FACTOR = {"Beginner": 1.35, "Intermediate": 1.1, "Expert": 0.92}
WEATHER_CONDITIONS = ["Sunny", "Cloudy", "Rainy", "Windy", "Storm"]
PRIORITIES = ["Critical", "High", "Medium", "Low"]

NOW_MIN = 11 * 60 + 5  # 11:05 reference "now" for today


def weather_factor(task_type, weather, wind, rain_prob):
    f = 1.0
    if weather == "Rainy":
        if task_type == "Trenching":
            f += 0.28
        elif task_type == "Earth Excavation":
            f += 0.18
        elif task_type == "Grading":
            f += 0.22
        else:
            f += 0.1
    if weather == "Storm":
        f += 0.35
    if weather == "Windy" or wind > 30:
        if task_type == "Demolition":
            f += 0.2
        if task_type in ("Material Movement", "Material Loading"):
            f += 0.12
    if rain_prob > 60 and weather not in ("Rainy", "Storm"):
        f += 0.05
    return f


def ground_from_weather(weather, rainfall):
    if weather == "Storm":
        return "Flooded"
    if weather == "Rainy" or rainfall > 3:
        return "Muddy"
    if weather == "Cloudy":
        return "Damp"
    return "Dry"


def fmt_time(h, m):
    return "%02d:%02d" % (h, m)


# ---------- Weather dataset ----------
weather = []
weather_lookup = {}


def day_weather_arc(is_today):
    arc = {}
    if is_today:
        for h in range(6, 19):
            if h < 12:
                arc[h] = "Cloudy" if h < 8 else "Sunny"
            elif h < 14:
                arc[h] = "Cloudy"
            else:
                arc[h] = "Rainy" if h < 17 else "Storm"
    else:
        base = pick(WEATHER_CONDITIONS)
        for h in range(6, 19):
            arc[h] = base if chance(0.7) else pick(WEATHER_CONDITIONS)
    return arc


for di, date in enumerate(DATE_LIST):
    is_today = date == TODAY
    for site in SITES:
        arc = day_weather_arc(is_today)
        for h in range(6, 19):
            cond = arc[h]
            if cond == "Storm":
                rain_prob = randi(80, 98)
            elif cond == "Rainy":
                rain_prob = randi(60, 90)
            elif cond == "Cloudy":
                rain_prob = randi(15, 45)
            elif cond == "Windy":
                rain_prob = randi(10, 30)
            else:
                rain_prob = randi(0, 15)
            rainfall = rnd1(rand(6, 20)) if cond == "Storm" else (rnd1(rand(1, 8)) if cond == "Rainy" else 0)
            wind = randi(28, 55) if cond == "Windy" else (randi(35, 65) if cond == "Storm" else randi(5, 22))
            temp = rnd1(rand(24, 34) - (4 if cond in ("Rainy", "Storm") else 0))
            humidity = randi(70, 95) if cond in ("Rainy", "Storm") else randi(35, 65)
            visibility = "Poor" if cond == "Storm" else ("Moderate" if cond == "Rainy" else "Good")
            rec = {
                "timestamp": "%sT%02d:00:00" % (date, h),
                "date": date, "hour": h, "site_id": site["site_id"],
                "temperature": temp, "humidity": humidity, "rain_probability": rain_prob,
                "rainfall_mm": rainfall, "wind_speed": wind, "weather_condition": cond,
                "visibility": visibility, "ground_condition": ground_from_weather(cond, rainfall),
            }
            weather.append(rec)
            weather_lookup["%s|%s|%d" % (date, site["site_id"], h)] = rec


def weather_at(date, site_id, hour):
    h = max(6, min(18, hour))
    return weather_lookup["%s|%s|%d" % (date, site_id, h)]


# ---------- Daily crew assignment ----------
# Deterministic, stable index-based pairing so the demo identity (Arjun / EXC001)
# is always valid. A fixed per-day rotation keeps assignments varied but repeatable.
def crew_for(date, site_id):
    site_machines = [m for m in MACHINES if m["site_id"] == site_id]
    ops = [o for o in OPERATORS if o["shift_type"] == "Day"]  # OP1001,OP1002,OP1003,OP1006
    # rotate by day so history varies, but never for TODAY (keep the demo crew fixed)
    day_offset = 0 if date == TODAY else (int(date.replace("-", "")) % len(ops))
    assignments = []
    for i, m in enumerate(site_machines):
        op = ops[(i + day_offset) % len(ops)]
        assignments.append({"machine": m, "operator": op})
    return assignments


# ---------- Tasks, telemetry, shifts, incidents ----------
tasks = []
telemetry = []
shifts = []
incidents = []
counters = {"task": 1, "tel": 1, "inc": 1}


def incident_rec(date, operator, machine, site, task_id, itype, severity, description, timestamp):
    rec = {
        "incident_id": "INC%04d" % counters["inc"],
        "timestamp": timestamp, "date": date, "operator_id": operator["operator_id"],
        "machine_id": machine["machine_id"], "site_id": site["site_id"], "task_id": task_id,
        "incident_type": itype, "severity": severity, "description": description,
        "status": "Resolved" if chance(0.6) else "Open",
        "resolution": "Reviewed with operator; no further action." if chance(0.6) else "Pending supervisor review.",
        "reported_by": "System", "shift_ref": None,
    }
    counters["inc"] += 1
    return rec


NOTE_BANK = [
    {"note": "Machine felt slower during the final excavation task.", "category": "machine", "task": None, "reason": None, "duration_minutes": None},
    {"note": "Trenching in Zone B was slower because of wet ground.", "category": "task_delay", "task": "Trenching", "reason": "Wet ground", "duration_minutes": 18},
    {"note": "Refuelled at midday, no issues afterwards.", "category": "general", "task": None, "reason": None, "duration_minutes": None},
]


def sample_notes(operator):
    out = []
    for _ in range(randi(0, 2)):
        base = dict(pick(NOTE_BANK))
        base["language"] = operator["preferred_language"]
        base["source"] = "voice"
        out.append(base)
    return out


def build_handover(operator, machine, day_tasks, agg):
    completed = [t["task_type"] for t in day_tasks if t["task_status"] == "Completed"]
    pending = [t for t in day_tasks if t["task_status"] in ("Scheduled", "In Progress")]
    delayed = [t for t in day_tasks if t["task_status"] == "Delayed"]
    parts = []
    if completed:
        parts.append("%s completed successfully." % ", ".join(completed))
    if delayed:
        d = delayed[0]
        parts.append("%s was delayed, coinciding with %s conditions." % (d["task_type"], d["weather_condition"].lower()))
    if agg["safety_alerts"]:
        parts.append("%d safety alert(s) recorded — review before continuing." % agg["safety_alerts"])
    if pending:
        parts.append("Next operator should prioritise %s in %s." % (pending[0]["task_type"], pending[0]["zone"]))
    return " ".join(parts)


for date in DATE_LIST:
    is_today = date == TODAY
    for site in SITES:
        for pairing in crew_for(date, site["site_id"]):
            machine = pairing["machine"]
            operator = pairing["operator"]
            # today gets a full 6-task day so 13:20 always has an in-progress +
            # upcoming tasks (needed for the live demo); history varies 4-6.
            n_tasks = 6 if is_today else randi(4, 6)
            cursor = 8 * 60
            day_tasks = []
            engine_hours = machine["base_hours"] + DATE_LIST.index(date) * rand(6, 9)
            agg = {"fuel": 0.0, "idle": 0, "load_cycles": 0, "safety_alerts": 0, "seatbelt": 0}

            for _ in range(n_tasks):
                suited = [tt for tt in TASK_TYPES if machine["machine_type"] in TASK_MACHINE[tt]]
                task_type = pick(suited if suited else TASK_TYPES)
                start_h, start_m = cursor // 60, cursor % 60
                zone = pick(site["zones"])
                w = weather_at(date, site["site_id"], start_h)

                base = TASK_BASE_MIN[task_type]
                est = round(base * (0.9 + rng.next() * 0.2))
                skill_f = SKILL_FACTOR[operator["skill_level"]]
                age_f = 1 + machine["age"] * 0.012
                w_f = weather_factor(task_type, w["weather_condition"], w["wind_speed"], w["rain_probability"])
                predicted = round(base * skill_f * age_f * w_f)

                end_planned = cursor + est
                status = "Completed"
                actual_start = actual_end = actual = None

                if is_today:
                    if end_planned <= NOW_MIN:
                        status = "Completed"
                    elif cursor <= NOW_MIN < end_planned:
                        status = "In Progress"
                    else:
                        status = "Scheduled"

                if status in ("Completed", "In Progress"):
                    noise = 1 + (rng.next() - 0.45) * 0.18
                    actual = round(predicted * noise * (operator["speed"] * 0.35 + 0.7))
                    actual_start = fmt_time(start_h, start_m)
                    if status == "Completed":
                        if w_f > 1.2 and chance(0.5):
                            status = "Delayed"
                        end_total = cursor + actual
                        actual_end = fmt_time(end_total // 60, end_total % 60)
                if is_today and status == "Scheduled" and chance(0.08):
                    status = "Cancelled"

                task_id = "T%04d" % counters["task"]
                counters["task"] += 1
                task_rec = {
                    "task_id": task_id, "task_type": task_type, "machine_id": machine["machine_id"],
                    "operator_id": operator["operator_id"], "site_id": site["site_id"], "zone": zone,
                    "date": date, "priority": pick(PRIORITIES),
                    "scheduled_start": fmt_time(start_h, start_m),
                    "scheduled_end": fmt_time(end_planned // 60, end_planned % 60),
                    "actual_start": actual_start, "actual_end": actual_end,
                    "weather_condition": w["weather_condition"], "temperature": w["temperature"],
                    "rain_probability": w["rain_probability"], "wind_speed": w["wind_speed"],
                    "ground_condition": w["ground_condition"], "operator_skill": operator["skill_level"],
                    "machine_age_years": machine["age"], "estimated_time_min": est,
                    "predicted_time_min": predicted, "actual_time_min": actual, "task_status": status,
                }
                tasks.append(task_rec)
                day_tasks.append(task_rec)

                fuel = rnd1(rand(2.0, 7.5) * (1.15 if machine["machine_type"] == "Dozer" else 1) * w_f, 1)
                load_cycles = randi(6, 18) if machine["machine_type"] == "Wheel Loader" else randi(1, 14)
                idle = randi(20, 70) if w["weather_condition"] in ("Rainy", "Storm") else randi(3, 35)
                engine_hours += (actual or predicted) / 60
                seatbelt_fastened = chance(operator["safety"])
                safety_alert = (not seatbelt_fastened and chance(0.6)) or (chance(1 - operator["safety"]) and chance(0.4))
                tel_rec = {
                    "telemetry_id": "TM%05d" % counters["tel"],
                    "timestamp": "%sT%s:00" % (date, fmt_time(start_h, start_m)), "date": date,
                    "machine_id": machine["machine_id"], "machine_type": machine["machine_type"],
                    "machine_model": machine["machine_model"], "operator_id": operator["operator_id"],
                    "engine_hours": rnd1(engine_hours, 1), "fuel_used_l": fuel, "load_cycles": load_cycles,
                    "idling_time_min": idle, "seatbelt_status": "Fastened" if seatbelt_fastened else "Unfastened",
                    "safety_alert_triggered": "Yes" if safety_alert else "No", "machine_age_years": machine["age"],
                    "site_id": site["site_id"], "site_zone": zone,
                    "operating_hours": rnd1((actual or predicted) / 60, 2), "task_id": task_id,
                    "machine_status": "Active" if status == "In Progress" else ("Idle" if status == "Scheduled" else "Active"),
                }
                counters["tel"] += 1
                telemetry.append(tel_rec)

                agg["fuel"] += fuel
                agg["idle"] += idle
                agg["load_cycles"] += load_cycles
                if safety_alert:
                    agg["safety_alerts"] += 1
                if not seatbelt_fastened:
                    agg["seatbelt"] += 1

                ts = tel_rec["timestamp"]
                if safety_alert:
                    incidents.append(incident_rec(date, operator, machine, site, task_id, "Safety alert", "Medium", "Safety alert triggered during operation.", ts))
                if not seatbelt_fastened and chance(0.7):
                    incidents.append(incident_rec(date, operator, machine, site, task_id, "Seatbelt violation", "Low", "Seatbelt recorded as unfastened.", ts))
                if idle > 55:
                    incidents.append(incident_rec(date, operator, machine, site, task_id, "Excessive idle", "Low", "High idle time (%d min) recorded." % idle, ts))
                if status == "Delayed":
                    wr = w_f > 1.2
                    incidents.append(incident_rec(date, operator, machine, site, task_id,
                        "Weather interruption" if wr else "Unexpected delay", "Medium",
                        ("%s slowed by %s conditions." % (task_type, w["weather_condition"].lower())) if wr else ("%s exceeded planned duration." % task_type), ts))

                cursor = end_planned + randi(5, 20)
                if cursor > 17 * 60:
                    break

            completed = sum(1 for t in day_tasks if t["task_status"] == "Completed")
            delayed = sum(1 for t in day_tasks if t["task_status"] == "Delayed")
            shift_id = "SH-%s-%s" % (date, machine["machine_id"])
            handover = build_handover(operator, machine, day_tasks, agg)
            shift_incidents = [i for i in incidents if i["date"] == date and i["machine_id"] == machine["machine_id"] and i["shift_ref"] is None]
            for i in shift_incidents:
                i["shift_ref"] = shift_id
            shifts.append({
                "shift_id": shift_id, "operator_id": operator["operator_id"], "machine_id": machine["machine_id"],
                "site_id": site["site_id"], "shift_date": date, "shift_start": "08:00",
                "shift_end": None if is_today else "17:00", "status": "Active" if is_today else "Closed",
                "tasks_assigned": len(day_tasks), "tasks_completed": completed, "tasks_delayed": delayed,
                "safety_alerts": agg["safety_alerts"], "seatbelt_violations": agg["seatbelt"],
                "idle_time_min": agg["idle"], "fuel_used_l": rnd1(agg["fuel"], 1),
                "load_cycles": agg["load_cycles"], "incidents": len(shift_incidents),
                "operator_notes": [] if is_today else sample_notes(operator),
                "handover_notes": None if is_today else handover,
            })


# ---------- Write ----------
def write(name, data):
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(data, f, indent=2)
    print("  %s: %s" % (name, ("%d records" % len(data)) if isinstance(data, list) else "object"))


meta = {
    "generated_at": datetime.utcnow().isoformat() + "Z",
    "seed": SEED, "today": TODAY, "now": "%sT11:05:00" % TODAY,
    "disclaimer": "All data is SYNTHETIC hackathon data. Values do not represent official Caterpillar operating thresholds, policies, or specifications.",
    "date_range": {"start": DATE_LIST[0], "end": DATE_LIST[-1]}, "counts": {},
}

print("Generating CAT Operator Copilot synthetic data...")
write("sites.json", SITES)
write("machines.json", MACHINES)
write("operators.json", OPERATORS)
write("weather.json", weather)
write("tasks.json", tasks)
write("telemetry.json", telemetry)
write("shifts.json", shifts)
write("incidents.json", incidents)

meta["counts"] = {
    "sites": len(SITES), "machines": len(MACHINES), "operators": len(OPERATORS),
    "weather": len(weather), "tasks": len(tasks), "telemetry": len(telemetry),
    "shifts": len(shifts), "incidents": len(incidents),
}
write("meta.json", meta)
print("Done.", json.dumps(meta["counts"]))
