"""Lightweight in-memory runtime store for operator-added shift notes and
shift open/close state during a demo session. (Not persisted — prototype.)"""
from __future__ import annotations
from typing import Dict, List, Any, Optional

_notes: Dict[str, List[Dict[str, Any]]] = {}
_shift_state: Dict[str, Dict[str, Any]] = {}


def add_note(shift_id: str, note: Dict[str, Any]) -> List[Dict[str, Any]]:
    _notes.setdefault(shift_id, []).append(note)
    return _notes[shift_id]


def get_notes(shift_id: str) -> List[Dict[str, Any]]:
    return _notes.get(shift_id, [])


def set_shift_state(shift_id: str, state: Dict[str, Any]) -> None:
    _shift_state[shift_id] = state


def get_shift_state(shift_id: str) -> Optional[Dict[str, Any]]:
    return _shift_state.get(shift_id)
