"""Canonical Windows service-state normalization.

PowerShell 5.1 commonly serializes ServiceControllerStatus and ServiceStartMode
as integers.  All downstream code consumes the canonical values from here and
never compares raw enum output directly.
"""
from __future__ import annotations

from typing import Any


SERVICE_STATES = frozenset({
    "running", "stopped", "paused", "start_pending", "stop_pending",
    "continue_pending", "pause_pending", "unknown", "not_run", "unavailable",
})

_NUMERIC_STATES = {
    1: "stopped",
    2: "start_pending",
    3: "stop_pending",
    4: "running",
    5: "continue_pending",
    6: "pause_pending",
    7: "paused",
}

_TEXT_STATES = {
    "running": "running",
    "stopped": "stopped",
    "paused": "paused",
    "startpending": "start_pending",
    "stoppending": "stop_pending",
    "continuepending": "continue_pending",
    "pausepending": "pause_pending",
    "notrun": "not_run",
    "unavailable": "unavailable",
    "unknown": "unknown",
}

_NUMERIC_START_TYPES = {0: "boot", 1: "system", 2: "automatic", 3: "manual", 4: "disabled"}
_TEXT_START_TYPES = {
    "boot": "boot",
    "system": "system",
    "automatic": "automatic",
    "auto": "automatic",
    "manual": "manual",
    "disabled": "disabled",
    "unknown": "unknown",
    "notrun": "not_run",
    "unavailable": "unavailable",
}


def _compact(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def normalize_service_state(value: Any) -> str:
    if value is None:
        return "not_run"
    if isinstance(value, bool):
        return "unknown"
    if isinstance(value, (int, float)) and int(value) == value:
        return _NUMERIC_STATES.get(int(value), "unknown")
    compact = _compact(value)
    if compact.isdigit():
        return _NUMERIC_STATES.get(int(compact), "unknown")
    return _TEXT_STATES.get(compact, "unknown")


def normalize_start_type(value: Any) -> str:
    if value is None:
        return "not_run"
    if isinstance(value, bool):
        return "unknown"
    if isinstance(value, (int, float)) and int(value) == value:
        return _NUMERIC_START_TYPES.get(int(value), "unknown")
    compact = _compact(value)
    if compact.isdigit():
        return _NUMERIC_START_TYPES.get(int(compact), "unknown")
    return _TEXT_START_TYPES.get(compact, "unknown")


def normalize_service_record(record: dict[str, Any] | None, expected_name: str) -> dict[str, Any]:
    if record is None:
        return {
            "Name": expected_name,
            "DisplayName": expected_name,
            "state": "unavailable",
            "start_type": "unavailable",
            "raw_status": None,
            "raw_start_type": None,
        }
    return {
        "Name": str(record.get("Name") or expected_name),
        "DisplayName": str(record.get("DisplayName") or record.get("Name") or expected_name),
        "state": normalize_service_state(record.get("Status")),
        "start_type": normalize_start_type(record.get("StartType")),
        "raw_status": record.get("Status"),
        "raw_start_type": record.get("StartType"),
    }


def service_needs_attention(service: dict[str, Any]) -> bool:
    state = service.get("state", "unknown")
    start_type = service.get("start_type", "unknown")
    if state in {"paused", "start_pending", "stop_pending", "continue_pending", "pause_pending"}:
        return True
    return state == "stopped" and start_type in {"automatic", "boot", "system"}

