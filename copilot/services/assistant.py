"""Operator Assistant reasoning core.
Pipeline: intent detection -> context retrieval -> data retrieval ->
(LLM reasoning OR deterministic responder) -> safety validation -> response.
The LLM never invents application data; all facts come from context/tools."""
from __future__ import annotations
import json
import os
from typing import Dict, Any, Optional
from .context import build_context, context_digest, DEFAULT_OPERATOR, DEFAULT_MACHINE
from .task_optimizer import optimize_day
from .task_prediction import predict_for_task
from .safety import get_operator_insights
from .shift import generate_handover

# ---------- Safety validation layer ----------
SAFETY_TRIGGERS = ["hydraulic", "leak", "fire", "smoke", "brake", "brakes", "repair", "fix engine",
                   "override", "disable", "bypass", "electrical", "fuel leak", "tip over", "rollover",
                   "injured", "injury", "accident", "stuck", "trapped", "spark", "overheat"]

SAFETY_RESPONSE = {
    "en-IN": "Stop operation and follow the machine's approved shutdown and safety procedure. Do not attempt a repair yourself or approach a pressurised or energised component. Refer to the machine's official manual and notify your supervisor or a qualified technician immediately. If anyone is at risk, prioritise personal safety and site emergency procedures.",
    "hi-IN": "मशीन का संचालन तुरंत रोकें और स्वीकृत शटडाउन एवं सुरक्षा प्रक्रिया का पालन करें। स्वयं मरम्मत करने की कोशिश न करें और किसी दबाव वाले या ऊर्जावान हिस्से के पास न जाएँ। मशीन के आधिकारिक मैनुअल का पालन करें और तुरंत अपने सुपरवाइज़र या योग्य तकनीशियन को सूचित करें। यदि किसी को खतरा हो तो पहले सुरक्षा और साइट की आपातकालीन प्रक्रिया का पालन करें।",
    "es-ES": "Detenga la operación y siga el procedimiento aprobado de apagado y seguridad de la máquina. No intente reparar usted mismo ni se acerque a un componente presurizado o energizado. Consulte el manual oficial y avise de inmediato a su supervisor o a un técnico calificado.",
    "ta-IN": "இயந்திரத்தை நிறுத்தி, அங்கீகரிக்கப்பட்ட பாதுகாப்பு நடைமுறையைப் பின்பற்றவும். நீங்களே பழுதுபார்க்க முயற்சிக்க வேண்டாம். அதிகாரப்பூர்வ கையேட்டைப் பார்த்து உடனே உங்கள் மேற்பார்வையாளரிடம் தெரிவிக்கவும்.",
}

LANG_NAME = {"en-IN": "English", "hi-IN": "Hindi", "es-ES": "Spanish", "ta-IN": "Tamil"}


def is_safety_critical(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in SAFETY_TRIGGERS)


def detect_intent(text: str) -> str:
    t = text.lower()

    def has(*ks):
        return any(k in t for k in ks)

    if has("hello", "hi ", "good morning", "namaste", "नमस्ते", "hola"):
        return "greeting"
    if has("optimize", "optimise", "reorder", "rearrange", "better order", "बेहतर"):
        return "optimize"
    if has("why", "क्यों", "kyun", "kyon", "reason", "explain"):
        return "why_duration"
    if has("weather", "rain", "बारिश", "मौसम", "lluvia", "storm", "wind"):
        return "weather_impact"
    if has("next task", "अगला", "agla", "next"):
        return "next_task"
    if has("how long", "duration", "take", "समय", "kitna", "kitni", "predicted", "estimate"):
        return "task_duration"
    if has("finish", "on time", "complete today", "समय पर"):
        return "finish_on_time"
    if has("safety", "seatbelt", "alert", "सुरक्षा", "safe"):
        return "safety_status"
    if has("handover", "summary", "shift", "हैंडओवर", "सारांश"):
        return "handover"
    if has("today", "what do i", "tasks", "काम", "task"):
        return "today_tasks"
    if has("current", "now", "doing", "status", "अभी"):
        return "current_status"
    return "unknown"


def _L(lang: str, en: str, hi: str) -> str:
    return hi if lang == "hi-IN" else en


def deterministic_answer(text: str, lang: str, ctx: Dict[str, Any]) -> str:
    intent = detect_intent(text)
    op = ctx["operator"]["operator_name"].split(" ")[0]
    m = ctx["machine"]
    site = ctx["site"]
    nxt = ctx["nextTask"]
    cur = ctx["currentTask"]

    if intent == "greeting":
        return _L(lang,
            "Hello %s. You're on %s (%s) at %s. Ask me about your tasks, the weather, or safety." % (op, m["machine_model"], m["machine_id"], site["name"]),
            "नमस्ते %s। आप %s पर %s (%s) चला रहे हैं। अपने कार्यों, मौसम या सुरक्षा के बारे में पूछें।" % (op, site["name"], m["machine_model"], m["machine_id"]))

    if intent == "next_task":
        if not nxt:
            return _L(lang, "You have no more scheduled tasks today.", "आज आपके लिए कोई और कार्य निर्धारित नहीं है।")
        p = predict_for_task(nxt)
        return _L(lang,
            "Your next task is %s in %s at %s. Predicted duration %d min. Rain probability %d%%%s" % (
                nxt["task_type"], nxt["zone"], nxt["scheduled_start"], p["predicted"], nxt["rain_probability"],
                " — it may take longer than usual." if nxt["rain_probability"] > 50 else "."),
            "आपका अगला task %s है (%s, %s बजे)। अनुमानित समय %d मिनट। बारिश की संभावना %d%% है%s" % (
                nxt["task_type"], nxt["zone"], nxt["scheduled_start"], p["predicted"], nxt["rain_probability"],
                ", इसलिए इसमें सामान्य से अधिक समय लग सकता है।" if nxt["rain_probability"] > 50 else "।"))

    if intent == "today_tasks":
        lst = "; ".join("%s %s (%s)" % (t["scheduled_start"], t["task_type"], t["task_status"]) for t in ctx["tasks"])
        return _L(lang,
            "You have %d tasks today: %s. %d delayed, %d completed so far." % (ctx["counts"]["tasks"], lst, ctx["counts"]["delayed"], ctx["counts"]["completed"]),
            "आज आपके %d कार्य हैं: %s। %d देरी से, %d पूरे हो चुके हैं।" % (ctx["counts"]["tasks"], lst, ctx["counts"]["delayed"], ctx["counts"]["completed"]))

    if intent == "task_duration":
        t = nxt or cur
        if not t:
            return _L(lang, "No upcoming task to estimate.", "अनुमान के लिए कोई कार्य नहीं है।")
        p = predict_for_task(t)
        return _L(lang,
            "%s is predicted at %d min (historical expected %d min, difference %s%d min). Main factors: %s." % (
                t["task_type"], p["predicted"], p["expected"], "+" if p["difference"] >= 0 else "", p["difference"], p["reason"]),
            "%s के लिए अनुमानित समय %d मिनट है (ऐतिहासिक औसत %d मिनट, अंतर %s%d मिनट)। मुख्य कारण: %s।" % (
                t["task_type"], p["predicted"], p["expected"], "+" if p["difference"] >= 0 else "", p["difference"], p["reason"]))

    if intent == "why_duration":
        t = nxt or cur
        if not t:
            return _L(lang, "There's no active task to explain right now.", "अभी समझाने के लिए कोई सक्रिय कार्य नहीं है।")
        p = predict_for_task(t)
        f = p["factors"]
        return _L(lang,
            "%s may take about %d min because of: %s. Weather factor %sx, operator-skill factor %sx, machine-age factor %sx. These are combined with historical performance for similar tasks." % (
                t["task_type"], p["predicted"], p["reason"], f["weatherF"], f["skillF"], f["ageF"]),
            "%s में लगभग %d मिनट लग सकते हैं क्योंकि: %s। मौसम कारक %sx, कौशल कारक %sx, मशीन-आयु कारक %sx। इन्हें समान कार्यों के ऐतिहासिक प्रदर्शन के साथ जोड़ा गया है।" % (
                t["task_type"], p["predicted"], p["reason"], f["weatherF"], f["skillF"], f["ageF"]))

    if intent == "weather_impact":
        w = ctx["weather"]["current"]
        base = _L(lang,
            "Current weather: %s, %s°C, rain probability %s%%." % (w["weather_condition"], w["temperature"], w["rain_probability"]),
            "वर्तमान मौसम: %s, %s°C, बारिश की संभावना %s%%।" % (w["weather_condition"], w["temperature"], w["rain_probability"]))
        if ctx["weather"]["rainExpected"] and ctx["weather"]["rainStartHour"] is not None:
            base += " " + _L(lang,
                "Rain is expected around %02d:00." % ctx["weather"]["rainStartHour"],
                "लगभग %02d:00 बजे बारिश की संभावना है।" % ctx["weather"]["rainStartHour"])
        if nxt:
            base += " " + _L(lang,
                "Your next task, %s at %s, has %d%% rain probability%s" % (nxt["task_type"], nxt["scheduled_start"], nxt["rain_probability"],
                    " and similar tasks have taken longer in wet conditions — consider doing it earlier if the schedule allows." if nxt["rain_probability"] > 50 else "."),
                "आपका अगला task %s (%s) में बारिश की संभावना %d%% है%s" % (nxt["task_type"], nxt["scheduled_start"], nxt["rain_probability"],
                    "; गीली परिस्थितियों में ऐसे कार्यों में अधिक समय लगता है — यदि संभव हो तो इसे पहले करें।" if nxt["rain_probability"] > 50 else "।"))
        return base

    if intent == "optimize":
        o = optimize_day(ctx["tasks"], m["site_id"])
        if not o["changes"]:
            return _L(lang, "Your current schedule already avoids the weather windows well — no changes recommended.", "आपका मौजूदा शेड्यूल मौसम के हिसाब से पहले से ठीक है — कोई बदलाव आवश्यक नहीं।")
        changes = ", ".join("%s → %s" % (c["task"], c["to"]) for c in o["changes"])
        first = o["changes"][0]
        if o["completionOriginal"] != o["completionOptimized"]:
            tail_en = "Estimated completion improves from %s to %s." % (o["completionOriginal"], o["completionOptimized"])
            tail_hi = "अनुमानित समाप्ति %s से सुधरकर %s हो जाती है।" % (o["completionOriginal"], o["completionOptimized"])
        else:
            tail_en = "Completion stays around %s, but weather-sensitive work moves out of the rain window." % o["completionOptimized"]
            tail_hi = "समाप्ति लगभग %s रहती है, लेकिन मौसम-संवेदनशील कार्य बारिश से पहले हो जाता है।" % o["completionOptimized"]
        return _L(lang,
            "I recommend reordering: %s. Key change: %s %s" % (changes, first["reason"], tail_en),
            "मैं क्रम बदलने की सलाह देता हूँ: %s। मुख्य कारण: %s %s" % (changes, first["reason"], tail_hi))

    if intent == "safety_status":
        s = ctx["safety"]
        insights = get_operator_insights(ctx["operator"]["operator_id"])
        msg = _L(lang,
            "Seatbelt: %s. Today: %d safety alert(s), %d seatbelt violation(s)." % (s["seatbeltStatus"], s["todayAlerts"], s["seatbeltViolations"]),
            "सीटबेल्ट: %s। आज: %d सुरक्षा अलर्ट, %d सीटबेल्ट उल्लंघन।" % (s["seatbeltStatus"], s["todayAlerts"], s["seatbeltViolations"]))
        if s["lastAlertTime"]:
            msg += _L(lang, " Last alert at %s." % s["lastAlertTime"], " अंतिम अलर्ट %s बजे।" % s["lastAlertTime"])
        if insights:
            msg += " " + insights[0]["message"]
        return msg

    if intent == "finish_on_time":
        o = optimize_day(ctx["tasks"], m["site_id"])
        return _L(lang,
            'Based on remaining tasks and the forecast, current plan completes around %s. An optimized order would complete around %s. Say "optimize my day" to apply it.' % (o["completionOriginal"], o["completionOptimized"]),
            'शेष कार्यों और मौसम के आधार पर मौजूदा योजना लगभग %s बजे पूरी होगी। अनुकूलित क्रम लगभग %s बजे पूरा होगा। लागू करने के लिए "optimize my day" कहें।' % (o["completionOriginal"], o["completionOptimized"]))

    if intent == "handover":
        return generate_handover(ctx["operator"]["operator_id"], m["machine_id"])

    if intent == "current_status":
        if not cur:
            tail = ("Next: %s at %s." % (nxt["task_type"], nxt["scheduled_start"])) if nxt else ""
            tail_hi = ("अगला: %s %s बजे।" % (nxt["task_type"], nxt["scheduled_start"])) if nxt else ""
            return _L(lang, "You're between tasks. " + tail, "आप कार्यों के बीच हैं। " + tail_hi)
        return _L(lang,
            "You're currently doing %s in %s (%d%% through). Scheduled %s–%s." % (cur["task_type"], cur["zone"], ctx["progress"], cur["scheduled_start"], cur["scheduled_end"]),
            "आप अभी %s कर रहे हैं (%s, %d%% पूर्ण)। निर्धारित %s–%s।" % (cur["task_type"], cur["zone"], ctx["progress"], cur["scheduled_start"], cur["scheduled_end"]))

    return _L(lang,
        'I can help with your tasks, task timing, weather impact, day optimization, safety status, and shift handover. Try: "What\'s my next task?" or "Will the weather affect my work?"',
        'मैं आपके कार्यों, समय अनुमान, मौसम प्रभाव, दिन के अनुकूलन, सुरक्षा स्थिति और शिफ्ट हैंडओवर में मदद कर सकता हूँ। पूछें: "मेरा अगला task क्या है?" या "क्या मौसम मेरे काम को प्रभावित करेगा?"')


def _llm_reason(text: str, lang: str, ctx: Dict[str, Any], grounded: str) -> Optional[str]:
    import httpx
    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
    lang_name = LANG_NAME.get(lang, "English")
    system = (
        "You are the CAT Operator Copilot, a voice assistant for a construction machine operator.\n"
        "Rules:\n"
        "- Reply ONLY in %s. Keep it concise (2-4 sentences), calm and clear for someone near heavy machinery.\n"
        "- Use ONLY the facts in the CONTEXT and GROUNDED_ANSWER below. NEVER invent tasks, times, weather, safety events, or machine procedures.\n"
        "- For any machine repair / safety-critical procedure, do NOT give technical steps; advise following the official manual and contacting a supervisor.\n"
        "- The GROUNDED_ANSWER already contains the correct data-derived facts; rephrase it naturally, do not contradict its numbers." % lang_name
    )
    payload = {
        "model": model, "max_tokens": 400, "system": system,
        "messages": [{"role": "user", "content": "CONTEXT:\n%s\n\nGROUNDED_ANSWER (authoritative facts):\n%s\n\nOPERATOR QUESTION:\n%s" % (
            json.dumps(context_digest(ctx), indent=2, ensure_ascii=False), grounded, text)}],
    }
    try:
        r = httpx.post("https://api.anthropic.com/v1/messages", json=payload, timeout=8, headers={
            "content-type": "application/json", "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        })
        if r.status_code != 200:
            return None
        data = r.json()
        out = (data.get("content") or [{}])[0].get("text", "").strip()
        return out or None
    except Exception:
        return None


def ask_assistant(text: str, language: str = "en-IN", operator_id: Optional[str] = None,
                  machine_id: Optional[str] = None, offline: bool = False) -> Dict[str, Any]:
    ctx = build_context(operator_id or DEFAULT_OPERATOR, machine_id or DEFAULT_MACHINE)
    intent = detect_intent(text)

    if is_safety_critical(text):
        return {
            "intent": "safety_critical", "language": language, "safetyCritical": True,
            "source": "safety-layer", "answer": SAFETY_RESPONSE.get(language, SAFETY_RESPONSE["en-IN"]),
            "context": context_digest(ctx), "offline": offline,
        }

    # The reasoning core is fully on-device: intent + real data + templated answer.
    grounded = deterministic_answer(text, language, ctx)
    answer = grounded
    source = "on-device"  # deterministic, no network
    # Cloud LLM is OPTIONAL enrichment — skipped entirely when offline so the
    # assistant never blocks on a dead network.
    if not offline and os.environ.get("ANTHROPIC_API_KEY"):
        llm = _llm_reason(text, language, ctx, grounded)
        if llm:
            answer = llm
            source = "llm"

    return {
        "intent": intent, "language": language, "safetyCritical": False,
        "source": source, "answer": answer, "context": context_digest(ctx), "offline": offline,
    }
