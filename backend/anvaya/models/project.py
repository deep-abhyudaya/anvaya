"""Multi-tenant project, dataset, generation, and project artifact models."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class DatasetStatus(str, Enum):
    INGESTING = "ingesting"
    READY = "ready"
    ERROR = "error"


class GenerationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


ARTIFACT_TYPES = [
    "incidents",
    "arbor",
    "impacts",
    "reach",
    "replay",
    "ecosystem",
    "arena",
    "orbits",
    "segments",
    "trophy_wall",
    "ledger",
]


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(unique=True, index=True, max_length=64)
    organization_id: str = Field(index=True, max_length=64)
    name: str = Field(max_length=256)
    description: str = ""
    created_by: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Dataset(SQLModel, table=True):
    __tablename__ = "datasets"

    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_id: str = Field(unique=True, index=True, max_length=64)
    organization_id: str = Field(index=True, max_length=64)
    project_id: str = Field(index=True, max_length=64, foreign_key="projects.project_id")
    created_by: str = Field(max_length=64)
    filename: str = Field(max_length=256)
    format: str = Field(max_length=32)
    size: int = 0
    checksum: str = Field(default="", max_length=128)
    source: str = ""
    status: str = Field(default=DatasetStatus.INGESTING, max_length=32)
    profile_json: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Generation(SQLModel, table=True):
    __tablename__ = "generations"

    id: Optional[int] = Field(default=None, primary_key=True)
    generation_id: str = Field(unique=True, index=True, max_length=64)
    organization_id: str = Field(index=True, max_length=64)
    project_id: str = Field(index=True, max_length=64, foreign_key="projects.project_id")
    dataset_id: str = Field(default="", max_length=64, foreign_key="datasets.dataset_id")
    user_id: str = Field(max_length=64)
    prompt: str = ""
    target_artifact_type: str = ""
    requested_artifacts_json: str = ""
    created_artifacts_json: str = ""
    status: str = Field(default=GenerationStatus.PENDING, max_length=32)
    current_artifact_index: int = 0
    total_artifacts: int = 0
    error_message: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectArtifact(SQLModel, table=True):
    __tablename__ = "project_artifacts"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(index=True, max_length=64)
    dataset_id: str = Field(index=True, max_length=64)
    generation_id: str = Field(index=True, max_length=64)
    artifact_type: str = Field(index=True, max_length=64)
    artifact_id: str = Field(index=True, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectArtifactPayload(SQLModel, table=True):
    __tablename__ = "project_artifact_payloads"

    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: str = Field(index=True, max_length=64)
    dataset_id: str = Field(index=True, max_length=64)
    generation_id: str = Field(index=True, max_length=64)
    artifact_type: str = Field(index=True, max_length=64)
    artifact_id: str = Field(index=True, max_length=64)
    payload_json: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
