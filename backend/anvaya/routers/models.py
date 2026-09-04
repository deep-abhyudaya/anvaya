"""Models API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.models.model_version import ModelVersion

router = APIRouter()


@router.get("/models")
def list_models(session: Session = Depends(get_session)) -> dict:
    models = session.exec(select(ModelVersion).order_by(ModelVersion.created_at.desc())).all()
    return {"items": [m.model_dump() for m in models]}


@router.get("/models/{model_id}")
def get_model(model_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(ModelVersion).where(ModelVersion.model_id == model_id)
    model = session.exec(stmt).first()
    return model.model_dump() if model else {}
