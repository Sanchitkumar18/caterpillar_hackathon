"""Safety + anomaly service. Transparent rule-based baselines over synthetic
telemetry. Cautious language: 'potential' patterns, never definitive claims."""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from .. import data


def get_safety_status(operator_id: str, machine_id: str) -> Dict[str, Any]:
    today_tel = [t for t in data.telemetry if t["date"] == data.TODAY and t["operator_id"] == operator_id and t["machine_id"] == machine_id]
    today_alerts = sum(1 for t in today_tel if t["safety_alert_triggered"] == "Yes")
    seatbelt_violations = sum(1 for t in today_tel if t["seatbelt_status"] == "Unfastened")
    latest = today_tel[-1] if today_tel else None
    today_incidents = [i for i in data.incidents if i["date"] == data.TODAY and i["operator_id"] == operator_id and i["machine_id"] == machine_id]
    level = "attention" if today_alerts > 0 else ("caution" if seatbelt_violations > 0 else "ok")
    alert_times = [t for t in today_tel if t["safety_alert_triggered"] == "Yes"]
    return {
        "level": level,
        "seatbeltStatus": latest["seatbelt_status"] if latest else "Unknown",
        "todayAlerts": today_alerts,
        "seatbeltViolations": seatbelt_violations,
        "incidents": today_incidents,
        "lastAlertTime": alert_times[-1]["timestamp"][11:16] if alert_times else None,
    }


def get_operator_insights(operator_id: str) -> List[Dict[str, str]]:
    hist = [t for t in data.telemetry if t["operator_id"] == operator_id]
    if not hist:
        return []
    insights: List[Dict[str, str]] = []

    avg_idle = sum(t["idling_time_min"] for t in hist) / len(hist)
    today_hist = [t for t in data.telemetry if t["operator_id"] == operator_id and t["date"] == data.TODAY]
    today_count = len(today_hist) or 1
    today_avg_idle = sum(t["idling_time_min"] for t in today_hist) / today_count
    if today_avg_idle > avg_idle * 1.4 and today_avg_idle > 30:
        insights.append({"type": "Idle", "severity": "caution",
            "message": "Potential excessive idling — today's average (%d min) is above this operator's historical baseline (%d min)." % (round(today_avg_idle), round(avg_idle))})

    seatbelt_rate = sum(1 for t in hist if t["seatbelt_status"] == "Unfastened") / len(hist)
    if seatbelt_rate > 0.15:
        insights.append({"type": "Seatbelt", "severity": "attention",
            "message": "Potential unusual pattern: seatbelt recorded unfastened in %d%% of records. Recommend reinforcing seatbelt use." % round(seatbelt_rate * 100)})

    alert_rate = sum(1 for t in hist if t["safety_alert_triggered"] == "Yes") / len(hist)
    if alert_rate > 0.2:
        insights.append({"type": "Safety alerts", "severity": "attention",
            "message": "Repeated safety alerts detected (%d%% of records). Suggest a safety review." % round(alert_rate * 100)})

    fuels = [t["fuel_used_l"] for t in hist]
    avg_fuel = sum(fuels) / len(fuels)
    max_fuel = max(fuels)
    if max_fuel > avg_fuel * 1.8:
        insights.append({"type": "Fuel", "severity": "info",
            "message": "Potential unusual fuel usage detected in some cycles (peak %.1f L vs average %.1f L)." % (max_fuel, avg_fuel)})
    return insights


def get_recent_incidents(operator_id: Optional[str] = None, machine_id: Optional[str] = None, limit: int = 8):
    filtered = [i for i in data.incidents
                if (not operator_id or i["operator_id"] == operator_id)
                and (not machine_id or i["machine_id"] == machine_id)]
    filtered.sort(key=lambda i: i["timestamp"], reverse=True)
    return filtered[:limit]
