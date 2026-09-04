"""SentinelBacktracker API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from anvaya.db import get_session
from anvaya.sentinel import SentinelEngine

router = APIRouter()


@router.post("/sentinel/backtrack/{incident_id}")
def backtrack(incident_id: str, session: Session = Depends(get_session)) -> dict:
    engine = SentinelEngine(session)
    result = engine.backtrack(incident_id)
    return result


@router.post("/sentinel/propose-rule/{incident_id}")
def propose_rule(incident_id: str, session: Session = Depends(get_session)) -> dict:
    engine = SentinelEngine(session)
    result = engine.propose_rule(incident_id)
    return result


@router.post("/sentinel/validate-rule/{incident_id}")
def validate_rule(incident_id: str, session: Session = Depends(get_session)) -> dict:
    engine = SentinelEngine(session)
    result = engine.validate_rule(incident_id)
    return result


@router.post("/sentinel/replay/{incident_id}")
def replay_attack(incident_id: str, session: Session = Depends(get_session)) -> dict:
    engine = SentinelEngine(session)
    result = engine.replay_attack(incident_id)
    return result


@router.post("/sentinel/full-cycle/{incident_id}")
def full_cycle(incident_id: str, session: Session = Depends(get_session)) -> dict:
    engine = SentinelEngine(session)
    result = engine.run_full_cycle(incident_id)
    return result
