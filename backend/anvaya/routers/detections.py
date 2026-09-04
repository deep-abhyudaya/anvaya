"""Detections API router."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.models.detection import DetectionResult, DetectionRun

router = APIRouter()


@router.get("/detections")
def list_detections(
    incident_id: Optional[str] = None,
    run_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
) -> dict:
    stmt = select(DetectionRun)
    if incident_id:
        stmt = stmt.where(DetectionRun.incident_id == incident_id)
    if run_id:
        stmt = stmt.where(DetectionRun.run_id == run_id)
    stmt = stmt.order_by(DetectionRun.started_at.desc()).limit(limit)
    runs = session.exec(stmt).all()
    return {"items": [r.model_dump() for r in runs]}


@router.get("/detections/{run_id}")
def get_detection_run(run_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(DetectionRun).where(DetectionRun.run_id == run_id)
    run = session.exec(stmt).first()
    if not run:
        raise HTTPException(status_code=404, detail="Detection run not found")
    return run.model_dump()


@router.get("/detections/{run_id}/results")
def get_detection_results(run_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(DetectionResult).where(DetectionResult.run_id == run_id)
    results = session.exec(stmt).all()
    return {"items": [r.model_dump() for r in results]}
