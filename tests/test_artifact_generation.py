"""Tests for dataset profiling, world model, and artifact generation."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from anvaya.config import settings
from anvaya.dataset_profile import build_dataset_profile, normalize_dataframe
from anvaya.generation import ArtifactGenerator, delete_project_artifacts
from anvaya.models.project import (
    Dataset,
    Generation,
    Project,
    ProjectArtifact,
    ProjectArtifactPayload,
)
from anvaya.world import build_world_model
from sqlmodel import Session


@pytest.fixture
def dataset_a_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "src_ip": ["1.1.1.1", "2.2.2.2", "3.3.3.3"],
            "dst_ip": ["2.2.2.2", "1.1.1.1", "1.1.1.1"],
            "severity": ["high", "high", "medium"],
            "host": ["A", "B", "A"],
            "user": ["u1", "u2", "u1"],
            "event_type": ["net", "net", "auth"],
            "attack_family": ["lateral", "lateral", ""],
            "label": ["attack", "attack", ""],
        }
    )


@pytest.fixture
def dataset_b_df() -> pd.DataFrame:
    """A deliberately different topology from dataset_a."""
    return pd.DataFrame(
        {
            "src_ip": ["1.1.1.1", "2.2.2.2", "3.3.3.3"],
            "dst_ip": ["3.3.3.3", "1.1.1.1", "2.2.2.2"],
            "severity": ["high", "high", "high"],
            "host": ["X", "Y", "Z"],
            "user": ["u1", "u2", "u3"],
            "event_type": ["net", "net", "net"],
            "attack_family": ["exfil", "exfil", "exfil"],
            "label": ["attack", "attack", "attack"],
        }
    )


@pytest.fixture
def test_project() -> Project:
    return Project(
        project_id="PRJ-TEST",
        organization_id="ORG-1",
        name="Test Project",
        created_by="u1",
    )


def _write_csv(df: pd.DataFrame, dataset_id: str) -> str:
    path = settings.datasets_dir / f"{dataset_id}.csv"
    df.to_csv(path, index=False)
    return str(path)


def test_dataset_profile_maps_security_columns():
    df = pd.DataFrame(
        {
            "src_ip": ["1.1.1.1"],
            "dst_ip": ["2.2.2.2"],
            "severity": ["high"],
            "event_type": ["network"],
            "attack_family": ["lateral"],
        }
    )
    profile = build_dataset_profile(df, "DS-MAP")
    assert profile.canonical_map["source_ip"] == "src_ip"
    assert profile.canonical_map["destination_ip"] == "dst_ip"
    assert profile.canonical_map["severity"] == "severity"
    assert profile.canonical_map["event_type"] == "event_type"
    assert profile.canonical_map["attack_family"] == "attack_family"


def test_dataset_profile_detects_network_fields():
    df = pd.DataFrame(
        {
            "client_ip": ["1.1.1.1", "2.2.2.2"],
            "server_ip": ["2.2.2.2", "1.1.1.1"],
            "proto": ["tcp", "udp"],
        }
    )
    profile = build_dataset_profile(df, "DS-NET")
    assert "source_ip" in profile.canonical_map
    assert "destination_ip" in profile.canonical_map
    assert "protocol" in profile.canonical_map
    src_col = profile.column("source_ip")
    assert src_col is not None and src_col.is_network


def test_world_model_derives_orbits_and_incidents(dataset_a_df: pd.DataFrame):
    profile = build_dataset_profile(dataset_a_df, "DS-A")
    df = normalize_dataframe(dataset_a_df, profile)
    world = build_world_model(df, profile, "PRJ-1", "DS-A", "GEN-A")

    assert world.statistics["event_count"] == 3
    assert world.statistics["incident_count"] >= 1
    assert world.statistics["orbit_count"] >= 1
    assert world.orbits[0].forward_count >= 1
    assert any(inc.attack_family for inc in world.incidents)


def test_different_datasets_produce_different_orbits(
    dataset_a_df: pd.DataFrame, dataset_b_df: pd.DataFrame
):
    profile_a = build_dataset_profile(dataset_a_df, "DS-A")
    df_a = normalize_dataframe(dataset_a_df, profile_a)
    world_a = build_world_model(df_a, profile_a, "PRJ-1", "DS-A", "GEN-A")

    profile_b = build_dataset_profile(dataset_b_df, "DS-B")
    df_b = normalize_dataframe(dataset_b_df, profile_b)
    world_b = build_world_model(df_b, profile_b, "PRJ-1", "DS-B", "GEN-B")

    orbits_a = {(o.source, o.target) for o in world_a.orbits}
    orbits_b = {(o.source, o.target) for o in world_b.orbits}
    assert orbits_a != orbits_b, "Different datasets must produce different orbit topologies"


def test_artifact_generator_creates_all_artifact_payloads(
    db_session: Session, dataset_a_df: pd.DataFrame, test_project: Project
):
    _write_csv(dataset_a_df, "DS-ARTIFACTS")

    db_session.add(test_project)
    dataset = Dataset(
        dataset_id="DS-ARTIFACTS",
        organization_id="ORG-1",
        project_id=test_project.project_id,
        created_by="u1",
        filename="a.csv",
        format="csv",
        size=100,
        source=str(settings.datasets_dir / "DS-ARTIFACTS.csv"),
        status="ready",
    )
    db_session.add(dataset)
    generation = Generation(
        generation_id="GEN-ARTIFACTS",
        organization_id="ORG-1",
        project_id=test_project.project_id,
        dataset_id="DS-ARTIFACTS",
        user_id="u1",
        requested_artifacts_json="[]",
        status="pending",
    )
    db_session.add(generation)
    db_session.commit()

    from anvaya.models.project import ARTIFACT_TYPES as MODEL_ARTIFACT_TYPES

    generator = ArtifactGenerator(db_session, test_project, generation, dataset)
    created = generator.generate_all(MODEL_ARTIFACT_TYPES)

    assert sum(created.values()) == len(MODEL_ARTIFACT_TYPES)
    for artifact_type in MODEL_ARTIFACT_TYPES:
        pa = (
            db_session.query(ProjectArtifact)
            .filter(
                ProjectArtifact.project_id == test_project.project_id,
                ProjectArtifact.artifact_type == artifact_type,
            )
            .first()
        )
        assert pa is not None, f"Missing ProjectArtifact for {artifact_type}"
        pap = (
            db_session.query(ProjectArtifactPayload)
            .filter(
                ProjectArtifactPayload.artifact_id == pa.artifact_id,
            )
            .first()
        )
        assert pap is not None, f"Missing payload for {artifact_type}"
        payload = json.loads(pap.payload_json)
        assert payload.get("dataset_id") == "DS-ARTIFACTS"
        assert "provenance" in payload


def test_artifact_provenance_contains_fingerprint(
    db_session: Session, dataset_a_df: pd.DataFrame, test_project: Project
):
    _write_csv(dataset_a_df, "DS-PROV")

    db_session.add(test_project)
    dataset = Dataset(
        dataset_id="DS-PROV",
        organization_id="ORG-1",
        project_id=test_project.project_id,
        created_by="u1",
        filename="a.csv",
        format="csv",
        size=100,
        source=str(settings.datasets_dir / "DS-PROV.csv"),
        status="ready",
    )
    db_session.add(dataset)
    generation = Generation(
        generation_id="GEN-PROV",
        organization_id="ORG-1",
        project_id=test_project.project_id,
        dataset_id="DS-PROV",
        user_id="u1",
        requested_artifacts_json="[]",
        status="pending",
    )
    db_session.add(generation)
    db_session.commit()

    generator = ArtifactGenerator(db_session, test_project, generation, dataset)
    generator.generate_all(["orbits"])

    pap = (
        db_session.query(ProjectArtifactPayload)
        .filter(
            ProjectArtifactPayload.artifact_type == "orbits",
            ProjectArtifactPayload.project_id == test_project.project_id,
        )
        .first()
    )
    payload = json.loads(pap.payload_json)
    assert payload["provenance"]["dataset_fingerprint"]
    assert payload["provenance"]["events_used"] == 3


def test_delete_artifacts_cleans_payloads(
    db_session: Session, dataset_a_df: pd.DataFrame, test_project: Project
):
    _write_csv(dataset_a_df, "DS-DEL")

    db_session.add(test_project)
    dataset = Dataset(
        dataset_id="DS-DEL",
        organization_id="ORG-1",
        project_id=test_project.project_id,
        created_by="u1",
        filename="a.csv",
        format="csv",
        size=100,
        source=str(settings.datasets_dir / "DS-DEL.csv"),
        status="ready",
    )
    db_session.add(dataset)
    generation = Generation(
        generation_id="GEN-DEL",
        organization_id="ORG-1",
        project_id=test_project.project_id,
        dataset_id="DS-DEL",
        user_id="u1",
        requested_artifacts_json="[]",
        status="pending",
    )
    db_session.add(generation)
    db_session.commit()

    generator = ArtifactGenerator(db_session, test_project, generation, dataset)
    generator.generate_all(["orbits"])
    assert (
        db_session.query(ProjectArtifact)
        .filter(ProjectArtifact.project_id == test_project.project_id)
        .count()
        >= 1
    )

    deleted = delete_project_artifacts(
        db_session, test_project.project_id, ["orbits"], delete_generations=False
    )
    assert deleted >= 1
    assert (
        db_session.query(ProjectArtifact)
        .filter(
            ProjectArtifact.project_id == test_project.project_id,
            ProjectArtifact.artifact_type == "orbits",
        )
        .count()
        == 0
    )


def test_agent_manage_artifacts_lifecycle_emits_events(
    db_session: Session, dataset_a_df: pd.DataFrame, test_project: Project
):
    _write_csv(dataset_a_df, "DS-AGENT")

    db_session.add(test_project)
    dataset = Dataset(
        dataset_id="DS-AGENT",
        organization_id="ORG-1",
        project_id=test_project.project_id,
        created_by="u1",
        filename="a.csv",
        format="csv",
        size=100,
        source=str(settings.datasets_dir / "DS-AGENT.csv"),
        status="ready",
    )
    db_session.add(dataset)
    db_session.commit()

    from anvaya.agent.executor import LocalToolExecutor
    from anvaya.models.execution import ExecutionEvent
    from anvaya.models.project import ARTIFACT_TYPES as MODEL_ARTIFACT_TYPES
    from anvaya.models.replay import ReplayRun

    executor = LocalToolExecutor(db_session)

    result = executor.execute(
        "manage_artifacts",
        {
            "project_id": test_project.project_id,
            "dataset_id": "DS-AGENT",
            "action": "generate",
            "requested_artifacts": ["all"],
        },
        execution_id="EXEC-AGENT",
    )
    assert result.status == "success", result.error_message
    created_types = {
        row.artifact_type
        for row in db_session.query(ProjectArtifact)
        .filter(ProjectArtifact.project_id == test_project.project_id)
        .all()
    }
    assert created_types == set(MODEL_ARTIFACT_TYPES)
    replay_run = db_session.query(ReplayRun).filter(ReplayRun.scenario_id == "DS-AGENT").first()
    assert replay_run is not None
    assert replay_run.pre_patch_detected is False
    assert replay_run.post_patch_detected is False
    assert replay_run.post_patch_rule_id is None

    pa = (
        db_session.query(ProjectArtifact)
        .filter(
            ProjectArtifact.project_id == test_project.project_id,
            ProjectArtifact.artifact_type == "orbits",
        )
        .first()
    )
    assert pa is not None

    events = (
        db_session.query(ExecutionEvent)
        .filter(ExecutionEvent.execution_id == "EXEC-AGENT")
        .order_by(ExecutionEvent.sequence)
        .all()
    )
    event_types = [e.type for e in events]
    assert event_types.count("artifact.generating") >= len(MODEL_ARTIFACT_TYPES)
    assert event_types.count("artifact.saved") == len(MODEL_ARTIFACT_TYPES)
    assert "agent.artifact_action_complete" in event_types
    assert event_types.count("generation.started") >= len(MODEL_ARTIFACT_TYPES)
    assert event_types.count("artifact.completed") >= len(MODEL_ARTIFACT_TYPES)
    assert event_types.count("element.thinking") > 0
    assert event_types.count("element.mounted") > 0

    before_id = pa.artifact_id
    result = executor.execute(
        "manage_artifacts",
        {
            "project_id": test_project.project_id,
            "dataset_id": "DS-AGENT",
            "action": "regenerate",
            "requested_artifacts": ["orbits"],
        },
        execution_id="EXEC-AGENT",
    )
    assert result.status == "success"
    after = (
        db_session.query(ProjectArtifact)
        .filter(
            ProjectArtifact.project_id == test_project.project_id,
            ProjectArtifact.artifact_type == "orbits",
        )
        .first()
    )
    assert after is not None
    assert after.artifact_id != before_id

    result = executor.execute(
        "manage_artifacts",
        {
            "project_id": test_project.project_id,
            "action": "delete",
            "requested_artifacts": ["orbits"],
        },
        execution_id="EXEC-AGENT",
    )
    assert result.status == "success"
    assert (
        db_session.query(ProjectArtifact)
        .filter(
            ProjectArtifact.project_id == test_project.project_id,
            ProjectArtifact.artifact_type == "orbits",
        )
        .count()
        == 0
    )
