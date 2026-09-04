"""Rules API router."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.models.enums import RuleStatus
from anvaya.models.rule import DetectionRule

router = APIRouter()


@router.get("/rules")
def list_rules(
    status: Optional[RuleStatus] = None,
    incident_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
) -> dict:
    stmt = select(DetectionRule)
    if status:
        stmt = stmt.where(DetectionRule.status == status)
    if incident_id:
        stmt = stmt.where(DetectionRule.incident_id == incident_id)
    stmt = stmt.order_by(DetectionRule.created_at.desc()).limit(limit)
    rules = session.exec(stmt).all()
    return {"items": [r.model_dump() for r in rules]}


@router.get("/rules/{rule_id}")
def get_rule(rule_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(DetectionRule).where(DetectionRule.rule_id == rule_id)
    rule = session.exec(stmt).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule.model_dump()


@router.post("/rules")
def create_rule(data: dict, session: Session = Depends(get_session)) -> dict:
    rule = DetectionRule(
        rule_id=data.get("rule_id", f"RL-{uuid4().hex[:8].upper()}"),
        name=data.get("name", "Untitled Rule"),
        description=data.get("description", ""),
        conditions_json=data.get("conditions_json", ""),
        attack_family=data.get("attack_family", ""),
        scenario_id=data.get("scenario_id", ""),
        incident_id=data.get("incident_id", ""),
        status=RuleStatus(data.get("status", "draft")),
        proposed_by=data.get("proposed_by", "system"),
        parent_rule_id=data.get("parent_rule_id"),
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule.model_dump()
