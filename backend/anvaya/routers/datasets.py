"""Datasets API router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.models.dataset import DatasetVersion

router = APIRouter()


@router.get("/datasets")
def list_datasets(session: Session = Depends(get_session)) -> dict:
    datasets = session.exec(select(DatasetVersion).order_by(DatasetVersion.created_at.desc())).all()
    return {"items": [d.model_dump() for d in datasets]}


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
    dataset = session.exec(stmt).first()
    return dataset.model_dump() if dataset else {}


@router.post("/datasets/generate")
def generate_dataset(config: dict | None = None, session: Session = Depends(get_session)) -> dict:
    from anvaya.data import DataFactory

    factory = DataFactory(session)
    result = factory.generate(config or {})
    return result
