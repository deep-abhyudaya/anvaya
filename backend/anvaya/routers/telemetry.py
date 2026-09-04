"""Telemetry API router."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.live import score_and_maybe_flag
from anvaya.models.telemetry import TelemetryEvent

router = APIRouter()


@router.get("/telemetry")
def list_telemetry(
    incident_id: Optional[str] = None,
    scenario_id: Optional[str] = None,
    is_attack: Optional[bool] = None,
    limit: int = Query(default=100, le=500),
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict:
    stmt = select(TelemetryEvent)
    if incident_id:
        stmt = stmt.where(TelemetryEvent.incident_id == incident_id)
    if scenario_id:
        stmt = stmt.where(TelemetryEvent.scenario_id == scenario_id)
    if is_attack is not None:
        stmt = stmt.where(TelemetryEvent.is_attack == is_attack)
    stmt = stmt.order_by(TelemetryEvent.timestamp.desc()).offset(offset).limit(limit)
    events = session.exec(stmt).all()
    return {"items": [e.model_dump() for e in events], "limit": limit, "offset": offset}


@router.get("/telemetry/{event_id}")
def get_telemetry_event(event_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(TelemetryEvent).where(TelemetryEvent.event_id == event_id)
    event = session.exec(stmt).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event.model_dump()


@router.post("/telemetry")
def create_telemetry(data: dict, session: Session = Depends(get_session)) -> dict:
    event = TelemetryEvent(
        event_id=data.get("event_id", f"EVT-{uuid4().hex[:8].upper()}"),
        incident_id=data.get("incident_id"),
        scenario_id=data.get("scenario_id", ""),
        event_type=data.get("event_type", "auth_login"),
        actor=data.get("actor", ""),
        host=data.get("host", ""),
        process=data.get("process", ""),
        source=data.get("source", ""),
        destination=data.get("destination", ""),
        command=data.get("command", ""),
        is_off_hours=data.get("is_off_hours", False),
        is_new_device=data.get("is_new_device", False),
        is_privilege_escalation=data.get("is_privilege_escalation", False),
        is_anomalous_process=data.get("is_anomalous_process", False),
        is_unusual_network=data.get("is_unusual_network", False),
        is_lateral_movement=data.get("is_lateral_movement", False),
        is_attack=data.get("is_attack", False),
        attack_family=data.get("attack_family", ""),
        ground_truth_label=data.get("ground_truth_label", "normal"),
        seed=data.get("seed", 0),
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    detection = score_and_maybe_flag(event, session)
    return {"event": event.model_dump(), "detection": detection}
