"""Project, dataset, generation, and organization-scoped artifact API."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections import Counter
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlmodel import Session, delete, select

from anvaya.agent.events import event_store
from anvaya.auth import get_auth_context
from anvaya.config import settings
from anvaya.dataset_profile import build_dataset_profile
from anvaya.db import get_session
from anvaya.generation import ArtifactGenerator, delete_project_artifacts
from anvaya.generations.builder import build_artifact, build_artifacts
from anvaya.live.dispatch import on_project_created
from anvaya.logging import get_logger
from anvaya.models.artifact_build import GenerationArtifact
from anvaya.models.project import (
    ARTIFACT_TYPES,
    Dataset,
    DatasetStatus,
    Generation,
    GenerationStatus,
    Project,
    ProjectArtifact,
    ProjectArtifactPayload,
)

router = APIRouter()
logger = get_logger("anvaya.routers.projects")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8].upper()}"


def _user_orgs(session: Session, user_id: str) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT o."id", o."name", o."slug", o."logo", o."metadata", m."role"
            FROM "organization" o
            JOIN "member" m ON m."organizationId" = o."id"
            WHERE m."userId" = :user_id
            ORDER BY m."createdAt" DESC
            """
        ).bindparams(user_id=user_id)
    ).all()
    return [
        {
            "id": r[0],
            "name": r[1],
            "slug": r[2],
            "logo": r[3],
            "metadata": r[4],
            "role": r[5],
        }
        for r in rows
    ]


def _require_project(session: Session, project_id: str, organization_id: str) -> Project:
    stmt = select(Project).where(
        Project.project_id == project_id,
        Project.organization_id == organization_id,
    )
    project = session.exec(stmt).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_dataset(
    session: Session, dataset_id: str, project_id: str, organization_id: str
) -> Dataset:
    stmt = select(Dataset).where(
        Dataset.dataset_id == dataset_id,
        Dataset.project_id == project_id,
        Dataset.organization_id == organization_id,
    )
    dataset = session.exec(stmt).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


def _url_scheme_safe(url: str) -> bool:
    return bool(re.match(r"^https?://", url, re.IGNORECASE))


@router.get("/organizations")
def list_organizations(
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    return {"items": _user_orgs(db_session, auth.user_id)}


@router.get("/organizations/{org_id}")
def get_organization(
    org_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    row = db_session.execute(
        text(
            """
            SELECT o."id", o."name", o."slug", o."logo", o."metadata", m."role"
            FROM "organization" o
            JOIN "member" m ON m."organizationId" = o."id"
            WHERE o."id" = :org_id AND m."userId" = :user_id
            """
        ).bindparams(org_id=org_id, user_id=auth.user_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {
        "id": row[0],
        "name": row[1],
        "slug": row[2],
        "logo": row[3],
        "metadata": row[4],
        "role": row[5],
    }


@router.put("/organizations/{org_id}")
def update_organization(
    org_id: str,
    data: dict[str, Any],
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    member_row = db_session.execute(
        text(
            'SELECT "role" FROM "member" WHERE "organizationId" = :org_id AND "userId" = :user_id'
        ).bindparams(org_id=org_id, user_id=auth.user_id)
    ).first()
    if not member_row or member_row[0] not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    updates: dict[str, Any] = {}
    if "name" in data:
        updates["name"] = data["name"]
    if "slug" in data:
        updates["slug"] = data["slug"]
    if "logo" in data:
        logo = data["logo"]
        if logo and not _url_scheme_safe(logo):
            raise HTTPException(status_code=400, detail="Logo URL must use http:// or https://")
        updates["logo"] = logo
    if "metadata" in data:
        updates["metadata"] = json.dumps(data["metadata"])

    if not updates:
        return get_organization(org_id, request, db_session)

    set_clause = ", ".join([f'"{k}" = :{k}' for k in updates])
    updates["org_id"] = org_id
    db_session.execute(
        text(f'UPDATE "organization" SET {set_clause} WHERE "id" = :org_id').bindparams(**updates)
    )
    db_session.commit()
    return get_organization(org_id, request, db_session)


@router.get("/projects")
def list_projects(
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    org = auth.organization
    if not org:
        return {"items": []}
    projects = db_session.exec(
        select(Project)
        .where(Project.organization_id == org["id"])
        .order_by(Project.created_at.desc())
    ).all()
    return {"items": [p.model_dump() for p in projects]}


@router.post("/projects")
def create_project(
    data: dict[str, Any],
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")
    project = Project(
        project_id=_new_id("PRJ"),
        organization_id=org["id"],
        name=name,
        description=data.get("description", ""),
        created_by=auth.user_id,
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    on_project_created(project, db_session)

    return project.model_dump()


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    project = _require_project(db_session, project_id, org["id"])
    data = project.model_dump()
    data["datasets"] = [
        d.model_dump()
        for d in db_session.exec(select(Dataset).where(Dataset.project_id == project_id)).all()
    ]
    data["artifact_counts"] = _artifact_counts(db_session, project_id)
    return data


def _artifact_counts(session: Session, project_id: str) -> dict[str, int]:
    rows = session.exec(
        select(ProjectArtifact.artifact_type, ProjectArtifact.artifact_id).where(
            ProjectArtifact.project_id == project_id
        )
    ).all()
    counts: Counter[str] = Counter()
    for artifact_type, _ in rows:
        counts[artifact_type] += 1
    return {t: counts.get(t, 0) for t in ARTIFACT_TYPES}


@router.post("/projects/{project_id}/datasets")
def create_dataset(
    project_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
    file: UploadFile = File(...),
) -> dict:
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])

    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    fmt = _detect_format(filename)
    if fmt not in ("csv", "json", "jsonl", "parquet"):
        raise HTTPException(status_code=400, detail="Unsupported file format")

    contents = file.file.read()
    size = len(contents)
    if size > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")

    checksum = hashlib.sha256(contents).hexdigest()
    dataset_id = _new_id("DS")
    os.makedirs(settings.datasets_dir, exist_ok=True)
    dest_path = settings.datasets_dir / f"{dataset_id}{ext}"
    with open(dest_path, "wb") as f:
        f.write(contents)

    dataset = Dataset(
        dataset_id=dataset_id,
        organization_id=org["id"],
        project_id=project_id,
        created_by=auth.user_id,
        filename=filename,
        format=fmt,
        size=size,
        checksum=checksum,
        source=str(dest_path),
        status=DatasetStatus.INGESTING,
    )
    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)

    try:
        profile = _profile_dataset(dest_path, fmt)
        dataset.profile_json = json.dumps(profile)
        dataset.status = DatasetStatus.READY
    except Exception as exc:
        logger.error("dataset_ingest_failed", dataset_id=dataset_id, error=str(exc))
        dataset.status = DatasetStatus.ERROR

    db_session.add(dataset)
    db_session.commit()
    db_session.refresh(dataset)
    return dataset.model_dump()


def _detect_format(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    mapping = {
        ".csv": "csv",
        ".json": "json",
        ".jsonl": "jsonl",
        ".parquet": "parquet",
    }
    return mapping.get(ext, "")


def _profile_dataset(path: os.PathLike, fmt: str, dataset_id: str = "") -> dict[str, Any]:
    if fmt == "csv":
        df = pd.read_csv(path)
    elif fmt == "json":
        df = pd.read_json(path)
    elif fmt == "jsonl":
        df = pd.read_json(path, lines=True)
    elif fmt == "parquet":
        df = pd.read_parquet(path)
    else:
        raise ValueError("Unsupported format")

    profile = build_dataset_profile(df, dataset_id or "DS-?")
    return profile.to_dict()


@router.get("/projects/{project_id}/datasets")
def list_datasets(
    project_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    datasets = db_session.exec(
        select(Dataset).where(Dataset.project_id == project_id).order_by(Dataset.created_at.desc())
    ).all()
    return {"items": [d.model_dump() for d in datasets]}


@router.get("/projects/{project_id}/datasets/{dataset_id}")
def get_dataset(
    project_id: str,
    dataset_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    dataset = _require_dataset(db_session, dataset_id, project_id, org["id"])
    return dataset.model_dump()


@router.post("/projects/{project_id}/generate")
def create_generation(
    project_id: str,
    data: dict[str, Any],
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])

    requested = data.get("requested_artifacts") or []
    if not isinstance(requested, list):
        raise HTTPException(status_code=400, detail="requested_artifacts must be a list")

    invalid = [r for r in requested if r not in ARTIFACT_TYPES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown artifact types: {', '.join(invalid)}")

    dataset_id = data.get("dataset_id")
    if dataset_id:
        _require_dataset(db_session, dataset_id, project_id, org["id"])

    generation = Generation(
        generation_id=_new_id("GEN"),
        organization_id=org["id"],
        project_id=project_id,
        dataset_id=dataset_id or "",
        user_id=auth.user_id,
        requested_artifacts_json=json.dumps(requested),
        created_artifacts_json="{}",
        status=GenerationStatus.PENDING,
    )
    db_session.add(generation)
    db_session.commit()
    db_session.refresh(generation)

    _run_generation(db_session, generation, requested)
    db_session.refresh(generation)

    return jsonable_encoder(generation)


def _run_generation(session: Session, generation: Generation, requested: list[str]) -> None:
    """Generate requested artifacts from the project's dataset."""
    project = session.exec(
        select(Project).where(Project.project_id == generation.project_id)
    ).first()
    if not project:
        generation.status = GenerationStatus.FAILED
        generation.error_message = "Project not found"
        session.add(generation)
        session.commit()
        return

    dataset = None
    if generation.dataset_id:
        dataset = session.exec(
            select(Dataset).where(Dataset.dataset_id == generation.dataset_id)
        ).first()

    generation.status = GenerationStatus.RUNNING
    session.add(generation)
    session.commit()

    try:
        generator = ArtifactGenerator(session, project, generation, dataset)
        created = generator.generate_all(requested)
        generation.status = GenerationStatus.COMPLETED
        generation.created_artifacts_json = json.dumps(created)
    except Exception as exc:
        generation.status = GenerationStatus.FAILED
        generation.error_message = str(exc)

    session.add(generation)
    session.commit()


def _target_from_prompt(prompt: str) -> str | None:
    prompt = prompt.lower()
    for artifact_type in ARTIFACT_TYPES:
        if artifact_type in prompt:
            return artifact_type
    aliases = {
        "orbit": "orbits",
        "orbits": "orbits",
        "reach": "reach",
        "arbor": "arbor",
        "segments": "segments",
        "trophy": "trophy_wall",
        "arena": "arena",
        "ecosystem": "ecosystem",
        "incident": "incidents",
        "impact": "impacts",
        "replay": "replay",
        "ledger": "ledger",
    }
    for alias, target in aliases.items():
        if alias in prompt:
            return target
    return None


@router.post("/projects/{project_id}/build")
def create_build_session(
    project_id: str,
    data: dict[str, Any],
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    """Create a product-build session and start the artifact-by-artifact builder.

    Accepts either a single ``target`` (unchanged behavior) or a ``targets``
    list / ``requested_artifacts`` list. With multiple targets, ONE execution is
    minted and the builders run sequentially under it so the agent panel shows
    one continuous narration stream across all requested artifacts.
    """
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])

    prompt = data.get("prompt", "")
    targets: list[str] = []
    raw_targets = data.get("targets") or data.get("requested_artifacts") or []
    if isinstance(raw_targets, list):
        targets = [t for t in raw_targets if isinstance(t, str)]
    if not targets:
        target = data.get("target") or _target_from_prompt(prompt)
        if not target:
            raise HTTPException(
                status_code=400, detail="Could not determine target artifact from prompt"
            )
        targets = [target]

    invalid = [t for t in targets if t not in ARTIFACT_TYPES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown artifact types: {', '.join(invalid)}")

    dataset_id = data.get("dataset_id")
    if dataset_id:
        _require_dataset(db_session, dataset_id, project_id, org["id"])

    objective = prompt or f"Build {targets[0]}" if len(targets) == 1 else prompt or f"Build {', '.join(targets)}"
    execution_id = event_store.create_execution(
        db_session,
        objective=objective,
        incident_id=project_id,
        provider="artifact-builder",
    )

    generation_ids: list[str] = []
    for target in targets:
        generation = Generation(
            generation_id=_new_id("GEN"),
            organization_id=org["id"],
            project_id=project_id,
            dataset_id=dataset_id or "",
            user_id=auth.user_id,
            prompt=prompt,
            target_artifact_type=target,
            requested_artifacts_json=json.dumps([target]),
            status=GenerationStatus.PENDING,
        )
        db_session.add(generation)
        db_session.commit()
        db_session.refresh(generation)
        generation_ids.append(generation.generation_id)

    if len(generation_ids) == 1:
        thread = threading.Thread(
            target=build_artifact,
            args=(generation_ids[0], execution_id, project_id),
            daemon=True,
        )
    else:
        thread = threading.Thread(
            target=build_artifacts,
            args=(generation_ids, execution_id, project_id),
            daemon=True,
        )
    thread.start()

    return {
        "generation_id": generation_ids[0],
        "generation_ids": generation_ids,
        "execution_id": execution_id,
        "target": targets[0],
        "targets": targets,
        "status": GenerationStatus.PENDING,
    }


@router.get("/projects/{project_id}/generations/{generation_id}/artifacts")
def list_generation_artifacts(
    project_id: str,
    generation_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    """Return the artifact timeline for a build session."""
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    rows = db_session.exec(
        select(GenerationArtifact)
        .where(
            GenerationArtifact.project_id == project_id,
            GenerationArtifact.generation_id == generation_id,
        )
        .order_by(GenerationArtifact.index)
    ).all()
    return {
        "items": [
            {
                "id": r.artifact_type,
                "index": r.index,
                "name": r.name,
                "type": r.artifact_type,
                "status": r.status,
                "purpose": r.purpose,
                "dependencies": json.loads(r.dependencies_json or "[]"),
                "payload": json.loads(r.payload_json or "{}"),
                "error": r.error,
                "metadata": json.loads(r.metadata_json or "{}"),
            }
            for r in rows
        ],
    }


@router.get("/projects/{project_id}/generations")
def list_generations(
    project_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    generations = db_session.exec(
        select(Generation)
        .where(Generation.project_id == project_id)
        .order_by(Generation.created_at.desc())
    ).all()
    return {"items": [g.model_dump() for g in generations]}


@router.get("/projects/{project_id}/generations/{generation_id}")
def get_generation(
    project_id: str,
    generation_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    generation = db_session.exec(
        select(Generation).where(
            Generation.generation_id == generation_id,
            Generation.project_id == project_id,
            Generation.organization_id == org["id"],
        )
    ).first()
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
    return generation.model_dump()


@router.get("/projects/{project_id}/artifact-counts")
def list_artifact_counts(
    project_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    """List all artifact types with counts for a project."""
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    return {"artifact_types": ARTIFACT_TYPES, "counts": _artifact_counts(db_session, project_id)}


@router.get("/projects/{project_id}/{artifact_type}")
def list_project_artifacts(
    project_id: str,
    artifact_type: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown artifact type")
    rows = db_session.exec(
        select(ProjectArtifact)
        .where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.artifact_type == artifact_type,
        )
        .order_by(ProjectArtifact.created_at.desc())
    ).all()
    payloads = {
        p.artifact_id: p.payload_json
        for p in db_session.exec(
            select(ProjectArtifactPayload).where(
                ProjectArtifactPayload.project_id == project_id,
                ProjectArtifactPayload.artifact_type == artifact_type,
            )
        ).all()
    }
    items = []
    for r in rows:
        d = r.model_dump()
        try:
            d["payload"] = json.loads(payloads.get(r.artifact_id, "{}"))
        except json.JSONDecodeError:
            d["payload"] = {}
        items.append(d)
    return {"items": items}


@router.get("/projects/{project_id}/orbits")
def get_project_orbits(
    project_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    """Return the latest generated orbit artifact payload for a project."""
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    row = db_session.exec(
        select(ProjectArtifact)
        .where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.artifact_type == "orbits",
        )
        .order_by(ProjectArtifact.created_at.desc())
    ).first()
    if not row:
        return {"payload": None}
    payload = db_session.exec(
        select(ProjectArtifactPayload).where(
            ProjectArtifactPayload.artifact_id == row.artifact_id,
            ProjectArtifactPayload.artifact_type == "orbits",
        )
    ).first()
    if not payload:
        return {"payload": None}
    try:
        return {"payload": json.loads(payload.payload_json)}
    except json.JSONDecodeError:
        return {"payload": None}


@router.get("/projects/{project_id}/{artifact_type}/latest")
def get_latest_project_artifact(
    project_id: str,
    artifact_type: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    """Return the latest payload for an artifact type (or null)."""
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown artifact type")
    row = db_session.exec(
        select(ProjectArtifact)
        .where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.artifact_type == artifact_type,
        )
        .order_by(ProjectArtifact.created_at.desc())
    ).first()
    if not row:
        return {"payload": None}
    payload = db_session.exec(
        select(ProjectArtifactPayload).where(
            ProjectArtifactPayload.artifact_id == row.artifact_id,
            ProjectArtifactPayload.artifact_type == artifact_type,
        )
    ).first()
    if not payload:
        return {"payload": None}
    try:
        return {"payload": json.loads(payload.payload_json)}
    except json.JSONDecodeError:
        return {"payload": None}


@router.get("/projects/{project_id}/{artifact_type}/{artifact_id}")
def get_project_artifact(
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    """Get a single project artifact payload."""
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown artifact type")
    row = db_session.exec(
        select(ProjectArtifact).where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.artifact_type == artifact_type,
            ProjectArtifact.artifact_id == artifact_id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    payload = db_session.exec(
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


@router.delete("/projects/{project_id}/{artifact_type}/{artifact_id}")
def delete_project_artifact(
    project_id: str,
    artifact_type: str,
    artifact_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    """Delete a single project artifact."""
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown artifact type")

    row = db_session.exec(
        select(ProjectArtifact).where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.artifact_type == artifact_type,
            ProjectArtifact.artifact_id == artifact_id,
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")

    pap = ProjectArtifactPayload.__table__
    db_session.delete(row)
    db_session.exec(
        delete(ProjectArtifactPayload).where(
            pap.c.project_id == project_id,
            pap.c.artifact_type == artifact_type,
            pap.c.artifact_id == artifact_id,
        )
    )
    db_session.commit()
    return {"deleted": True, "artifact_id": artifact_id, "artifact_type": artifact_type}


@router.delete("/projects/{project_id}/{artifact_type}")
def delete_project_artifact_type(
    project_id: str,
    artifact_type: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    """Delete all artifacts of a type for a project."""
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    _require_project(db_session, project_id, org["id"])
    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown artifact type")

    count = delete_project_artifacts(
        db_session, project_id, [artifact_type], delete_generations=False
    )
    return {"deleted": count, "artifact_type": artifact_type}


@router.post("/projects/{project_id}/{artifact_type}/regenerate")
def regenerate_artifact_type(
    project_id: str,
    artifact_type: str,
    request: Request,
    db_session: Session = Depends(get_session),
    dataset_id: str | None = None,
) -> dict:
    """Regenerate a single artifact type for a project from the latest/specified dataset."""
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    project = _require_project(db_session, project_id, org["id"])

    if artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(status_code=400, detail="Unknown artifact type")

    dataset = None
    if dataset_id:
        dataset = _require_dataset(db_session, dataset_id, project_id, org["id"])
    else:
        dataset = db_session.exec(
            select(Dataset)
            .where(Dataset.project_id == project_id, Dataset.status == "ready")
            .order_by(Dataset.created_at.desc())
        ).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="No usable dataset found")

    delete_project_artifacts(db_session, project_id, [artifact_type], delete_generations=False)

    generation = Generation(
        generation_id=f"GEN-{uuid4().hex[:8].upper()}",
        organization_id=org["id"],
        project_id=project_id,
        dataset_id=dataset.dataset_id,
        user_id=auth.user_id,
        requested_artifacts_json=json.dumps([artifact_type]),
        created_artifacts_json="{}",
        status="pending",
    )
    db_session.add(generation)
    db_session.commit()
    db_session.refresh(generation)

    try:
        generator = ArtifactGenerator(db_session, project, generation, dataset)
        created = generator.generate_all([artifact_type])
        generation.status = "completed"
    except Exception as exc:
        generation.status = "failed"
        generation.error_message = str(exc)
        db_session.add(generation)
        db_session.commit()
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {exc}")

    db_session.add(generation)
    db_session.commit()
    return {
        "regenerated": True,
        "artifact_type": artifact_type,
        "generation_id": generation.generation_id,
        "created": created,
    }


@router.get("/projects/{project_id}/datasets/{dataset_id}/profile")
def get_dataset_profile(
    project_id: str,
    dataset_id: str,
    request: Request,
    db_session: Session = Depends(get_session),
) -> dict:
    """Return the stored schema profile for a dataset."""
    auth = get_auth_context(request, db_session)
    org = auth.require_org()
    dataset = _require_dataset(db_session, dataset_id, project_id, org["id"])
    try:
        return json.loads(dataset.profile_json or "{}")
    except json.JSONDecodeError:
        return {}
