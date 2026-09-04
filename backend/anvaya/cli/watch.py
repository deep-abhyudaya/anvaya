"""`anvaya watch` — real-time telemetry watcher and live scorer."""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from sqlmodel import Session, select

from anvaya.db import get_session_sync, init_db
from anvaya.live import score_and_maybe_flag
from anvaya.logging import get_logger
from anvaya.ml.alertness import AlertnessEngine
from anvaya.models.telemetry import TelemetryEvent

logger = get_logger("anvaya.cli.watch")

console = Console()


_PIPE_FIELDS = [
    "timestamp",
    "actor",
    "host",
    "event_type",
    "process",
    "source",
    "destination",
    "command",
    "is_off_hours",
    "is_new_device",
    "is_privilege_escalation",
    "is_anomalous_process",
    "is_unusual_network",
    "is_lateral_movement",
    "is_attack",
    "attack_family",
    "ground_truth_label",
]

_BOOL_FIELDS = {
    "is_off_hours",
    "is_new_device",
    "is_privilege_escalation",
    "is_anomalous_process",
    "is_unusual_network",
    "is_lateral_movement",
    "is_attack",
}


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_log_line(line: str) -> dict[str, Any] | None:
    """Parse a single log line into a TelemetryEvent-shaped dict.

    Supports JSON lines and a simple pipe-delimited format. Returns None for
    blank or unparseable lines.
    """
    line = line.strip()
    if not line:
        return None

    if line.startswith("{"):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return _normalise_event_dict(data)

    parts = line.split("|")
    if len(parts) < 4:
        return None

    data: dict[str, Any] = {}
    for idx, field in enumerate(_PIPE_FIELDS):
        if idx >= len(parts):
            break
        value = parts[idx].strip()
        if not value:
            continue
        if field in _BOOL_FIELDS:
            data[field] = _to_bool(value)
        else:
            data[field] = value
    return _normalise_event_dict(data)


def _normalise_event_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure a parsed dict can be used to build a TelemetryEvent."""
    normalised: dict[str, Any] = {
        "event_id": data.get("event_id", f"EVT-{os.urandom(4).hex().upper()}"),
        "scenario_id": data.get("scenario_id", ""),
        "event_type": data.get("event_type", "auth_login"),
        "actor": data.get("actor", ""),
        "host": data.get("host", ""),
        "process": data.get("process", ""),
        "source": data.get("source", ""),
        "destination": data.get("destination", ""),
        "command": data.get("command", ""),
        "is_off_hours": bool(data.get("is_off_hours", False)),
        "is_new_device": bool(data.get("is_new_device", False)),
        "is_privilege_escalation": bool(data.get("is_privilege_escalation", False)),
        "is_anomalous_process": bool(data.get("is_anomalous_process", False)),
        "is_unusual_network": bool(data.get("is_unusual_network", False)),
        "is_lateral_movement": bool(data.get("is_lateral_movement", False)),
        "is_attack": bool(data.get("is_attack", False)),
        "attack_family": data.get("attack_family", ""),
        "ground_truth_label": data.get("ground_truth_label", "normal"),
    }
    timestamp = data.get("timestamp")
    if timestamp:
        try:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            normalised["timestamp"] = dt
        except ValueError:
            normalised["timestamp"] = datetime.now(timezone.utc)
    else:
        normalised["timestamp"] = datetime.now(timezone.utc)
    return normalised


def _ensure_model_trained(session: Session) -> AlertnessEngine:
    """Load or train an Alertness model so live scoring has a model to use."""
    engine = AlertnessEngine(session)
    engine.load_latest()
    if engine.model is not None:
        return engine

    from anvaya.data import DataFactory
    from anvaya.models.telemetry import TelemetryEvent as TelemetryEventModel

    factory = DataFactory(session)
    if not session.exec(select(TelemetryEventModel)).first():
        console.print("[dim]No telemetry found; generating a small background dataset...[/dim]")
        factory.generate(
            {
                "seed": 42,
                "normal_count": 4,
                "suspicious_count": 2,
                "attack_count": 4,
                "include_self_correction": False,
            }
        )

    events = list(session.exec(select(TelemetryEventModel)).all())
    if not events:
        raise RuntimeError("No telemetry events available to train a model")

    console.print(f"[dim]Training Alertness model on {len(events)} events...[/dim]")
    engine = AlertnessEngine(session)
    metrics = engine.train(events)
    console.print(
        f"[dim]Model {metrics.get('model_id')} trained "
        f"(precision {metrics.get('precision', 0):.4f}, "
        f"recall {metrics.get('recall', 0):.4f})[/dim]"
    )
    return engine


def _synthetic_event(seed: int) -> dict[str, Any]:
    """Generate one synthetic telemetry event from a random scenario."""
    from anvaya.simulator.generator import TelemetryGenerator
    from anvaya.simulator.scenarios import get_all_scenarios

    rng = random.Random(seed)
    # Draw from the full catalog (normal + suspicious + attack), not attacks
    # only: a live feed of pure attacks flags everything, so the [normal] tag
    # could never appear and the demo cannot show the detector discriminating.
    scenario = rng.choice(get_all_scenarios())
    replay_id = f"WATCH-{seed}-{os.urandom(2).hex().upper()}"
    generator = TelemetryGenerator(seed=seed)
    events = generator.generate_for_scenario(
        scenario,
        base_time=datetime.now(timezone.utc),
        replay_id=replay_id,
        is_replay=False,
    )
    if not events:
        raise RuntimeError("Scenario produced no events")
    # Draw a random timeline position, not always events[0]: the first row of
    # every attack scenario is the same benign-looking auth_login (empty
    # process, no anomaly flags), so a fixed index produced an identical
    # feature vector — and therefore an identical score — on every tick.
    return rng.choice(events)


def _print_event_summary(event: TelemetryEvent, detection: dict[str, Any]) -> None:
    detected = detection.get("detected", False)
    ts = event.timestamp
    ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    color = "bold red" if detected else "dim"
    tag = "[DETECTED]" if detected else "[normal]"
    incident = detection.get("incident_id", "")
    incident_text = f" incident={incident}" if incident else ""
    event_type = event.event_type
    event_type_str = event_type.value if hasattr(event_type, "value") else str(event_type)
    console.print(
        f"[{color}]{tag} {ts_str} actor={event.actor} host={event.host} "
        f"type={event_type_str} process={event.process} "
        f"score={detection.get('score', 0):.4f}{incident_text}[/]"
    )


def _process_event_dict(data: dict[str, Any], session: Session) -> dict[str, Any]:
    """Create, persist, and score a single telemetry event."""
    ts = data.get("timestamp")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if isinstance(ts, datetime) and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    data["timestamp"] = ts
    event = TelemetryEvent(**data)
    session.add(event)
    session.commit()
    session.refresh(event)
    detection = score_and_maybe_flag(event, session)
    return {"event": event, "detection": detection}


def _tail_and_score(
    source: str,
    session: Session,
    interval: float,
    max_events: int,
) -> int:
    """Tail a log file and score each new line."""
    path = Path(source)
    if not path.exists():
        console.print(f"[red]Log file not found: {source}[/red]")
        raise typer.Exit(1)

    with path.open("r") as f:
        f.seek(0, os.SEEK_END)
        processed = 0
        while True:
            if 0 < max_events <= processed:
                break
            line = f.readline()
            if not line:
                time.sleep(interval)
                continue
            data = parse_log_line(line)
            if not data:
                continue
            result = _process_event_dict(data, session)
            _print_event_summary(result["event"], result["detection"])
            processed += 1
    return processed


def _synthetic_feed(
    session: Session,
    interval: float,
    max_events: int,
) -> int:
    """Generate a synthetic live feed and score each event."""
    _ensure_model_trained(session)
    processed = 0
    seed = int(time.time())
    while True:
        if 0 < max_events <= processed:
            break
        data = _synthetic_event(seed + processed)
        data["scenario_id"] = f"SYNTHETIC-{data.get('scenario_id', '')}"
        result = _process_event_dict(data, session)
        console.print(
            f"[dim][SYNTHETIC][/dim] {result['event'].timestamp.isoformat()} "
            f"actor={result['event'].actor} host={result['event'].host} "
            f"scenario={result['event'].scenario_id}"
        )
        _print_event_summary(result["event"], result["detection"])
        processed += 1
        if 0 < max_events <= processed:
            break
        sleep_for = max(0.1, interval * random.uniform(0.5, 1.5))
        time.sleep(sleep_for)
    return processed


def run_watch(
    source: str,
    interval: float,
    max_events: int,
    console_override: Console | None = None,
) -> int:
    """Run the watch loop for either a file or the synthetic feed."""
    global console
    if console_override:
        console = console_override

    init_db()
    session = get_session_sync()
    try:
        if source == "synthetic":
            console.print("[bold cyan]ANVAYA Watch — synthetic live feed[/bold cyan]")
            return _synthetic_feed(session, interval, max_events)

        console.print(f"[bold cyan]ANVAYA Watch — tailing {source}[/bold cyan]")
        return _tail_and_score(source, session, interval, max_events)
    finally:
        session.close()



