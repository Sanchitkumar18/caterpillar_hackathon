"""Transparent statistical task-duration predictor over synthetic history.
No overclaimed ML — a weighted historical baseline with explainable factors."""
from __future__ import annotations
from typing import Optional, Dict, Any
from .. import data
from .weather import weather_factor

SKILL_FACTOR = {"Beginner": 1.35, "Intermediate": 1.1, "Expert": 0.92}
BASE_MIN = {"Earth Excavation": 60, "Trenching": 45, "Material Loading": 30, "Grading": 35,
            "Demolition": 90, "Site Preparation": 40, "Material Movement": 25}


def historical_average(task_type: str, weather_cond: Optional[str] = None) -> Optional[int]:
    hist = [t for t in data.tasks if t["task_type"] == task_type and t["actual_time_min"] is not None
            and (not weather_cond or t["weather_condition"] == weather_cond)]
    if not hist:
        return None
    return round(sum(t["actual_time_min"] for t in hist) / len(hist))


def predict_duration(task_type: str, weather_cond: str, skill: str, machine_age: int,
                     wind: float = 10, rain_prob: float = 10) -> Dict[str, Any]:
    base = BASE_MIN.get(task_type, 45)
    skill_f = SKILL_FACTOR.get(skill, 1.1)
    age_f = 1 + machine_age * 0.012
    w_f = weather_factor(task_type, weather_cond, wind, rain_prob)

    model_est = base * skill_f * age_f * w_f
    hist = historical_average(task_type, weather_cond)
    predicted = round(model_est * 0.6 + hist * 0.4) if hist else round(model_est)
    expected = historical_average(task_type) or round(base)

    reasons = []
    if w_f > 1.15:
        reasons.append("%s conditions" % weather_cond.lower())
    if skill_f > 1.15:
        reasons.append("%s operator experience" % skill.lower())
    elif skill_f < 1:
        reasons.append("expert operator")
    if age_f > 1.05:
        reasons.append("older machine (%d yrs)" % machine_age)

    return {
        "predicted": predicted, "expected": expected, "difference": predicted - expected,
        "factors": {"skillF": round(skill_f, 2), "ageF": round(age_f, 2), "weatherF": round(w_f, 2)},
        "reason": " + ".join(reasons) if reasons else "nominal conditions",
    }


def predict_for_task(t: Dict[str, Any]) -> Dict[str, Any]:
    return predict_duration(t["task_type"], t["weather_condition"], t["operator_skill"],
                            t["machine_age_years"], t["wind_speed"], t["rain_probability"])
