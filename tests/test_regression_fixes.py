"""Regression tests for agentic chat, risk scores, replay, and ecosystem simulation."""

from __future__ import annotations

import os
from io import BytesIO

import pytest
from anvaya.config import settings
from fastapi.testclient import TestClient
from sqlmodel import Session


@pytest.fixture(scope="session", autouse=True)
def _register_project_models():
    """Register project/dataset models before any in-memory db is created."""
    from anvaya.models.project import (  # noqa: F401
        Dataset,
        Project,
        ProjectArtifact,
        ProjectArtifactPayload,
    )

    yield


@pytest.fixture(scope="function")
def client(tmp_path, monkeypatch):
    """FastAPI TestClient with auth patched and datasets directed to tmp."""
    db_path = tmp_path / "regression.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["DEBUG"] = "false"

    import importlib

    import anvaya.config

    importlib.reload(anvaya.config)
    import anvaya.db

    importlib.reload(anvaya.db)
    from anvaya.db import init_db
    from anvaya.main import app
    from anvaya.routers import projects

    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    settings.datasets_dir = datasets_dir

    init_db()

    class DummyAuth:
        organization = {"id": "ORG-REG"}
        user_id = "user-reg"
        member_role = "owner"

        def require_org(self):
            return self.organization

    monkeypatch.setattr(
        projects,
        "get_auth_context",
        lambda request, db_session: DummyAuth(),
    )

    with TestClient(app) as c:
        yield c


DATASET = b"""timestamp,src_ip,dst_ip,port,severity,event_type,attack_family,host,user
2024-01-01T10:00:00Z,10.0.0.1,10.0.0.2,443,high,network,lateral,A,B
2024-01-01T10:00:01Z,10.0.0.2,10.0.0.1,443,high,network,lateral,B,A
2024-01-01T10:00:02Z,10.0.0.3,10.0.0.4,443,medium,network,exfil,C,D
"""


def _upload_dataset(client: TestClient, project_id: str):
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        files={"file": ("reg.csv", BytesIO(DATASET), "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _generate(client: TestClient, project_id: str, types: list[str], dataset_id: str = ""):
    payload = {"requested_artifacts": types}
    if dataset_id:
        payload["dataset_id"] = dataset_id
    response = client.post(f"/api/v1/projects/{project_id}/generate", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_replay_start_time_is_clock_only(client):
    """Replay scenarios must expose start_time as HH:MM:SS, not a full ISO timestamp."""
    resp = client.post("/api/v1/projects", json={"name": "Replay Reg"})
    assert resp.status_code == 200
    project_id = resp.json()["project_id"]

    ds = _upload_dataset(client, project_id)
    _generate(client, project_id, ["incidents", "replay"], ds["dataset_id"])

    payload = client.get(f"/api/v1/projects/{project_id}/replay/latest").json()["payload"]
    assert payload and payload.get("replays")
    start = payload["replays"][0]["start_time"]
    assert ":" in start
    assert "T" not in start
    parts = start.split(":")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


def test_incident_risk_score_is_nonzero(client):
    """Generated incidents must have a meaningful risk_score, not the default 0.0."""
    resp = client.post("/api/v1/projects", json={"name": "Risk Reg"})
    assert resp.status_code == 200
    project_id = resp.json()["project_id"]

    ds = _upload_dataset(client, project_id)
    _generate(client, project_id, ["incidents"], ds["dataset_id"])

    payload = client.get(f"/api/v1/projects/{project_id}/incidents/latest").json()["payload"]
    assert payload and payload.get("incidents")
    risks = [inc.get("risk_score", 0.0) for inc in payload["incidents"]]
    assert risks, "no incidents generated"
    assert all(r > 0 for r in risks), f"incident risk scores are zero: {risks}"


def test_orbit_risk_scores_have_spread(client):
    """Generated orbits must have non-uniform risk scores (regression for the
    ~0.10/0.11 orbit lock bug)."""
    resp = client.post("/api/v1/projects", json={"name": "Orbit Risk Reg"})
    assert resp.status_code == 200
    project_id = resp.json()["project_id"]

    ds = _upload_dataset(client, project_id)
    _generate(client, project_id, ["orbits"], ds["dataset_id"])

    payload = client.get(f"/api/v1/projects/{project_id}/orbits/latest").json()[
        "payload"
    ]
    assert payload and payload.get("orbits"), "no orbits generated"
    risks = [o.get("risk_score", 0.0) for o in payload["orbits"]]
    assert risks, "no orbit risk scores"
    assert len(set(round(r, 2) for r in risks)) >= 2, f"orbit risks are uniform: {risks}"


def test_ecosystem_simulation_steps_alter_state(client):
    """The simulation endpoint must return a different graph state per step."""
    resp = client.post("/api/v1/projects", json={"name": "Eco Reg"})
    assert resp.status_code == 200
    project_id = resp.json()["project_id"]

    ds = _upload_dataset(client, project_id)
    _generate(client, project_id, ["ecosystem"], ds["dataset_id"])

    states = []
    for step in (0, 1, 4, 8):
        res = client.get(
            "/api/v1/simulation/ecosystem",
            params={"project_id": project_id, "mode": "CONTAIN", "step": step},
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["nodes"]
        assert data["step"] == step
        states.append((step, data["compromised"], data["blockedEdges"], data["liveAttacks"]))

    assert any(s[1] or s[2] or s[3] for s in states[1:]), "simulation produced no changing state"


def test_chat_engine_loads_artifact_context(db_session: Session):
    """The chat engine must resolve artifact context for questions about generated artifacts."""
    import json

    from anvaya.agent.chat import ChatEngine
    from anvaya.models.project import Project, ProjectArtifact, ProjectArtifactPayload

    project = Project(
        project_id="PRJ-CHAT",
        organization_id="ORG-1",
        name="Chat Test",
        created_by="u1",
    )
    db_session.add(project)
    db_session.commit()

    artifact = ProjectArtifact(
        project_id="PRJ-CHAT",
        dataset_id="DS-1",
        generation_id="GEN-1",
        artifact_type="orbits",
        artifact_id="ART-1",
    )
    db_session.add(artifact)
    db_session.commit()

    payload = ProjectArtifactPayload(
        project_id="PRJ-CHAT",
        dataset_id="DS-1",
        generation_id="GEN-1",
        artifact_type="orbits",
        artifact_id="ART-1",
        payload_json=json.dumps({"orbits": [{"source": "A", "target": "B"}]}),
    )
    db_session.add(payload)
    db_session.commit()

    engine = ChatEngine(db_session)
    context = engine._load_artifact_context("What do the orbits show?", "PRJ-CHAT")
    assert context is not None
    assert "Generated orbits artifact" in context
    assert "A" in context and "B" in context


def test_infer_artifact_types_respects_explicit_type():
    """Phrases like 'delete only all incidents' must target incidents, not all artifacts."""
    from anvaya.agent.artifact_utils import infer_artifact_types

    assert infer_artifact_types("delete all incidents") == ["incidents"]
    assert infer_artifact_types("delete only all incidents") == ["incidents"]
    assert infer_artifact_types("regenerate all orbits and reach") == ["orbits", "reach"]
    assert infer_artifact_types("delete all") == ["all"]
    assert infer_artifact_types("regenerate") == ["all"]
    assert infer_artifact_types("generate") == ["all"]

    assert "all" not in infer_artifact_types("delete small incidents")
    assert "all" not in infer_artifact_types("explain overall reach")

    assert infer_artifact_types("delete all incidents nearby") == ["incidents"]
    assert infer_artifact_types("regenerate the street tree view") == ["arbor"]


def test_infer_artifact_action_detects_delete_regenerate():
    from anvaya.agent.artifact_utils import infer_artifact_action

    assert infer_artifact_action("delete all incidents") == "delete"
    assert infer_artifact_action("regenerate reach") == "regenerate"
    assert infer_artifact_action("generate orbits") == "generate"


def test_resolve_implicit_project_covers_all_artifact_types(db_session: Session):
    """Every artifact type can be targeted by an implicit project fallback."""
    from anvaya.agent.orchestrator import _resolve_implicit_project
    from anvaya.models.project import Project

    project = Project(
        project_id="PRJ-IMPLICIT",
        organization_id="ORG-1",
        name="Implicit Test",
        created_by="u1",
    )
    db_session.add(project)
    db_session.commit()

    objectives = [
        "generate orbits",
        "build arbor",
        "create trophy wall",
        "regenerate replay",
        "delete all incidents",
        "refresh ledger",
        "update impacts",
        "run segments",
        "make ecosystem",
        "produce arena",
        "generate all",
    ]
    for objective in objectives:
        assert _resolve_implicit_project(db_session, objective) == project.project_id, objective

    assert _resolve_implicit_project(db_session, "Investigate something") == ""
    assert _resolve_implicit_project(db_session, "explain overall reach") == ""


def test_chat_resolve_context_falls_back_to_latest_project(db_session: Session, tmp_path):
    """Generic read commands like 'read it' resolve to the latest project."""
    import csv as csv_module

    from anvaya.agent.chat import ChatEngine
    from anvaya.models.project import Dataset, Project

    project = Project(
        project_id="PRJ-READ",
        organization_id="ORG-1",
        name="Read Test",
        created_by="u1",
    )
    db_session.add(project)
    db_session.commit()

    csv_path = tmp_path / "reg.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv_module.writer(f)
        writer.writerow(["a", "b"])
        writer.writerow(["1", "2"])

    dataset = Dataset(
        dataset_id="DS-READ",
        organization_id="ORG-1",
        project_id=project.project_id,
        created_by="u1",
        filename="reg.csv",
        format="csv",
        source=str(csv_path),
        status="ready",
    )
    db_session.add(dataset)
    db_session.commit()

    engine = ChatEngine(db_session)
    context = engine._resolve_context("read it", "", "")
    assert context is not None
    assert "reg.csv" in context or "a" in context
