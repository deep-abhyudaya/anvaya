"""Tests for real-time live scoring and the watch CLI."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from anvaya.cli.watch import parse_log_line, run_watch
from anvaya.config import settings
from anvaya.data import DataFactory
from anvaya.live import score_and_maybe_flag
from anvaya.live.dispatch import on_incident_event, on_project_created
from anvaya.live.enums import IncidentEventType
from anvaya.ml.alertness import AlertnessEngine
from anvaya.models.incident import Incident
from anvaya.models.project import Project
from anvaya.models.telemetry import TelemetryEvent
from rich.console import Console
from sqlmodel import Session, select


def _train_alertness_model(session: Session) -> str:
    """Generate a small dataset and train an Alertness model."""
    factory = DataFactory(session)
    factory.generate(
        {
            "seed": 1234,
            "normal_count": 6,
            "suspicious_count": 2,
            "attack_count": 6,
            "include_self_correction": False,
        }
    )
    events = list(session.exec(select(TelemetryEvent)).all())
    engine = AlertnessEngine(session)
    metrics = engine.train(events)
    return metrics["model_id"]


def _make_event(is_attack: bool, attack_family: str = "") -> TelemetryEvent:
    return TelemetryEvent(
        event_id="EVT-TEST-001",
        scenario_id="TEST-001",
        event_type="lateral_move",
        timestamp=datetime.now(timezone.utc),
        actor="eve",
        host="WS-001",
        process="ssh",
        source="WS-001",
        destination="JMP-01",
        is_off_hours=True,
        is_new_device=True,
        is_privilege_escalation=False,
        is_anomalous_process=False,
        is_unusual_network=True,
        is_lateral_movement=True,
        is_attack=is_attack,
        attack_family=attack_family if is_attack else "",
        ground_truth_label="attack" if is_attack else "normal",
    )


def test_score_and_maybe_flag_creates_incident_for_attack(db_session: Session) -> None:
    """A clearly anomalous event is detected and turned into an incident."""
    _train_alertness_model(db_session)

    event = _make_event(is_attack=True, attack_family="lateral_movement")
    detection = score_and_maybe_flag(event, db_session)

    assert detection["scored"] is True
    assert detection["detected"] is True
    assert detection["model_id"]
    assert "incident_id" in detection

    incident = db_session.exec(
        select(Incident).where(Incident.incident_id == detection["incident_id"])
    ).first()
    assert incident is not None
    assert incident.status.value == "detected"


def test_score_and_maybe_flag_no_incident_for_normal(db_session: Session) -> None:
    """A normal-looking event should not create an incident."""
    _train_alertness_model(db_session)

    event = _make_event(is_attack=False)
    event.is_off_hours = False
    event.is_new_device = False
    event.is_unusual_network = False
    event.is_lateral_movement = False
    event.event_type = "auth_login"
    event.process = "chrome.exe"
    # Pin inside the training distribution's hour range: the generator's base
    # times are midnight-UTC + jitter, so training data lives at hours 0-3 and
    # the Isolation Forest boundary is calibrated to that. datetime.now() made
    # this test time-of-day flaky (an afternoon run scored the event as an
    # anomaly). Hour 1 is the densest training hour, so this exercises the
    # actual intent — a benign, in-distribution event creates no incident.
    event.timestamp = datetime(2026, 6, 2, 1, 30, 0, tzinfo=timezone.utc)

    detection = score_and_maybe_flag(event, db_session)

    assert detection["scored"] is True
    assert detection["detected"] is False
    assert "incident_id" not in detection

    incidents = db_session.exec(select(Incident)).all()
    assert len(incidents) == 0


def test_parse_log_line_json() -> None:
    line = '{"actor": "alice", "host": "WS-001", "event_type": "auth_login"}'
    data = parse_log_line(line)
    assert data is not None
    assert data["actor"] == "alice"
    assert data["host"] == "WS-001"
    assert data["event_type"] == "auth_login"
    assert data["event_id"].startswith("EVT-")


def test_parse_log_line_pipe_delimited() -> None:
    line = (
        "2026-01-01T03:00:00+00:00|eve|WS-001|lateral_move|ssh|"
        "WS-001|JMP-01||1|1|0|0|1|1|1|lateral_movement|attack"
    )
    data = parse_log_line(line)
    assert data is not None
    assert data["actor"] == "eve"
    assert data["is_off_hours"] is True
    assert data["is_lateral_movement"] is True
    assert data["is_attack"] is True
    assert data["attack_family"] == "lateral_movement"


def test_parse_log_line_invalid_returns_none() -> None:
    assert parse_log_line("") is None
    assert parse_log_line("not|enough|fields") is None
    assert parse_log_line("not json") is None


def test_watch_synthetic_generates_events(db_session: Session) -> None:
    """The synthetic watch source produces and scores the requested number of events."""
    _train_alertness_model(db_session)

    console = Console(force_terminal=True, record=True)
    count = run_watch(source="synthetic", interval=0.05, max_events=2, console_override=console)

    assert count >= 2
    recorded = console.export_text()
    assert "[SYNTHETIC]" in recorded


def test_on_incident_event_dispatches_tavily_and_n8n(db_session: Session, monkeypatch) -> None:
    """When Tavily and n8n are configured, detection dispatches Tavily, n8n, and Signal."""
    incident = Incident(
        incident_id="INC-DISPATCH-01",
        title="Lateral movement detected on WS-001",
        status="detected",
        attack_family="lateral_movement",
        severity="high",
        host="WS-001",
        user="eve",
    )
    db_session.add(incident)
    db_session.commit()

    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    monkeypatch.setattr(settings, "n8n_webhook_url", "https://n8n.test/webhook/abc")

    calls: list[tuple[str, str]] = []

    def fake_post(url: str, **kwargs):
        workflow = kwargs.get("json", {}).get("workflow", "")
        calls.append((url, workflow))
        resp = MagicMock()
        if "tavily" in url:
            resp.text = (
                '{"results": [{"title": "Intel", "url": "https://example.com", '
                '"content": "summary", "score": 0.9}]}'
            )
            resp.json.return_value = {
                "results": [
                    {
                        "title": "Intel",
                        "url": "https://example.com",
                        "content": "summary",
                        "score": 0.9,
                    }
                ]
            }
        else:
            resp.text = '{"status": "ok"}'
            resp.json.return_value = {"status": "ok"}
        resp.raise_for_status.return_value = None
        return resp

    monkeypatch.setattr("httpx.post", fake_post)

    result = on_incident_event(incident, IncidentEventType.DETECTED, db_session)

    assert result["dispatched"] == 3
    assert any("api.tavily.com" in u for u, _ in calls)
    n8n_calls = [w for u, w in calls if "n8n.test" in u]
    assert len(n8n_calls) == 2
    assert "anvaya_incident_event" in n8n_calls
    assert "signal" in n8n_calls


def test_on_project_created_dispatches_launchpad_via_n8n(db_session: Session, monkeypatch) -> None:
    """When n8n is configured, creating a project dispatches a Launchpad event."""
    project = Project(
        project_id="PRJ-TEST-001",
        name="Test Project",
        description="A test project",
        organization_id="ORG-TEST",
        created_by="user-001",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    monkeypatch.setattr(settings, "n8n_webhook_url", "https://n8n.test/webhook/launchpad")

    calls: list[tuple[str, str]] = []

    def fake_post(url: str, **kwargs):
        workflow = kwargs.get("json", {}).get("workflow", "")
        calls.append((url, workflow))
        resp = MagicMock()
        resp.text = '{"status": "ok"}'
        resp.json.return_value = {"status": "ok"}
        resp.raise_for_status.return_value = None
        return resp

    monkeypatch.setattr("httpx.post", fake_post)

    result = on_project_created(project, db_session)

    assert result is not None
    assert result["workflow"] == "launchpad_account"
    assert len(calls) == 1
    assert calls[0][0] == "https://n8n.test/webhook/launchpad"
    assert calls[0][1] == "launchpad_account"
