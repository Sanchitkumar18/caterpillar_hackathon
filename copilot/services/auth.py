"""Operator authentication: PIN verification + signed session cookies.

- PINs are stored only as salted PBKDF2 hashes (data/credentials.json).
- The session is a signed, HTTP-only cookie: `base64(operator_id|machine_id).hmac`.
  The HMAC is keyed by SESSION_SECRET so the cookie cannot be forged client-side.
- Identity (operator + machine) is resolved server-side from the cookie; the
  client never gets to pick who it is via query params once auth is on.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional, Dict, Any, Tuple
from .. import data

_CRED_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "credentials.json")
with open(_CRED_PATH) as f:
    _CREDENTIALS: Dict[str, Any] = json.load(f)

COOKIE_NAME = "cat_session"
SESSION_TTL = 60 * 60 * 12  # 12 hours
_SECRET = os.environ.get("SESSION_SECRET", "dev-insecure-secret-change-me").encode()


def _hash_pin(pin: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), 100000).hex()


def verify_pin(operator_id: str, pin: str) -> bool:
    cred = _CREDENTIALS.get(operator_id)
    if not cred or not pin:
        return False
    expected = cred["pin_hash"]
    actual = _hash_pin(pin, cred["salt"])
    return hmac.compare_digest(expected, actual)


def machine_for_today(operator_id: str) -> Optional[str]:
    """The machine this operator is assigned to on the current (demo) day."""
    shift = next((s for s in data.shifts if s["shift_date"] == data.TODAY and s["operator_id"] == operator_id), None)
    return shift["machine_id"] if shift else None


# ---------- signed cookie ----------
def _sign(payload: str) -> str:
    sig = hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()
    return sig


def make_session(operator_id: str, machine_id: str) -> str:
    issued = str(int(time.time()))
    raw = "%s|%s|%s" % (operator_id, machine_id, issued)
    body = base64.urlsafe_b64encode(raw.encode()).decode()
    return "%s.%s" % (body, _sign(body))


def read_session(cookie: Optional[str]) -> Optional[Dict[str, str]]:
    if not cookie or "." not in cookie:
        return None
    body, sig = cookie.rsplit(".", 1)
    if not hmac.compare_digest(_sign(body), sig):
        return None
    try:
        raw = base64.urlsafe_b64decode(body.encode()).decode()
        operator_id, machine_id, issued = raw.split("|")
    except Exception:
        return None
    if int(time.time()) - int(issued) > SESSION_TTL:
        return None
    if operator_id not in _CREDENTIALS:
        return None
    return {"operator_id": operator_id, "machine_id": machine_id}


def authenticate(operator_id: str, pin: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (session_token, error). error is a human-readable string on failure."""
    if not verify_pin(operator_id, pin):
        return None, "Invalid operator ID or PIN."
    machine_id = machine_for_today(operator_id)
    if not machine_id:
        return None, "No active shift assigned to this operator today."
    return make_session(operator_id, machine_id), None
