"""Golden end-to-end test: custom dataset -> world -> artifacts -> persistence.

This test proves the entire dataset-grounded artifact pipeline for the
Phase 20 verification matrix:

  CUSTOM DATASET -> DATASET PROFILE -> WORLD MODEL -> ARTIFACTS -> PERSISTENCE
  -> API READ -> REGENERATE -> DELETE -> REGENERATE AGAIN
"""

from __future__ import annotations

import os
from io import BytesIO

import pytest
from anvaya.config import settings
from anvaya.models.project import ARTIFACT_TYPES
from anvaya.routers import projects
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def client(tmp_path, monkeypatch):
    """FastAPI TestClient with auth patched and datasets directed to tmp."""
    db_path = tmp_path / "golden.db"
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
        organization = {"id": "ORG-GOLDEN"}
        user_id = "user-golden"
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


DATASET_A = b"""timestamp,src_ip,dst_ip,port,severity,event_type,attack_family,host,user
2024-01-01T10:00:00Z,10.0.0.1,10.0.0.2,443,high,network,lateral,A,B
2024-01-01T10:00:01Z,10.0.0.2,10.0.0.1,443,high,network,lateral,B,A
2024-01-01T10:00:02Z,10.0.0.3,10.0.0.4,443,medium,network,exfil,C,D
2024-01-01T10:00:03Z,10.0.0.1,10.0.0.2,443,high,network,lateral,A,B
"""

DATASET_B = b"""timestamp,src_ip,dst_ip,port,severity,event_type,attack_family,host,user
2024-01-01T10:00:00Z,10.0.0.1,10.0.0.5,443,high,network,exfil,A,E
2024-01-01T10:00:01Z,10.0.0.5,10.0.0.6,443,high,network,exfil,E,F
2024-01-01T10:00:02Z,10.0.0.6,10.0.0.1,443,high,network,exfil,F,A
2024-01-01T10:00:03Z,10.0.0.1,10.0.0.5,443,high,network,exfil,A,E
"""

REQUIRED_ARTIFACT_FIELDS = {
    "incidents": {"incidents", "incident_count"},
    "arbor": {"tree", "columns"},
    "impacts": {"impacts"},
    "reach": {"items", "incident_id"},
    "replay": {"replays"},
    "ecosystem": {"nodes", "edges", "health", "compromised"},
    "arena": {"stages", "engines", "severity", "consensus"},
    "orbits": {"orbits", "node_count", "edge_count", "blast_radius"},
    "segments": {"items", "nodes", "extra_edges"},
    "trophy_wall": {"trophies", "trophy_count"},
    "ledger": {"records"},
}


def _upload_dataset(client: TestClient, project_id: str, name: str, body: bytes):
    response = client.post(
        f"/api/v1/projects/{project_id}/datasets",
        files={"file": (name, BytesIO(body), "text/csv")},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "ready", f"dataset status: {data['status']}"
    assert data["profile_json"], "dataset profile not built"
    return data


def _generate(client: TestClient, project_id: str, types: list[str], dataset_id: str = ""):
    payload: dict = {"requested_artifacts": types}
    if dataset_id:
        payload["dataset_id"] = dataset_id
    response = client.post(
        f"/api/v1/projects/{project_id}/generate",
        json=payload,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed", f"generation status: {data['status']}"
    return data


def _latest(client: TestClient, project_id: str, artifact_type: str):
    response = client.get(f"/api/v1/projects/{project_id}/{artifact_type}/latest")
    assert response.status_code == 200, response.text
    return response.json()["payload"]


def test_golden_dataset_to_artifact_flow(client, monkeypatch):
    """Create project, upload datasets, generate all artifacts, verify CRUD and differentiation."""
    response = client.post("/api/v1/projects", json={"name": "Golden Flow"})
    assert response.status_code == 200
    project = response.json()
    project_id = project["project_id"]

    ds_a = _upload_dataset(client, project_id, "a.csv", DATASET_A)
    ds_a_id = ds_a["dataset_id"]

    gen_a = _generate(client, project_id, list(ARTIFACT_TYPES), ds_a_id)
    assert gen_a["created_artifacts_json"]

    payloads_a = {}
    for artifact_type in ARTIFACT_TYPES:
        payload = _latest(client, project_id, artifact_type)
        assert payload is not None, f"missing {artifact_type} payload for dataset A"
        assert payload.get("artifact_type") == artifact_type
        assert payload.get("dataset_id") == ds_a_id, f"{artifact_type} has wrong dataset_id"
        assert payload.get("fingerprint"), f"{artifact_type} missing fingerprint"
        assert "provenance" in payload, f"{artifact_type} missing provenance"
        assert payload["provenance"]["dataset_fingerprint"], f"{artifact_type} missing fingerprint"
        missing = REQUIRED_ARTIFACT_FIELDS[artifact_type] - payload.keys()
        assert not missing, f"{artifact_type} missing required fields: {sorted(missing)}"
        payloads_a[artifact_type] = payload

    orbits_a = payloads_a["orbits"]["orbits"]
    orbit_pairs_a = {(o["source"], o["target"]) for o in orbits_a}

    eco_a = payloads_a["ecosystem"]
    assert payloads_a["replay"]["replays"], "replay artifact must contain a scenario"
    replay_a = payloads_a["replay"]["replays"][0]
    assert replay_a["status"] == "pending"
    assert replay_a["verified"] is False
    assert replay_a["detection_before"] is False
    assert replay_a["detection_after"] is False
    assert replay_a["host"] and replay_a["user"]
    assert replay_a["timeline"] and replay_a["stages"]
    trophies_a = payloads_a["trophy_wall"]["trophies"]

    ds_b = _upload_dataset(client, project_id, "b.csv", DATASET_B)
    ds_b_id = ds_b["dataset_id"]
    assert ds_b_id != ds_a_id

    gen_b = _generate(client, project_id, list(ARTIFACT_TYPES), ds_b_id)
    assert gen_b["generation_id"] != gen_a["generation_id"]

    payloads_b = {}
    for artifact_type in ARTIFACT_TYPES:
        payload = _latest(client, project_id, artifact_type)
        assert payload is not None, f"missing {artifact_type} payload for dataset B"
        wrong = f"{artifact_type} still associated with dataset A"
        assert payload.get("dataset_id") == ds_b_id, wrong
        payloads_b[artifact_type] = payload

    orbits_b = payloads_b["orbits"]["orbits"]
    orbit_pairs_b = {(o["source"], o["target"]) for o in orbits_b}
    diff = f"orbits did not change: A={orbit_pairs_a}, B={orbit_pairs_b}"
    assert orbit_pairs_a != orbit_pairs_b, diff

    eco_b = payloads_b["ecosystem"]
    assert (
        eco_b["nodes"] != eco_a["nodes"] or eco_b["edges"] != eco_a["edges"]
    ), "ecosystem graph unchanged"

    replay_b = payloads_b["replay"]["replays"][0]
    assert replay_b["incident_id"] != replay_a["incident_id"], "replay incident_id did not change"

    trophies_b = payloads_b["trophy_wall"]["trophies"]
    assert len(trophies_a) == len(trophies_b) or any(
        a["incident_id"] != b["incident_id"]
        for a, b in zip(trophies_a, trophies_b)
    ), "trophy wall did not reflect new dataset"

    before_id = (
        client.get(f"/api/v1/projects/{project_id}/orbits").json()["items"][0]["artifact_id"]
    )

    regen = client.post(
        f"/api/v1/projects/{project_id}/orbits/regenerate",
        params={"dataset_id": ds_b_id},
    )
    assert regen.status_code == 200, regen.text
    regen_data = regen.json()
    assert regen_data["regenerated"]
    assert regen_data["generation_id"] != gen_b["generation_id"]

    after = _latest(client, project_id, "orbits")
    after_id = client.get(f"/api/v1/projects/{project_id}/orbits").json()["items"][0]["artifact_id"]
    assert after_id != before_id, "regenerate must create a new artifact identity"
    assert after["provenance"]["generation_id"] == regen_data["generation_id"]

    delete_resp = client.delete(f"/api/v1/projects/{project_id}/ecosystem")
    assert delete_resp.status_code == 200, delete_resp.text
    assert delete_resp.json()["deleted"] >= 1

    latest = client.get(f"/api/v1/projects/{project_id}/ecosystem/latest").json()
    assert latest["payload"] is None, "ecosystem payload still present after delete"

    list_resp = client.get(f"/api/v1/projects/{project_id}/ecosystem").json()
    assert len(list_resp["items"]) == 0, "ecosystem artifacts still present after delete"

    regen_eco = client.post(f"/api/v1/projects/{project_id}/ecosystem/regenerate")
    assert regen_eco.status_code == 200, regen_eco.text
    eco_back = _latest(client, project_id, "ecosystem")
    assert eco_back is not None, "ecosystem did not reappear"
    assert eco_back["dataset_id"] == ds_b_id

    orbits_list = client.get(f"/api/v1/projects/{project_id}/orbits").json()
    assert orbits_list["items"]
    artifact_id = orbits_list["items"][0]["artifact_id"]
    detail = client.get(f"/api/v1/projects/{project_id}/orbits/{artifact_id}").json()
    assert detail["artifact_id"] == artifact_id
    assert detail["artifact_type"] == "orbits"
    assert detail["payload"]["provenance"]["dataset_fingerprint"]

    counts = client.get(f"/api/v1/projects/{project_id}/artifact-counts").json()["counts"]
    for artifact_type in ARTIFACT_TYPES:
        assert counts.get(artifact_type, 0) > 0, f"artifact count missing for {artifact_type}"

    class OtherOrgAuth:
        organization = {"id": "ORG-OTHER"}
        user_id = "user-other"
        member_role = "member"

        def require_org(self):
            return self.organization

    monkeypatch.setattr(
        projects,
        "get_auth_context",
        lambda request, db_session: OtherOrgAuth(),
    )
    isolated = client.get(f"/api/v1/projects/{project_id}/orbits/latest")
    assert isolated.status_code == 404, "cross-org access must be denied"
