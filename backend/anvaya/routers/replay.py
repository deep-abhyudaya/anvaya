"""Replay API router."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.models.replay import ReplayRun

router = APIRouter()


@router.get("/replay")
def list_replays(
    incident_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
) -> dict:
    stmt = select(ReplayRun)
    if incident_id:
        stmt = stmt.where(ReplayRun.incident_id == incident_id)
    stmt = stmt.order_by(ReplayRun.started_at.desc()).limit(limit)
    replays = session.exec(stmt).all()
    return {"items": [r.model_dump() for r in replays]}


@router.get("/replay/{replay_id}")
def get_replay(replay_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(ReplayRun).where(ReplayRun.replay_id == replay_id)
    replay = session.exec(stmt).first()
    if not replay:
        raise HTTPException(status_code=404, detail="Replay not found")
    return replay.model_dump()
