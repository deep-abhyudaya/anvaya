"""Audit API router."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.models.audit import AuditRecord, verify_chain
from anvaya.models.counterfactual import CounterfactualAnalysis
from anvaya.models.graph import BlastRadiusResult
from anvaya.models.incident import Incident
from anvaya.models.replay import ReplayRun

router = APIRouter()


@router.get("/audit")
def list_audit(
    incident_id: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    session: Session = Depends(get_session),
) -> dict:
    """List audit records.

    When no incident filter is provided, the ledger page expects the sealed
    incident records, so we default to records with action=incident_sealed.
    """
    stmt = select(AuditRecord)
    if incident_id:
        stmt = stmt.where(AuditRecord.incident_id == incident_id)
    else:
        stmt = stmt.where(AuditRecord.action == "incident_sealed")
    stmt = stmt.order_by(AuditRecord.timestamp.asc()).limit(limit)
    records = session.exec(stmt).all()

    incident_ids = list({r.incident_id for r in records})
    blast_results = {
        b.incident_id: b
        for b in session.exec(
            select(BlastRadiusResult).where(BlastRadiusResult.incident_id.in_(incident_ids))
        ).all()
    }
    replay_rows = session.exec(
        select(ReplayRun).where(ReplayRun.incident_id.in_(incident_ids))
    ).all()
    replays_by_incident: dict[str, list[ReplayRun]] = {}
    for r in replay_rows:
        replays_by_incident.setdefault(r.incident_id, []).append(r)
    counterfactual_counts: dict[str, int] = {}
    for cf in session.exec(
        select(CounterfactualAnalysis).where(CounterfactualAnalysis.incident_id.in_(incident_ids))
    ).all():
        counterfactual_counts[cf.incident_id] = counterfactual_counts.get(cf.incident_id, 0) + 1
    audit_controls: dict[str, set[str]] = {}
    for a in session.exec(
        select(AuditRecord).where(AuditRecord.incident_id.in_(incident_ids))
    ).all():
        if a.control_mapping:
            audit_controls.setdefault(a.incident_id, set()).add(a.control_mapping)
    incidents = {
        i.incident_id: i
        for i in session.exec(select(Incident).where(Incident.incident_id.in_(incident_ids))).all()
    }

    items = []
    for record in records:
        data = record.model_dump()
        inc = incidents.get(record.incident_id)
        blast = blast_results.get(record.incident_id)
        replays = replays_by_incident.get(record.incident_id, [])
        caught = any(r.post_patch_detected for r in replays)

        if inc:
            data["controls_satisfied"] = len(audit_controls.get(record.incident_id, set()))
            data["blast_radius"] = inc.blast_radius_score or (blast.impact_score if blast else 0.0)
            data["engines"] = {
                "sentinel": 1.0 if caught else 0.0,
                "blastscope": inc.blast_radius_score,
                "whatif": inc.whatif_risk_delta,
                "ledger": 1.0 if audit_controls.get(record.incident_id) else 0.0,
            }
        items.append(data)

    return {"items": items}


@router.get("/audit/verify")
def verify_audit_chain(session: Session = Depends(get_session)) -> dict:
    """Verify audit integrity. Each incident has its own hash chain."""
    records = session.exec(select(AuditRecord)).all()
    if not records:
        return {"valid": True, "record_count": 0, "message": "No audit records to verify"}

    by_incident: dict[str, list[AuditRecord]] = {}
    for r in records:
        by_incident.setdefault(r.incident_id, []).append(r)

    details = []
    all_valid = True
    for incident_id, inc_records in by_incident.items():
        inc_records.sort(key=lambda x: x.timestamp)
        valid = verify_chain(inc_records)
        all_valid = all_valid and valid
        details.append(
            {
                "incident_id": incident_id,
                "valid": valid,
                "record_count": len(inc_records),
            }
        )

    return {
        "valid": all_valid,
        "record_count": len(records),
        "incident_count": len(by_incident),
        "details": details,
    }


@router.get("/audit/{record_id}")
def get_audit_record(record_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(AuditRecord).where(AuditRecord.record_id == record_id)
    record = session.exec(stmt).first()
    if not record:
        raise HTTPException(status_code=404, detail="Audit record not found")
    return record.model_dump()
