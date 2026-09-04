"""Incidents API router."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.models.graph import BlastRadiusResult
from anvaya.models.incident import Incident, IncidentStatus, SelfCorrectionStatus

router = APIRouter()


@router.get("/incidents")
def list_incidents(
    status: Optional[IncidentStatus] = None,
    self_correction: Optional[SelfCorrectionStatus] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict:
    stmt = select(Incident)
    if status:
        stmt = stmt.where(Incident.status == status)
    if self_correction:
        stmt = stmt.where(Incident.self_correction_status == self_correction)
    stmt = stmt.order_by(Incident.created_at.desc()).offset(offset).limit(limit)
    incidents = session.exec(stmt).all()

    total_stmt = select(Incident)
    if status:
        total_stmt = total_stmt.where(Incident.status == status)
    total = len(session.exec(total_stmt).all())

    incident_ids = [inc.incident_id for inc in incidents]
    blast_results = {
        b.incident_id: b
        for b in session.exec(
            select(BlastRadiusResult).where(BlastRadiusResult.incident_id.in_(incident_ids))
        ).all()
    }

    items = []
    for inc in incidents:
        data = inc.model_dump()
        blast = blast_results.get(inc.incident_id)
        data["blastRadius"] = inc.blast_radius_score or (blast.impact_score if blast else 0.0)
        data["hops"] = blast.max_depth if blast else 0
        items.append(data)

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(Incident).where(Incident.incident_id == incident_id)
    incident = session.exec(stmt).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident.model_dump()


@router.post("/incidents")
def create_incident(data: dict, session: Session = Depends(get_session)) -> dict:
    incident = Incident(
        incident_id=data.get("incident_id", f"INC-{uuid4().hex[:8].upper()}"),
        title=data.get("title", "Untitled Incident"),
        description=data.get("description", ""),
        severity=data.get("severity", "medium"),
        attack_family=data.get("attack_family", ""),
        scenario_id=data.get("scenario_id", ""),
        scenario_seed=data.get("scenario_seed", 0),
        host=data.get("host", ""),
        user=data.get("user", ""),
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident.model_dump()


@router.post("/incidents/{incident_id}/transition")
def transition_incident(
    incident_id: str,
    new_status: IncidentStatus,
    session: Session = Depends(get_session),
) -> dict:
    stmt = select(Incident).where(Incident.incident_id == incident_id)
    incident = session.exec(stmt).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    try:
        incident.transition_to(new_status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident.model_dump()


@router.post("/incidents/{incident_id}/self-correction")
def self_correct_incident(
    incident_id: str,
    new_status: SelfCorrectionStatus,
    session: Session = Depends(get_session),
) -> dict:
    stmt = select(Incident).where(Incident.incident_id == incident_id)
    incident = session.exec(stmt).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    try:
        incident.self_correct_to(new_status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident.model_dump()
