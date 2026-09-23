"""CAT Operator Copilot — FastAPI backend + server-rendered operator UI.

Run:  uvicorn app:app --reload --port 8000
"""
from __future__ import annotations
import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from copilot.services.context import build_context, get_today_tasks, DEFAULT_OPERATOR, DEFAULT_MACHINE
from copilot.services.task_prediction import predict_for_task
from copilot.services.task_optimizer import optimize_day, what_if
from copilot.services.safety import get_safety_status, get_operator_insights, get_recent_incidents
from copilot.services.shift import get_shift_summary, generate_handover
from copilot.services.assistant import ask_assistant
from copilot.services.voice import get_voice_service, extract_note
from copilot.services import store
from copilot import data as db

app = FastAPI(title="CAT Operator Copilot")
BASE = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))

PAGES = {
    "home": "Home", "assistant": "Assistant", "shift": "My Shift",
    "tasks": "Tasks", "safety": "Safety", "training": "Training",
}


# ---------------- Page routes ----------------
def _page(request: Request, page: str):
    return templates.TemplateResponse(page + ".html", {"request": request, "page": page, "pages": PAGES,
                                                       "disclaimer": db.meta["disclaimer"]})


@app.get("/")
def home(request: Request):
    return _page(request, "home")


@app.get("/assistant")
def assistant_page(request: Request):
    return _page(request, "assistant")


@app.get("/shift")
def shift_page(request: Request):
    return _page(request, "shift")


@app.get("/tasks")
def tasks_page(request: Request):
    return _page(request, "tasks")


@app.get("/safety")
def safety_page(request: Request):
    return _page(request, "safety")


@app.get("/training")
def training_page(request: Request):
    return _page(request, "training")


# ---------------- API routes ----------------
@app.get("/api/context")
def api_context(operator: str = DEFAULT_OPERATOR, machine: str = DEFAULT_MACHINE):
    return build_context(operator, machine)


@app.post("/api/assistant")
async def api_assistant(request: Request):
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty"}, status_code=400)
    return ask_assistant(text, body.get("language", "en-IN"), body.get("operatorId"), body.get("machineId"))


@app.get("/api/tasks")
def api_tasks(operator: str = DEFAULT_OPERATOR, machine: str = DEFAULT_MACHINE):
    tasks = []
    for t in get_today_tasks(operator, machine):
        tt = dict(t)
        tt["prediction"] = predict_for_task(t)
        tasks.append(tt)
    return {"tasks": tasks}


@app.get("/api/optimize")
def api_optimize(operator: str = DEFAULT_OPERATOR, machine: str = DEFAULT_MACHINE, rainHour: Optional[int] = None):
    tasks = get_today_tasks(operator, machine)
    m = db.get_machine(machine)
    if rainHour is not None:
        return what_if(tasks, m["site_id"], int(rainHour))
    return optimize_day(tasks, m["site_id"])


@app.get("/api/safety")
def api_safety(operator: str = DEFAULT_OPERATOR, machine: str = DEFAULT_MACHINE):
    return {
        "status": get_safety_status(operator, machine),
        "insights": get_operator_insights(operator),
        "incidents": get_recent_incidents(operator, machine, 10),
    }


def _shift_id(machine: str, date: str) -> str:
    return "SH-%s-%s" % (date, machine)


@app.get("/api/shift")
def api_shift_get(operator: str = DEFAULT_OPERATOR, machine: str = DEFAULT_MACHINE):
    summary = get_shift_summary(operator, machine)
    sid = summary["shift"]["shift_id"] if summary["shift"] else _shift_id(machine, db.TODAY)
    runtime_notes = store.get_notes(sid)
    state = store.get_shift_state(sid)
    handover = generate_handover(operator, machine, runtime_notes)
    out = dict(summary)
    out.update({
        "shiftId": sid, "runtimeNotes": runtime_notes,
        "runtimeState": (state or {}).get("status") or (summary["shift"] or {}).get("status") or "Active",
        "endedAt": (state or {}).get("endedAt"), "handover": handover,
    })
    return out


@app.post("/api/shift")
async def api_shift_post(request: Request):
    body = await request.json()
    operator = body.get("operatorId") or DEFAULT_OPERATOR
    machine = body.get("machineId") or DEFAULT_MACHINE
    summary = get_shift_summary(operator, machine)
    sid = summary["shift"]["shift_id"] if summary["shift"] else _shift_id(machine, db.TODAY)
    action = body.get("action")

    if action == "note":
        lang = body.get("language", "en-IN")
        note = extract_note(body.get("text", ""), lang)
        if body.get("source"):
            note["source"] = body["source"]
        store.add_note(sid, note)
        return {"ok": True, "note": note, "notes": store.get_notes(sid)}

    if action == "end":
        import datetime
        store.set_shift_state(sid, {"status": "Closed", "endedAt": datetime.datetime.utcnow().isoformat() + "Z"})
        return {"ok": True, "status": "Closed", "handover": generate_handover(operator, machine, store.get_notes(sid))}

    if action == "start":
        store.set_shift_state(sid, {"status": "Active"})
        return {"ok": True, "status": "Active"}

    return JSONResponse({"error": "unknown action"}, status_code=400)


@app.get("/api/operators")
def api_operators():
    pairs = []
    for s in db.shifts:
        if s["shift_date"] != db.TODAY:
            continue
        op = db.get_operator(s["operator_id"])
        m = db.get_machine(s["machine_id"])
        pairs.append({
            "operatorId": s["operator_id"], "machineId": s["machine_id"],
            "operatorName": op["operator_name"], "machineModel": m["machine_model"],
            "language": op["preferred_language"],
            "label": "%s · %s (%s)" % (op["operator_name"], m["machine_model"], m["machine_id"]),
        })
    return {"pairs": pairs, "operators": db.operators, "machines": db.machines}


@app.post("/api/voice/transcribe")
async def api_voice_transcribe(request: Request):
    body = await request.json()
    service = get_voice_service()
    if service.name == "browser":
        return {"provider": "browser", "useClientSpeech": True}
    try:
        result = service.transcribe_audio(body.get("audio", ""), body.get("language", "en-IN"))
        return {"provider": service.name, **result}
    except Exception:
        return {"provider": "browser", "useClientSpeech": True, "fallback": True}


@app.post("/api/voice/synthesize")
async def api_voice_synthesize(request: Request):
    body = await request.json()
    service = get_voice_service()
    if service.name == "browser":
        return {"provider": "browser", "useClientSpeech": True}
    try:
        audio = service.synthesize_speech(body.get("text", ""), body.get("language", "en-IN"))
        if not audio:
            return {"provider": "browser", "useClientSpeech": True}
        return {"provider": service.name, **audio}
    except Exception:
        return {"provider": "browser", "useClientSpeech": True, "fallback": True}
