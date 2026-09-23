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
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from copilot.services.context import build_context, get_today_tasks
from copilot.services.task_prediction import predict_for_task
from copilot.services.task_optimizer import optimize_day, what_if
from copilot.services.safety import get_safety_status, get_operator_insights, get_recent_incidents
from copilot.services.shift import get_shift_summary, generate_handover
from copilot.services.assistant import ask_assistant
from copilot.services.voice import get_voice_service, extract_note
from copilot.services import store, auth
from copilot import data as db

app = FastAPI(title="CAT Operator Copilot")
BASE = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))

PAGES = {
    "home": "Home", "assistant": "Assistant", "shift": "My Shift",
    "tasks": "Tasks", "safety": "Safety", "training": "Training",
}


# ---------------- Auth helpers ----------------
def identity(request: Request) -> Optional[dict]:
    """Resolve (operator_id, machine_id) from the signed session cookie."""
    return auth.read_session(request.cookies.get(auth.COOKIE_NAME))


def _unauthorized():
    return JSONResponse({"error": "unauthorized"}, status_code=401)


# ---------------- Login ----------------
@app.get("/login")
def login_page(request: Request):
    if identity(request):
        return RedirectResponse("/", status_code=302)
    # Offer the operators who actually have a shift today as login hints.
    today_ops = []
    seen = set()
    for s in db.shifts:
        if s["shift_date"] == db.TODAY and s["operator_id"] not in seen:
            seen.add(s["operator_id"])
            op = db.get_operator(s["operator_id"])
            today_ops.append({"id": op["operator_id"], "name": op["operator_name"],
                              "machine": s["machine_id"], "lang": op["preferred_language"]})
    return templates.TemplateResponse("login.html", {"request": request, "operators": today_ops,
                                                     "disclaimer": db.meta["disclaimer"]})


@app.post("/api/login")
async def api_login(request: Request):
    body = await request.json()
    token, error = auth.authenticate((body.get("operatorId") or "").strip().upper(), (body.get("pin") or "").strip())
    if error:
        return JSONResponse({"error": error}, status_code=401)
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE_NAME, token, httponly=True, samesite="lax", max_age=auth.SESSION_TTL, path="/")
    return resp


@app.post("/api/logout")
def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


@app.get("/api/me")
def api_me(request: Request):
    ident = identity(request)
    if not ident:
        return _unauthorized()
    op = db.get_operator(ident["operator_id"])
    m = db.get_machine(ident["machine_id"])
    return {
        "operatorId": op["operator_id"], "operatorName": op["operator_name"],
        "machineId": m["machine_id"], "machineModel": m["machine_model"],
        "language": op["preferred_language"], "skillLevel": op["skill_level"],
        "label": "%s · %s (%s)" % (op["operator_name"], m["machine_model"], m["machine_id"]),
    }


# ---------------- Page routes (auth-gated) ----------------
def _page(request: Request, page: str):
    if not identity(request):
        return RedirectResponse("/login", status_code=302)
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


# ---------------- API routes (identity from cookie) ----------------
@app.get("/api/context")
def api_context(request: Request):
    ident = identity(request)
    if not ident:
        return _unauthorized()
    return build_context(ident["operator_id"], ident["machine_id"])


@app.post("/api/assistant")
async def api_assistant(request: Request):
    ident = identity(request)
    if not ident:
        return _unauthorized()
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "empty"}, status_code=400)
    return ask_assistant(text, body.get("language", "en-IN"), ident["operator_id"], ident["machine_id"])


@app.get("/api/tasks")
def api_tasks(request: Request):
    ident = identity(request)
    if not ident:
        return _unauthorized()
    tasks = []
    for t in get_today_tasks(ident["operator_id"], ident["machine_id"]):
        tt = dict(t)
        tt["prediction"] = predict_for_task(t)
        tasks.append(tt)
    return {"tasks": tasks}


@app.get("/api/optimize")
def api_optimize(request: Request, rainHour: Optional[int] = None):
    ident = identity(request)
    if not ident:
        return _unauthorized()
    tasks = get_today_tasks(ident["operator_id"], ident["machine_id"])
    m = db.get_machine(ident["machine_id"])
    if rainHour is not None:
        return what_if(tasks, m["site_id"], int(rainHour))
    return optimize_day(tasks, m["site_id"])


@app.get("/api/safety")
def api_safety(request: Request):
    ident = identity(request)
    if not ident:
        return _unauthorized()
    return {
        "status": get_safety_status(ident["operator_id"], ident["machine_id"]),
        "insights": get_operator_insights(ident["operator_id"]),
        "incidents": get_recent_incidents(ident["operator_id"], ident["machine_id"], 10),
    }


def _shift_id(machine: str, date: str) -> str:
    return "SH-%s-%s" % (date, machine)


@app.get("/api/shift")
def api_shift_get(request: Request):
    ident = identity(request)
    if not ident:
        return _unauthorized()
    operator, machine = ident["operator_id"], ident["machine_id"]
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
    ident = identity(request)
    if not ident:
        return _unauthorized()
    body = await request.json()
    operator, machine = ident["operator_id"], ident["machine_id"]
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


@app.post("/api/voice/transcribe")
async def api_voice_transcribe(request: Request):
    if not identity(request):
        return _unauthorized()
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
    if not identity(request):
        return _unauthorized()
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
