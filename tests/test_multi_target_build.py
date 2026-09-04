"""Multi-target artifact builds under ONE execution.

Covers ``build_artifacts`` — the sequential, shared-execution builder loop used
by ``POST /projects/{id}/build`` when several targets are requested. The agent
panel subscribes to a single execution_id, so all narration for every target
must be emitted against that same execution, in order, and the execution must
be finalized with ``agent.completed`` so the panel returns to idle.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pandas as pd
import pytest
from sqlmodel import Session, select

import anvaya.agent.executor  # noqa: F401  # ensures anvaya.generations.builder is fully loaded before ArtifactBuilder
from anvaya.generations.builder import build_artifacts
from anvaya.models.execution import Execution, ExecutionEvent
from anvaya.models.project import Dataset, Generation, Project


@pytest.fixture(autouse=True)
def _disable_builder_sleep(monkeypatch):
    """Keep builder tests fast without changing the constant values."""
    monkeypatch.setattr("time.sleep", lambda _seconds: None)


def _attack_df(row_count: int = 40, seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    hosts = [f"10.0.0.{i}" for i in range(1, row_count + 1)]
    rows = []
    for i in range(row_count):
        src = rng.choice(hosts)
        dst = rng.choice(hosts)
        while dst == src:
            dst = rng.choice(hosts)
        rows.append(
            {
                "src_ip": src,
                "dst_ip": dst,
                "severity": ["high", "medium", "low"][i % 3],
                "host": f"H{i % 10}",
                "user": f"u{i % 5}",
                "event_type": "net",
                "attack_family": "lateral",
                "label": "attack",
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def test_project() -> Project:
    return Project(
        project_id="PRJ-MULTI",
        organization_id="ORG-1",
        name="Multi Target Build Project",
        created_by="u1",
    )


def _setup_dataset(
    session: Session, project: Project, dataset_id: str, df: pd.DataFrame, csv_dir: Path
) -> Dataset:
    # build_artifacts looks the project up by id, so it must be persisted
    # (unlike the transient project object the direct ArtifactBuilder tests use).
    existing = session.exec(
        select(Project).where(Project.project_id == project.project_id)
    ).first()
    if not existing:
        session.add(project)
        session.commit()
        session.refresh(project)
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


def test_build_artifacts_runs_all_targets_under_one_execution(
    db_session: Session, test_project: Project, tmp_path: Path
):
    """Three targets build sequentially, all narrated under ONE execution_id."""
    dataset = _setup_dataset(
        db_session, test_project, "DS-MULTI", _attack_df(), tmp_path
    )
    execution = Execution(
        execution_id="EXEC-MULTI",
        objective="Build orbits, incidents, impacts",
        status="running",
    )
    db_session.add(execution)
    db_session.commit()

    targets = ["orbits", "incidents", "impacts"]
    generation_ids = []
    for target in targets:
        generation = _setup_generation(
            db_session, test_project, dataset, f"GEN-MULTI-{target}", target
        )
        generation_ids.append(generation.generation_id)

    result = build_artifacts(
        generation_ids, "EXEC-MULTI", test_project.project_id, session=db_session
    )

    assert result["status"] == "completed"
    assert [r["target"] for r in result["results"]] == targets
    assert all(r["status"] == "completed" for r in result["results"])

    events = db_session.exec(
        select(ExecutionEvent).where(ExecutionEvent.execution_id == "EXEC-MULTI")
        .order_by(ExecutionEvent.sequence)  # type: ignore[arg-type]
    ).all()
    assert events, "no events emitted"

    # Every event belongs to the ONE shared execution (continuity for the panel).
    assert {e.execution_id for e in events} == {"EXEC-MULTI"}

    # Each target announced its own generation.started, in request order.
    started_targets = [
        json.loads(e.payload_json or "{}").get("target")
        for e in events
        if e.type == "generation.started"
    ]
    assert started_targets == targets

    # The batch is finalized so the panel returns to idle.
    assert events[-1].type == "agent.completed"

    finalized = db_session.exec(
        select(Execution).where(Execution.execution_id == "EXEC-MULTI")
    ).first()
    assert finalized is not None and finalized.status == "completed"


def test_build_artifacts_continues_after_failed_generation(
    db_session: Session, test_project: Project, tmp_path: Path
):
    """A missing generation row fails that target but does not abort the batch."""
    dataset = _setup_dataset(
        db_session, test_project, "DS-MULTI-2", _attack_df(seed=11), tmp_path
    )
    execution = Execution(
        execution_id="EXEC-MULTI-2",
        objective="Build orbits, impacts",
        status="running",
    )
    db_session.add(execution)
    db_session.commit()

    good = _setup_generation(
        db_session, test_project, dataset, "GEN-MULTI-2-IMPACTS", "impacts"
    )

    result = build_artifacts(
        ["GEN-DOES-NOT-EXIST", good.generation_id],
        "EXEC-MULTI-2",
        test_project.project_id,
        session=db_session,
    )

    assert result["status"] == "failed"
    assert result["results"][0]["status"] == "failed"
    assert result["results"][1]["status"] == "completed"

    events = db_session.exec(
        select(ExecutionEvent).where(ExecutionEvent.execution_id == "EXEC-MULTI-2")
    ).all()
    types = {e.type for e in events}
    assert "generation.failed" in types
    assert "generation.completed" in types
    assert events[-1].type == "agent.completed"
