"""Shift-note + shift-state store, now backed by the durable SQLite edge store
as an append-only event log (the outbox that syncs to the central cloud).

Public functions keep their original names so the rest of the app is unchanged.
"""
from __future__ import annotations
from typing import Dict, List, Any, Optional
from . import edge_db


def _machine_from_shift(shift_id: str) -> Optional[str]:
    # shift_id format: SH-<date>-<machine_id>
    parts = shift_id.split("-")
    return parts[-1] if len(parts) >= 3 else None


def add_note(shift_id: str, note: Dict[str, Any], operator_id: Optional[str] = None,
             machine_id: Optional[str] = None) -> List[Dict[str, Any]]:
    edge_db.append_event("SHIFT_NOTE", note, operator_id=operator_id,
                         machine_id=machine_id or _machine_from_shift(shift_id), shift_id=shift_id)
    return get_notes(shift_id)


def get_notes(shift_id: str) -> List[Dict[str, Any]]:
    return [e["payload"] for e in edge_db.events_for_shift(shift_id, "SHIFT_NOTE")]


def set_shift_state(shift_id: str, state: Dict[str, Any], operator_id: Optional[str] = None) -> None:
    edge_db.append_event("SHIFT_STATE", state, operator_id=operator_id,
                         machine_id=_machine_from_shift(shift_id), shift_id=shift_id)


def get_shift_state(shift_id: str) -> Optional[Dict[str, Any]]:
    ev = edge_db.latest_event(shift_id, "SHIFT_STATE")
    return ev["payload"] if ev else None
