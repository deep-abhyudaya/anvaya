"""Artifact build session and per-artifact state models.

These models power the visible, sequential product-builder experience. A
`Generation` represents a build session; `GenerationArtifact` tracks each
individual artifact inside that session, including its lifecycle state and
partial payload.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class ArtifactStatus(str):
    """Lifecycle states for a single product artifact."""

    QUEUED = "queued"
    THINKING = "thinking"
    CREATING = "creating"
    CREATED = "created"
    CONNECTING = "connecting"
    COMPLETE = "complete"
    FAILED = "failed"
    RETRYING = "retrying"


class GenerationArtifact(SQLModel, table=True):
    """One artifact within a product-generation build session."""

    __tablename__ = "generation_artifacts"

    id: Optional[int] = Field(default=None, primary_key=True)
    generation_id: str = Field(index=True, max_length=64)
    project_id: str = Field(index=True, max_length=64)
    artifact_type: str = Field(index=True, max_length=64)
    index: int = Field(default=0)
    name: str = Field(max_length=128)
    purpose: str = ""
    status: str = Field(default=ArtifactStatus.QUEUED, max_length=32)
    dependencies_json: str = ""
    payload_json: str = ""
    error: str = ""
    metadata_json: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
