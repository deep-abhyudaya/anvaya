"""Demo orchestration API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from anvaya.db import get_session
from anvaya.demo.orchestrator import DemoOrchestrator

router = APIRouter()


@router.post("/demo/run")
def run_demo(session: Session = Depends(get_session)) -> dict:
    orchestrator = DemoOrchestrator(session)
    result = orchestrator.run_full_demo()
    return result


@router.get("/demo/status")
def demo_status(session: Session = Depends(get_session)) -> dict:
    orchestrator = DemoOrchestrator(session)
    return orchestrator.get_status()
