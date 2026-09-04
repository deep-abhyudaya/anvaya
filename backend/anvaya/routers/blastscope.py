"""BlastScope API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from anvaya.blastscope import BlastScopeEngine
from anvaya.db import get_session

router = APIRouter()


@router.get("/blastscope/gallery")
def get_gallery(session: Session = Depends(get_session)) -> dict:
    """Get impact gallery of incidents with blast scope results."""
    incidents = [
        {"id": "INC-001", "severity": "high", "family": "lateral_movement", "status": "active"},
        {
            "id": "INC-002",
            "severity": "medium",
            "family": "credential_abuse",
            "status": "simulated",
        },
        {"id": "INC-003", "severity": "low", "family": "data_exfiltration", "status": "active"},
        {"id": "INC-004", "severity": "high", "family": "malware_drop", "status": "sealed"},
    ]

    return {"items": incidents}


@router.post("/blastscope/run/{incident_id}")
def run_blastscope(incident_id: str, session: Session = Depends(get_session)) -> dict:
    engine = BlastScopeEngine(session)
    result = engine.run(incident_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/blastscope/{incident_id}")
def get_blastscope(incident_id: str, session: Session = Depends(get_session)) -> dict:
    engine = BlastScopeEngine(session)
    result = engine.get_result(incident_id)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result
