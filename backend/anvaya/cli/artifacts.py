"""Artifact command helpers for the ANVAYA interactive CLI."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from anvaya.cli.selectors import confirm_deletion
from anvaya.models.project import (
    ARTIFACT_TYPES,
    Dataset,
    Generation,
    GenerationStatus,
    Project,
    ProjectArtifact,
    ProjectArtifactPayload,
)

ARTIFACT_NAME_MAP = {
    "orbit": "orbits",
    "orbits": "orbits",
    "ecosystem": "ecosystem",
    "replay": "replay",
    "reach": "reach",
    "reachability": "reach",
    "segments": "segments",
    "arena": "arena",
    "arbor": "arbor",
    "impact": "impacts",
    "impacts": "impacts",
    "trophy": "trophy_wall",
    "trophies": "trophy_wall",
    "trophy_wall": "trophy_wall",
    "ledger": "ledger",
    "incidents": "incidents",
    "all": "all",
}


def normalize_artifact_type(name: str) -> str:
    return ARTIFACT_NAME_MAP.get(name.lower(), name)


def list_artifacts_for_project(session: Session, project_id: str) -> list[dict[str, Any]]:
    rows = session.exec(
        select(ProjectArtifact)
        .where(ProjectArtifact.project_id == project_id)
        .order_by(ProjectArtifact.created_at.desc())
    ).all()
    payloads = {
        p.artifact_id: p.payload_json
        for p in session.exec(
            select(ProjectArtifactPayload).where(ProjectArtifactPayload.project_id == project_id)
        ).all()
    }
    items: list[dict[str, Any]] = []
    for r in rows:
        d = r.model_dump()
        try:
            d["payload"] = json.loads(payloads.get(r.artifact_id, "{}"))
        except json.JSONDecodeError:
            d["payload"] = {}
        items.append(d)
    return items


def list_artifact_counts(session: Session, project_id: str) -> dict[str, int]:
    rows = session.exec(
        select(ProjectArtifact.artifact_type).where(ProjectArtifact.project_id == project_id)
    ).all()
    counts: dict[str, int] = {}
    for atype in rows:
        counts[atype] = counts.get(atype, 0) + 1
    for t in ARTIFACT_TYPES:
        counts.setdefault(t, 0)
    return counts


def get_latest_artifact(
    session: Session, project_id: str, artifact_type: str
) -> dict[str, Any] | None:
    row = session.exec(
        select(ProjectArtifact)
        .where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.artifact_type == artifact_type,
        )
        .order_by(ProjectArtifact.created_at.desc())
    ).first()
    if not row:
        return None
    payload = session.exec(
        select(ProjectArtifactPayload).where(
            ProjectArtifactPayload.artifact_id == row.artifact_id,
            ProjectArtifactPayload.artifact_type == artifact_type,
            ProjectArtifactPayload.project_id == project_id,
        )
    ).first()
    data = row.model_dump()
    try:
        data["payload"] = json.loads(payload.payload_json) if payload else {}
    except json.JSONDecodeError:
        data["payload"] = {}
    return data


def get_artifact_by_id(
    session: Session, project_id: str, artifact_type: str, artifact_id: str
) -> dict[str, Any] | None:
    row = session.exec(
        select(ProjectArtifact).where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.artifact_type == artifact_type,
            ProjectArtifact.artifact_id == artifact_id,
        )
    ).first()
    if not row:
        return None
    payload = session.exec(
        select(ProjectArtifactPayload).where(
            ProjectArtifactPayload.artifact_id == artifact_id,
            ProjectArtifactPayload.artifact_type == artifact_type,
            ProjectArtifactPayload.project_id == project_id,
        )
    ).first()
    data = row.model_dump()
    try:
        data["payload"] = json.loads(payload.payload_json) if payload else {}
    except json.JSONDecodeError:
        data["payload"] = {}
    return data


def delete_artifact(
    session: Session,
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    *,
    confirm: bool = True,
) -> bool:
    row = session.exec(
        select(ProjectArtifact).where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.artifact_type == artifact_type,
            ProjectArtifact.artifact_id == artifact_id,
        )
    ).first()
    if not row:
        return False
    if confirm and not confirm_deletion(f"{artifact_id} ({artifact_type})"):
        return False

    payload = session.exec(
        select(ProjectArtifactPayload).where(
            ProjectArtifactPayload.artifact_id == artifact_id,
            ProjectArtifactPayload.artifact_type == artifact_type,
            ProjectArtifactPayload.project_id == project_id,
        )
    ).first()
    if payload:
        session.delete(payload)
    session.delete(row)
    session.commit()
    return True


def delete_artifacts_of_type(session: Session, project_id: str, artifact_type: str) -> int:
    if not confirm_deletion(f"all {artifact_type} artifacts"):
        return 0
    rows = session.exec(
        select(ProjectArtifact).where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.artifact_type == artifact_type,
        )
    ).all()
    count = 0
    for row in rows:
        payload = session.exec(
            select(ProjectArtifactPayload).where(
                ProjectArtifactPayload.artifact_id == row.artifact_id,
                ProjectArtifactPayload.artifact_type == artifact_type,
                ProjectArtifactPayload.project_id == project_id,
            )
        ).first()
        if payload:
            session.delete(payload)
        session.delete(row)
        count += 1
    session.commit()
    return count


def regenerate_artifact_type(
    session: Session,
    project_id: str,
    artifact_type: str,
    dataset_id: str = "",
) -> dict[str, Any]:
    """Regenerate a single artifact type using the existing generator."""
    from anvaya.generation import ArtifactGenerator, delete_project_artifacts

    project = session.exec(select(Project).where(Project.project_id == project_id)).first()
    if not project:
        return {"success": False, "error": f"Project {project_id} not found"}

    if artifact_type not in ARTIFACT_TYPES:
        return {"success": False, "error": f"Unknown artifact type: {artifact_type}"}

    dataset = None
    if dataset_id:
        dataset = session.exec(
            select(Dataset).where(
                Dataset.dataset_id == dataset_id, Dataset.project_id == project_id
            )
        ).first()
    if not dataset:
        dataset = session.exec(
            select(Dataset)
            .where(Dataset.project_id == project_id, Dataset.status == "ready")
            .order_by(Dataset.created_at.desc())
        ).first()
    if not dataset:
        return {"success": False, "error": "No usable dataset found"}

    delete_project_artifacts(session, project_id, [artifact_type], delete_generations=False)

    generation = Generation(
        generation_id=f"GEN-{__import__('uuid').uuid4().hex[:8].upper()}",
        organization_id=project.organization_id,
        project_id=project_id,
        dataset_id=dataset.dataset_id,
        user_id="cli",
        requested_artifacts_json=json.dumps([artifact_type]),
        created_artifacts_json="{}",
        status=GenerationStatus.PENDING,
    )
    session.add(generation)
    session.commit()
    session.refresh(generation)

    try:
        generator = ArtifactGenerator(session, project, generation, dataset)
        created = generator.generate_all([artifact_type])
        generation.status = GenerationStatus.COMPLETED
    except Exception as exc:
        generation.status = GenerationStatus.FAILED
        generation.error_message = str(exc)
        session.add(generation)
        session.commit()
        return {"success": False, "error": str(exc)}

    session.add(generation)
    session.commit()
    return {
        "success": True,
        "artifact_type": artifact_type,
        "generation_id": generation.generation_id,
        "created": created,
    }


def artifact_type_list() -> list[str]:
    return ["all"] + ARTIFACT_TYPES
