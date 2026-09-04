"""Live scoring and event dispatch for real-time telemetry.

`score_and_maybe_flag` is the shared entry point called by `POST /telemetry`,
the `anvaya watch` CLI, and any other real-time ingest path. It runs the
active Alertness model against a single event and, if anomalous, creates an
Incident and an AuditRecord, then dispatches to downstream integrations via
`on_incident_event`.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from anvaya.live.dispatch import on_incident_event
from anvaya.live.enums import IncidentEventType
from anvaya.logging import get_logger
from anvaya.ml.alertness import AlertnessEngine
from anvaya.models.audit import AuditRecord
from anvaya.models.enums import IncidentStatus
from anvaya.models.incident import Incident
from anvaya.models.telemetry import TelemetryEvent

logger = get_logger("anvaya.live")

_SEVERITY_BY_FAMILY: dict[str, str] = {
    "lateral_movement": "high",
    "privilege_escalation": "high",
    "data_exfiltration": "high",
    "persistence": "medium",
    "credential_abuse": "medium",
    "unusual_network": "medium",
    "suspicious_login": "low",
}


def _severity_for_family(family: str | None) -> str:
    return _SEVERITY_BY_FAMILY.get(family or "", "medium")


def _get_or_create_incident_for_event(
    event: TelemetryEvent,
    session: Session,
) -> Incident:
    """Return the incident linked to this event, creating one if needed."""
    incident: Incident | None = None
    if event.incident_id:
        stmt = select(Incident).where(Incident.incident_id == event.incident_id)
        incident = session.exec(stmt).first()

    if incident is None:
        family = event.attack_family or "unknown"
        incident_id = event.incident_id or f"INC-{uuid4().hex[:8].upper()}"
        title = f"{family.replace('_', ' ').title()} detected on {event.host or 'unknown host'}"
        incident = Incident(
            incident_id=incident_id,
            title=title,
            description=f"Live detection from event {event.event_id}",
            status=IncidentStatus.DETECTED,
            severity=_severity_for_family(family),
            attack_family=family,
            scenario_id=event.scenario_id or "",
            host=event.host or "",
            user=event.actor or "",
        )
        session.add(incident)

    event.incident_id = incident.incident_id
    session.add(event)
    session.commit()
    session.refresh(incident)
    return incident


def _append_detection_audit(
    incident: Incident,
    event: TelemetryEvent,
    session: Session,
    result: dict[str, Any],
) -> AuditRecord:
    """Append a hash-chained audit record for a live detection."""
    last = session.exec(
        select(AuditRecord)
        .where(AuditRecord.incident_id == incident.incident_id)
        .order_by(AuditRecord.timestamp.desc())
    ).first()
    prev_hash = last.record_hash if last else ""

    record = AuditRecord(
        record_id=f"AUD-{uuid4().hex[:8].upper()}",
        incident_id=incident.incident_id,
        actor="system",
        action="incident_detected",
        previous_state="",
        new_state="detected",
        reason=(
            f"Alertness model {result.get('model_id')} scored {result.get('score', 0):.4f} "
            f"and flagged event {event.event_id}"
        ),
        control_mapping="NIST.DETECT.ANOMALY",
        result="success",
        model_version=result.get("model_id", ""),
    )
    record.compute_hash(prev_hash)
    session.add(record)
    session.commit()
    return record


def score_and_maybe_flag(event: TelemetryEvent, session: Session) -> dict[str, Any]:
    """Run live scoring on a single telemetry event and create an incident if flagged.

    This is the only place the live Alertness model should be invoked for
    real-time ingest. It is safe to call with an already-persisted or an
    unpersisted TelemetryEvent.
    """
    if event.id is None:
        session.add(event)
        session.commit()
        session.refresh(event)

    engine = AlertnessEngine(session)
    engine.load_latest()

    if engine.model is None:
        return {
            "scored": False,
            "detected": False,
            "reason": "no alertness model trained",
            "model_id": None,
        }

    try:
        result = engine.predict_single(event)
    except Exception as exc:
        logger.warning("live.scoring_failed", error=str(exc), event_id=event.event_id)
        return {
            "scored": False,
            "detected": False,
            "reason": f"scoring failed: {exc}",
            "model_id": engine.model_id,
        }

    detection = {
        "scored": True,
        "detected": bool(result.get("detected")),
        "score": result.get("score"),
        "model_id": result.get("model_id"),
    }

    if detection["detected"]:
        incident = _get_or_create_incident_for_event(event, session)
        _append_detection_audit(incident, event, session, result)

        on_incident_event(incident, IncidentEventType.DETECTED, session)

        detection["incident_id"] = incident.incident_id
        detection["incident_status"] = incident.status.value

    return detection
