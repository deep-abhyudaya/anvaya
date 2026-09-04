"""Streaming/payload verification for the staged ArtifactBuilder.

These tests exercise the shared ``ArtifactBuilder.run()`` path and confirm that:

1. The final saved payload is the incrementally-built cumulative payload (with
   missing structural/cosmetic keys backfilled via ``setdefault``), not a
   wholesale overwrite with the pre-generated ``full_payload``.
2. ``ELEMENT_STREAM_LIMIT`` is large enough to stream every item that the
   server-side payload builders actually emit (currently 50 for
   ``orbits``/``incidents``).
3. The fix works for non-orbits manifests too.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd
import pytest
from sqlmodel import Session, select

import anvaya.agent.executor  # noqa: F401  # ensures anvaya.generations.builder is fully loaded before ArtifactBuilder
from anvaya.config import settings
from anvaya.generation import ArtifactGenerator
from anvaya.generations.builder import ArtifactBuilder
from anvaya.models.execution import Execution, ExecutionEvent
from anvaya.models.project import (
    Dataset,
    Generation,
    Project,
    ProjectArtifactPayload,
)


@pytest.fixture(autouse=True)
def _disable_builder_sleep(monkeypatch):
    """Keep builder tests fast without changing the constant values."""
    monkeypatch.setattr("time.sleep", lambda _seconds: None)


def _big_attack_df(row_count: int = 80, seed: int = 42) -> pd.DataFrame:
    """Return a deterministic DataFrame with many unique source/destination pairs.

    This is large enough to exercise the 50-item server-side caps for
    ``world.orbits`` and ``world.incidents`` without being slow to profile.
    """
    rng = random.Random(seed)
    hosts = [f"10.0.0.{i}" for i in range(1, row_count + 1)]
    srcs: list[str] = []
    dsts: list[str] = []
    for _ in range(row_count):
        src = rng.choice(hosts)
        dst = rng.choice(hosts)
        while dst == src:
            dst = rng.choice(hosts)
        srcs.append(src)
        dsts.append(dst)
    return pd.DataFrame(
        {
            "src_ip": srcs,
            "dst_ip": dsts,
            "severity": ["high"] * row_count,
            "host": [f"H{i % 20}" for i in range(row_count)],
            "user": [f"u{i % 10}" for i in range(row_count)],
            "event_type": ["net"] * row_count,
            "attack_family": ["lateral"] * row_count,
            "label": ["attack"] * row_count,
        }
    )


def _setup_dataset(
    session: Session,
    project: Project,
    dataset_id: str,
    df: pd.DataFrame,
    csv_dir: Path,
) -> Dataset:
    path = csv_dir / f"{dataset_id}.csv"
    df.to_csv(path, index=False)
    dataset = Dataset(
        dataset_id=dataset_id,
        organization_id=project.organization_id,
        project_id=project.project_id,
        created_by="u1",
        filename=path.name,
        format="csv",
        size=path.stat().st_size,
        source=str(path),
        status="ready",
    )
    session.add(dataset)
    session.commit()
    return dataset


def _setup_generation(
    session: Session,
    project: Project,
    dataset: Dataset,
    generation_id: str,
    artifact_type: str,
) -> Generation:
    generation = Generation(
        generation_id=generation_id,
        organization_id=project.organization_id,
        project_id=project.project_id,
        dataset_id=dataset.dataset_id,
        user_id="u1",
        prompt=f"Make {artifact_type.title()}",
        target_artifact_type=artifact_type,
        requested_artifacts_json=json.dumps([artifact_type]),
        created_artifacts_json="{}",
        status="pending",
    )
    session.add(generation)
    session.commit()
    return generation


def _setup_execution(session: Session, execution_id: str) -> Execution:
    execution = Execution(
        execution_id=execution_id,
        objective="test artifact build",
        status="running",
    )
    session.add(execution)
    session.commit()
    return execution


def _run_builder(
    session: Session,
    project: Project,
    dataset: Dataset,
    generation_id: str,
    artifact_type: str,
    execution_id: str,
    monkeypatch=None,
) -> dict[str, object]:
    execution = _setup_execution(session, execution_id)
    generation = _setup_generation(
        session, project, dataset, generation_id, artifact_type
    )

    generator = ArtifactGenerator(session, project, generation, dataset)
    generator.generate_all([artifact_type])

    builder = ArtifactBuilder(session, generation, execution, project)

    if monkeypatch is not None:
        saved_ids: list[int] = []
        original = ArtifactBuilder._save_payload

        def _spy(self, payload):
            saved_ids.append(id(payload))
            return original(self, payload)

        monkeypatch.setattr(ArtifactBuilder, "_save_payload", _spy)

    result = builder.run()
    result["_saved_payload_ids"] = saved_ids if monkeypatch is not None else []
    return result


def _final_payload(session: Session, project_id: str, generation_id: str) -> dict:
    artifact_id = f"{generation_id}-orbits"
    stmt = select(ProjectArtifactPayload).where(
        ProjectArtifactPayload.project_id == project_id,
        ProjectArtifactPayload.generation_id == generation_id,
        ProjectArtifactPayload.artifact_id == artifact_id,
    )
    pap = session.exec(stmt).first()
    assert pap is not None
    return json.loads(pap.payload_json)


def _count_events(session: Session, execution_id: str) -> dict[str, int]:
    stmt = select(ExecutionEvent).where(
        ExecutionEvent.execution_id == execution_id,
    )
    events = session.exec(stmt).all()
    thinking: dict[str, int] = {}
    mounted: dict[str, int] = {}
    for e in events:
        payload = json.loads(e.payload_json or "{}")
        collection = payload.get("collection")
        if e.type == "element.thinking" and collection:
            thinking[collection] = thinking.get(collection, 0) + 1
        elif e.type == "element.mounted" and collection:
            mounted[collection] = mounted.get(collection, 0) + 1
    return {"thinking": thinking, "mounted": mounted}


@pytest.fixture
def test_project() -> Project:
    return Project(
        project_id="PRJ-BUILDER",
        organization_id="ORG-1",
        name="Builder Test Project",
        created_by="u1",
    )


def test_orbits_streams_all_elements_and_preserves_payload(
    db_session: Session, test_project: Project, tmp_path: Path, monkeypatch
):
    """Orbits: every node and orbit up to the 50-item server cap is streamed,
    and the final DB payload contains every required key.
    """
    df = _big_attack_df()
    dataset = _setup_dataset(
        db_session, test_project, "DS-ORBITS-BIG", df, tmp_path
    )
    execution_id = "EXEC-ORBITS-BIG"
    result = _run_builder(
        db_session,
        test_project,
        dataset,
        "GEN-ORBITS-BIG",
        "orbits",
        execution_id,
        monkeypatch=monkeypatch,
    )
    assert result["status"] == "completed"

    saved_ids = result["_saved_payload_ids"]
    assert len(saved_ids) > 1
    assert saved_ids[-1] == saved_ids[0]

    payload = _final_payload(
        db_session, test_project.project_id, "GEN-ORBITS-BIG"
    )
    assert payload["artifact_type"] == "orbits"
    for key in ("top_nodes", "orbits", "node_count", "edge_count", "blast_radius"):
        assert key in payload, f"Missing required key: {key}"
    assert "provenance" in payload, "Missing provenance key (backfill failed)"

    counts = _count_events(db_session, execution_id)
    assert counts["mounted"].get("top_nodes", 0) == len(payload["top_nodes"])
    assert counts["mounted"].get("orbits", 0) == len(payload["orbits"])
    assert counts["thinking"].get("top_nodes", 0) == len(payload["top_nodes"])
    assert counts["thinking"].get("orbits", 0) == len(payload["orbits"])

    mounted_orbit_ids = {
        json.loads(e.payload_json or "{}").get("element_id")
        for e in db_session.exec(
            select(ExecutionEvent).where(
                ExecutionEvent.execution_id == execution_id,
                ExecutionEvent.type == "element.mounted",
            )
        ).all()
        if json.loads(e.payload_json or "{}").get("collection") == "orbits"
    }
    saved_orbit_ids = {str(o.get("orbit_id")) for o in payload["orbits"]}
    assert mounted_orbit_ids == saved_orbit_ids


def test_incidents_streams_all_elements(
    db_session: Session, test_project: Project, tmp_path: Path
):
    """Incidents (non-orbits, long list): every incident streams and the final
    payload is complete.
    """
    df = _big_attack_df()
    dataset = _setup_dataset(
        db_session, test_project, "DS-INCIDENTS-BIG", df, tmp_path
    )
    execution_id = "EXEC-INCIDENTS-BIG"
    result = _run_builder(
        db_session,
        test_project,
        dataset,
        "GEN-INCIDENTS-BIG",
        "incidents",
        execution_id,
    )
    assert result["status"] == "completed"

    stmt = select(ProjectArtifactPayload).where(
        ProjectArtifactPayload.project_id == test_project.project_id,
        ProjectArtifactPayload.generation_id == "GEN-INCIDENTS-BIG",
        ProjectArtifactPayload.artifact_id == "GEN-INCIDENTS-BIG-incidents",
    )
    pap = db_session.exec(stmt).first()
    assert pap is not None
    payload = json.loads(pap.payload_json)

    assert payload["artifact_type"] == "incidents"
    for key in ("incidents", "incident_count", "row_count", "provenance"):
        assert key in payload, f"Missing required key: {key}"

    counts = _count_events(db_session, execution_id)
    assert counts["mounted"].get("incidents", 0) == len(payload["incidents"])
    assert counts["thinking"].get("incidents", 0) == len(payload["incidents"])
