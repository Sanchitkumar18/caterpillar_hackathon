"""Weather service — reads synthetic hourly forecast and summarises it."""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from .. import data


def get_forecast(site_id: str, date: Optional[str] = None) -> List[Dict[str, Any]]:
    date = date or data.TODAY
    fc = [w for w in data.weather if w["site_id"] == site_id and w["date"] == date]
    return sorted(fc, key=lambda w: w["hour"])


def weather_at_hour(site_id: str, hour: int, date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    date = date or data.TODAY
    h = max(6, min(18, hour))
    return next((w for w in data.weather if w["site_id"] == site_id and w["date"] == date and w["hour"] == h), None)


def get_weather_context(site_id: str) -> Dict[str, Any]:
    forecast = get_forecast(site_id)
    now_hour = data.NOW_MINUTES // 60
    current = weather_at_hour(site_id, now_hour) or (forecast[0] if forecast else None)
    rain_window = next((w for w in forecast if w["hour"] > now_hour and w["weather_condition"] in ("Rainy", "Storm")), None)
    return {
        "current": current,
        "forecast": forecast,
        "rainExpected": rain_window is not None,
        "rainStartHour": rain_window["hour"] if rain_window else None,
        "summary": (
            "%s, %s°C, rain probability %s%%" % (current["weather_condition"], current["temperature"], current["rain_probability"])
            if current else "No forecast"
        ),
    }


def weather_factor(task_type: str, weather_cond: str, wind: float, rain_prob: float) -> float:
    f = 1.0
    if weather_cond == "Rainy":
        if task_type == "Trenching":
            f += 0.28
        elif task_type == "Earth Excavation":
            f += 0.18
        elif task_type == "Grading":
            f += 0.22
        else:
            f += 0.1
    if weather_cond == "Storm":
        f += 0.35
    if weather_cond == "Windy" or wind > 30:
        if task_type == "Demolition":
            f += 0.2
        if task_type in ("Material Movement", "Material Loading"):
            f += 0.12
    if rain_prob > 60 and weather_cond not in ("Rainy", "Storm"):
        f += 0.05
    return f
