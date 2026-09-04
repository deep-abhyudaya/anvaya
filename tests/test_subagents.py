"""Tests for the Devin-like subagent layer."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def client():
    db_path = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["DEBUG"] = "false"

    import importlib

    import anvaya.config
    import anvaya.db
    import anvaya.main

    importlib.reload(anvaya.config)
    importlib.reload(anvaya.db)
    importlib.reload(anvaya.main)

    from anvaya.db import init_db
    from anvaya.main import app

    init_db()
    with TestClient(app) as c:
        yield c

    from anvaya.agent.subagents import subagent_spawner

    for thread in list(subagent_spawner._threads.values()):
        thread.join(timeout=2.0)
    subagent_spawner._threads.clear()

    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass


def test_list_subagent_profiles(client):
    response = client.get("/api/v1/agent/subagents/profiles")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    ids = {p["id"] for p in data["items"]}
    assert "explore" in ids
    assert "general" in ids
    assert "tester" in ids


def test_get_subagent_profile(client):
    response = client.get("/api/v1/agent/subagents/profiles/explore")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "explore"
    assert "allowed_tools" in data
    assert "get_incident" in data["allowed_tools"]


def test_spawn_foreground_subagent(client):
    inc = client.post(
        "/api/v1/incidents",
        json={"title": "Subagent test", "severity": "high", "attack_family": "lateral_movement"},
    ).json()
    incident_id = inc["incident_id"]

    parent = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    ).json()
    parent_id = parent["execution_id"]

    response = client.post(
        "/api/v1/agent/subagents",
        json={
            "task": f"Research incident {incident_id}",
            "profile_id": "explore",
            "mode": "foreground",
            "parent_execution_id": parent_id,
            "incident_id": incident_id,
        },
    )
    assert response.status_code == 200
    sub = response.json()
    assert sub["profile_id"] == "explore"
    assert sub["status"] in ("completed", "failed")
    assert sub["child_execution_id"]

    events = client.get(f"/api/v1/agent/executions/{parent_id}/events").json()["items"]
    types = {e["type"] for e in events}
    assert "subagent.spawned" in types
    assert "subagent.started" in types
    assert "subagent.completed" in types or "subagent.failed" in types


def test_explore_subagent_cannot_seal(client):
    inc = client.post(
        "/api/v1/incidents",
        json={"title": "Explore test", "severity": "high", "attack_family": "lateral_movement"},
    ).json()
    incident_id = inc["incident_id"]

    parent = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    ).json()
    parent_id = parent["execution_id"]

    sub = client.post(
        "/api/v1/agent/subagents",
        json={
            "task": f"Research and audit {incident_id}",
            "profile_id": "explore",
            "mode": "foreground",
            "parent_execution_id": parent_id,
            "incident_id": incident_id,
        },
    ).json()

    child_events = (
        client.get(f"/api/v1/agent/executions/{sub['child_execution_id']}/events").json()["items"]
    )
    tools = {e["tool_name"] for e in child_events if e.get("tool_name")}
    assert "seal_incident" not in tools
    assert "append_audit_record" not in tools
    assert "get_incident" in tools


def test_tester_subagent_runs_tests(client):
    inc = client.post(
        "/api/v1/incidents",
        json={"title": "Tester test", "severity": "high", "attack_family": "lateral_movement"},
    ).json()
    incident_id = inc["incident_id"]

    parent = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    ).json()
    parent_id = parent["execution_id"]

    sub = client.post(
        "/api/v1/agent/subagents",
        json={
            "task": "run tests for tests/test_llm_providers.py",
            "profile_id": "tester",
            "mode": "foreground",
            "parent_execution_id": parent_id,
            "incident_id": incident_id,
        },
    ).json()

    assert sub["status"] == "completed"
    child_events = (
        client.get(f"/api/v1/agent/executions/{sub['child_execution_id']}/events").json()["items"]
    )
    tools = {e["tool_name"] for e in child_events if e.get("tool_name")}
    assert "run_tests" in tools


def test_background_subagent_and_list(client):
    inc = client.post(
        "/api/v1/incidents",
        json={"title": "Background test", "severity": "high", "attack_family": "lateral_movement"},
    ).json()
    incident_id = inc["incident_id"]

    parent = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    ).json()
    parent_id = parent["execution_id"]

    sub = client.post(
        "/api/v1/agent/subagents",
        json={
            "task": f"Research incident {incident_id}",
            "profile_id": "explore",
            "mode": "background",
            "parent_execution_id": parent_id,
            "incident_id": incident_id,
        },
    ).json()

    assert sub["status"] == "pending"
    assert sub["mode"] == "background"

    response = client.get(f"/api/v1/agent/executions/{parent_id}/subagents")
    assert response.status_code == 200
    data = response.json()
    assert any(s["subagent_id"] == sub["subagent_id"] for s in data["items"])

    response = client.get(f"/api/v1/agent/subagents/{sub['subagent_id']}")
    assert response.status_code == 200
    assert response.json()["subagent_id"] == sub["subagent_id"]


def test_cancel_background_subagent(client):
    inc = client.post(
        "/api/v1/incidents",
        json={"title": "Cancel test", "severity": "high", "attack_family": "lateral_movement"},
    ).json()
    incident_id = inc["incident_id"]

    parent = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    ).json()
    parent_id = parent["execution_id"]

    sub = client.post(
        "/api/v1/agent/subagents",
        json={
            "task": f"Research incident {incident_id}",
            "profile_id": "explore",
            "mode": "background",
            "parent_execution_id": parent_id,
            "incident_id": incident_id,
        },
    ).json()

    response = client.post(f"/api/v1/agent/subagents/{sub['subagent_id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_subagent_nesting_rejected(client):
    inc = client.post(
        "/api/v1/incidents",
        json={"title": "Nesting test", "severity": "high", "attack_family": "lateral_movement"},
    ).json()
    incident_id = inc["incident_id"]

    parent = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    ).json()
    parent_id = parent["execution_id"]

    first = client.post(
        "/api/v1/agent/subagents",
        json={
            "task": f"Explore incident {incident_id}",
            "profile_id": "explore",
            "mode": "foreground",
            "parent_execution_id": parent_id,
            "incident_id": incident_id,
        },
    ).json()

    response = client.post(
        "/api/v1/agent/subagents",
        json={
            "task": "nested research",
            "profile_id": "general",
            "mode": "background",
            "parent_execution_id": first["child_execution_id"],
            "incident_id": incident_id,
        },
    )
    assert response.status_code == 400
    assert "nesting" in response.json()["detail"].lower()


def test_resume_subagent(client):
    inc = client.post(
        "/api/v1/incidents",
        json={"title": "Resume test", "severity": "high", "attack_family": "lateral_movement"},
    ).json()
    incident_id = inc["incident_id"]

    parent = client.post(
        "/api/v1/agent/execute",
        json={"objective": f"Investigate {incident_id}", "incident_id": incident_id},
    ).json()
    parent_id = parent["execution_id"]

    sub = client.post(
        "/api/v1/agent/subagents",
        json={
            "task": f"Research {incident_id}",
            "profile_id": "explore",
            "mode": "foreground",
            "parent_execution_id": parent_id,
            "incident_id": incident_id,
        },
    ).json()

    response = client.post(
        f"/api/v1/agent/subagents/{sub['subagent_id']}/resume",
        json={"task": f"Continue research for {incident_id}"},
    )
    assert response.status_code == 200
    new_sub = response.json()
    assert new_sub["status"] in ("pending", "running", "completed", "failed")
    assert new_sub["mode"] == "foreground"
