"""Feature extraction from telemetry events."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from anvaya.models.telemetry import TelemetryEvent

FEATURE_COLUMNS = [
    "is_off_hours",
    "is_new_device",
    "is_privilege_escalation",
    "is_anomalous_process",
    "is_unusual_network",
    "is_lateral_movement",
    "hour_of_day",
    "is_weekend",
    "process_is_shell",
    "process_is_remote_tool",
    "has_lateral_flag",
    "event_type_code",
]

EVENT_TYPE_CODES = {
    "auth_login": 0,
    "auth_logout": 1,
    "process_create": 2,
    "network_connect": 3,
    "file_access": 4,
    "scheduled_task": 5,
    "privilege_change": 6,
    "lateral_move": 7,
}

SHELL_PROCESSES = {"cmd.exe", "powershell.exe", "bash", "sh"}
REMOTE_TOOLS = {"ssh", "scp", "psexec.exe", "mimikatz.exe"}


def _event_get(event: TelemetryEvent | dict[str, Any], key: str, default: Any = None) -> Any:
    """Read an event field without depending on Pydantic model_dump().

    SQLModel objects may be expired after a session.commit(); model_dump() can
    return an empty/None dictionary in that state, but attribute access still
    lazily loads the required field.  Plain dictionaries are passed through.
    """
    if isinstance(event, dict):
        return event.get(key, default)
    return getattr(event, key, default)


def extract_features(event: TelemetryEvent | dict[str, Any]) -> dict[str, float]:
    """Extract numeric features from a single telemetry event."""
    ts = _event_get(event, "timestamp")
    if isinstance(ts, str):
        from datetime import datetime
        try:
            ts = datetime.fromisoformat(ts)
        except Exception:
            ts = datetime.now()
    elif ts is None:
        from datetime import datetime
        ts = datetime.now()

    hour = ts.hour if hasattr(ts, "hour") else 0
    is_weekend = 1.0 if (hasattr(ts, "weekday") and ts.weekday() >= 5) else 0.0

    process = (_event_get(event, "process") or "").lower()
    event_type = _event_get(event, "event_type", "auth_login")
    if hasattr(event_type, "value"):
        event_type = event_type.value

    is_lateral_movement = _event_get(event, "is_lateral_movement", False)
    raw_event_type = _event_get(event, "event_type", "")
    if hasattr(raw_event_type, "value"):
        raw_event_type = raw_event_type.value

    features = {
        "is_off_hours": float(_event_get(event, "is_off_hours", False)),
        "is_new_device": float(_event_get(event, "is_new_device", False)),
        "is_privilege_escalation": float(_event_get(event, "is_privilege_escalation", False)),
        "is_anomalous_process": float(_event_get(event, "is_anomalous_process", False)),
        "is_unusual_network": float(_event_get(event, "is_unusual_network", False)),
        "is_lateral_movement": float(is_lateral_movement),
        "hour_of_day": float(hour),
        "is_weekend": is_weekend,
        "process_is_shell": 1.0 if process in SHELL_PROCESSES else 0.0,
        "process_is_remote_tool": 1.0 if process in REMOTE_TOOLS else 0.0,
        "has_lateral_flag": float(
            is_lateral_movement or (raw_event_type in ("lateral_move",))
        ),
        "event_type_code": float(EVENT_TYPE_CODES.get(event_type, 0)),
    }
    return features


def events_to_dataframe(events: list[TelemetryEvent | dict[str, Any]]) -> pd.DataFrame:
    """Convert a list of events to a feature DataFrame."""
    rows = [extract_features(e) for e in events]
    df = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    return df


def events_to_matrix(events: list[TelemetryEvent | dict[str, Any]]) -> np.ndarray:
    """Convert events to a numpy feature matrix."""
    df = events_to_dataframe(events)
    return df.values


def get_labels(events: list[TelemetryEvent | dict[str, Any]]) -> np.ndarray:
    """Extract ground-truth labels (1 = attack, 0 = normal)."""
    labels = []
    for e in events:
        if isinstance(e, TelemetryEvent):
            labels.append(1 if e.is_attack else 0)
        else:
            labels.append(1 if e.get("is_attack", False) else 0)
    return np.array(labels)
