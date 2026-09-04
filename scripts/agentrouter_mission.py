#!/usr/bin/env python3
"""Manual end-to-end adaptive mission using AgentRouter.

This script runs a real autonomous investigation against a synthetic incident
with an AgentRouter model, proving the full chain:

  AgentRouter → streaming → tool call → tool result → adaptive loop
  → verification → final finding.

It uses a temporary SQLite database and the FastAPI TestClient so it can run
without a running server. The API key is read from the environment and is never
logged.
"""

from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime, timezone

if not os.environ.get("AGENTROUTER_API_KEY"):
    os.environ["AGENTROUTER_API_KEY"] = (
        open("/home/de3p/Documents/Next.js/Anavaya/.env")  # noqa: SIM115
        .read()
        .split("AGENTROUTER_API_KEY=")[1]
        .split("\n")[0]
        .strip()
    )

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
os.environ["DEBUG"] = "false"

import importlib

import anvaya.config
import anvaya.db
import anvaya.main

importlib.reload(anvaya.config)
importlib.reload(anvaya.db)
importlib.reload(anvaya.main)

from anvaya.db import engine, init_db
from anvaya.main import app
from anvaya.models.enums import TelemetryEventType
from anvaya.models.graph import GraphEdge, GraphNode
from anvaya.models.telemetry import TelemetryEvent
from fastapi.testclient import TestClient
from sqlmodel import Session


def _create_incident(client: TestClient) -> str:
    response = client.post(
        "/api/v1/incidents",
        json={
            "title": "AgentRouter adaptive mission",
            "severity": "critical",
            "attack_family": "lateral_movement",
            "host": "WS-001",
            "user": "eve",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["incident_id"]


def _seed_data(client: TestClient, incident_id: str) -> None:
    """Seed the incident with attack telemetry and graph context."""
    base = datetime.now(timezone.utc)
    events = [
        TelemetryEvent(
            event_id="E1",
            incident_id=incident_id,
            event_type=TelemetryEventType.AUTH_LOGIN,
            timestamp=base,
            actor="eve",
            host="WS-001",
            source="WS-001",
            destination="DC-01",
            process="sshd",
            is_off_hours=True,
            is_new_device=True,
            is_attack=True,
            attack_family="lateral_movement",
        ),
        TelemetryEvent(
            event_id="E2",
            incident_id=incident_id,
            event_type=TelemetryEventType.LATERAL_MOVE,
            timestamp=base,
            actor="eve",
            host="WS-001",
            source="WS-001",
            destination="SERVER-09",
            process="psexec",
            is_lateral_movement=True,
            is_attack=True,
            attack_family="lateral_movement",
        ),
        TelemetryEvent(
            event_id="E3",
            incident_id=incident_id,
            event_type=TelemetryEventType.PRIVILEGE_CHANGE,
            timestamp=base,
            actor="eve",
            host="SERVER-09",
            source="SERVER-09",
            destination="DC-01",
            process="mimikatz",
            is_privilege_escalation=True,
            is_attack=True,
            attack_family="lateral_movement",
        ),
    ]
    nodes = [
        GraphNode(
            node_id="WS-001",
            incident_id=incident_id,
            label="WS-001",
            node_type="host",
            is_compromised=True,
            impact_score=0.8,
        ),
        GraphNode(
            node_id="SERVER-09",
            incident_id=incident_id,
            label="SERVER-09",
            node_type="host",
            is_compromised=True,
            impact_score=0.9,
        ),
        GraphNode(
            node_id="DC-01",
            incident_id=incident_id,
            label="DC-01",
            node_type="host",
            is_critical=True,
            impact_score=0.95,
        ),
    ]
    edges = [
        GraphEdge(
            source_node_id="WS-001",
            target_node_id="SERVER-09",
            incident_id=incident_id,
            edge_type="attack_path",
            is_observed=True,
        ),
        GraphEdge(
            source_node_id="SERVER-09",
            target_node_id="DC-01",
            incident_id=incident_id,
            edge_type="attack_path",
            is_observed=True,
        ),
    ]
    with Session(engine) as session:
        for ev in events:
            session.add(ev)
        for n in nodes:
            session.add(n)
        for edge in edges:
            session.add(edge)
        session.commit()


def _tool_names(events: list[dict]) -> list[str]:
    return [
        str(name)
        for e in events
        if e["type"] in ("tool.started", "tool.completed")
        and (name := e.get("tool_name"))
    ]


def main() -> int:
    init_db()
    with TestClient(app) as client:
        incident_id = _create_incident(client)
        _seed_data(client, incident_id)

        print(f"[mission] incident_id={incident_id}")
        print("[mission] starting adaptive AgentRouter investigation...")

        response = client.post(
            "/api/v1/agent/execute",
            json={
                "objective": f"Investigate {incident_id}",
                "incident_id": incident_id,
                "model_id": "agentrouter-claude-opus-4-8",
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        execution_id = data["execution_id"]
        print(f"[mission] execution_id={execution_id} status={data['status']}")

        deadline = time.time() + 180
        final_events: list[dict] = []
        after = 0
        while time.time() < deadline:
            response = client.get(
                f"/api/v1/agent/executions/{execution_id}/events?after={after}"
            )
            assert response.status_code == 200
            batch = response.json()["items"]
            if batch:
                final_events.extend(batch)
                after = batch[-1]["sequence"]
                for e in batch:
                    if e["type"] in ("agent.verification_passed", "agent.verification_failed"):
                        print(f"[mission] verification event: {e['type']}")
            response = client.get(f"/api/v1/agent/executions/{execution_id}")
            if response.json()["status"] in ("completed", "failed", "cancelled"):
                break
            time.sleep(2)

        response = client.get(f"/api/v1/agent/executions/{execution_id}")
        summary = response.json()
        duration = summary.get('duration_ms')
        print(f"[mission] final status={summary['status']} duration_ms={duration}")

        response = client.get(f"/api/v1/agent/executions/{execution_id}/context")
        context = response.json()
        print(f"[mission] findings={context.get('findings')}")

        tool_names = [n for n in _tool_names(final_events) if n]
        print(f"[mission] tools used: {tool_names}")

        if context.get("findings"):
            print("[mission] SUCCESS: AgentRouter produced a verified finding.")
            return 0
        print("[mission] WARNING: AgentRouter did not produce a finding in this run.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
