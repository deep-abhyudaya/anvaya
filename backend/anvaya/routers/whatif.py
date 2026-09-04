"""What-If API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from anvaya.db import get_session
from anvaya.whatif.engine import WhatIfEngine

router = APIRouter()


@router.post("/whatif/analyze/{incident_id}")
def analyze(
    incident_id: str, changes: dict | None = None, session: Session = Depends(get_session)
) -> dict:
    engine = WhatIfEngine(session)
    result = engine.analyze(incident_id, changes or {})
    return result


@router.get("/whatif/{incident_id}")
def get_analysis(incident_id: str, session: Session = Depends(get_session)) -> dict:
    engine = WhatIfEngine(session)
    result = engine.get_result(incident_id)
    return result
