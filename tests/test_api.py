"""Tests for FastAPI endpoints."""

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

    importlib.reload(anvaya.config)
    import anvaya.db

    importlib.reload(anvaya.db)
    from anvaya.db import init_db
    from anvaya.main import app

    init_db()
    with TestClient(app) as c:
        yield c
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass


class TestHealthCheck:
    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "anvaya"


class TestIncidentsAPI:
    def test_list_incidents_empty(self, client):
        response = client.get("/api/v1/incidents")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] == 0

    def test_create_and_get_incident(self, client):
        response = client.post(
            "/api/v1/incidents",
            json={
                "title": "Test Incident",
                "severity": "high",
                "attack_family": "credential_abuse",
            },
        )
        assert response.status_code == 200
        incident = response.json()
        assert incident["title"] == "Test Incident"
        incident_id = incident["incident_id"]

        response = client.get(f"/api/v1/incidents/{incident_id}")
        assert response.status_code == 200
        assert response.json()["incident_id"] == incident_id

    def test_transition_incident(self, client):
        response = client.post("/api/v1/incidents", json={"title": "Test"})
        incident_id = response.json()["incident_id"]

        response = client.post(
            f"/api/v1/incidents/{incident_id}/transition", params={"new_status": "analyzed"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "analyzed"

    def test_invalid_transition(self, client):
        response = client.post("/api/v1/incidents", json={"title": "Test"})
        incident_id = response.json()["incident_id"]

        response = client.post(
            f"/api/v1/incidents/{incident_id}/transition", params={"new_status": "sealed"}
        )
        assert response.status_code == 400


class TestMetricsAPI:
    def test_metrics_endpoint(self, client):
        response = client.get("/api/v1/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "total_incidents" in data
        assert "status_counts" in data


class TestAuditAPI:
    def test_verify_empty_chain(self, client):
        response = client.get("/api/v1/audit/verify")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True


class TestRouteContract:
    """Regression tests for frontend/backend route contract alignment."""

    def test_health_only_at_root(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

        response = client.get("/api/v1/health")
        assert response.status_code == 404

    def test_graph_static_routes_not_shadowed(self, client):
        response = client.get("/api/v1/graph/segments")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data and "nodes" in data

        response = client.get("/api/v1/graph/reachability")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_blastscope_gallery_not_shadowed(self, client):
        response = client.get("/api/v1/blastscope/gallery")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    def test_incidents_include_impact_gallery_fields(self, client):
        response = client.post(
            "/api/v1/incidents",
            json={
                "title": "Test",
                "severity": "high",
                "attack_family": "lateral_movement",
            },
        )
        assert response.status_code == 200

        response = client.get("/api/v1/incidents")
        assert response.status_code == 200
        data = response.json()
        assert data["items"]
        item = data["items"][0]
        assert "blastRadius" in item
        assert "hops" in item

    def test_trophies_match_frontend_contract(self, client):
        response = client.post(
            "/api/v1/incidents",
            json={
                "title": "Test",
                "severity": "high",
                "attack_family": "lateral_movement",
            },
        )
        assert response.status_code == 200
        incident_id = response.json()["incident_id"]

        client.post(
            f"/api/v1/incidents/{incident_id}/transition", params={"new_status": "analyzed"}
        )
        client.post(
            f"/api/v1/incidents/{incident_id}/transition", params={"new_status": "simulated"}
        )
        client.post(
            f"/api/v1/incidents/{incident_id}/transition", params={"new_status": "explained"}
        )
        client.post(f"/api/v1/incidents/{incident_id}/transition", params={"new_status": "sealed"})

        response = client.get("/api/v1/metrics/trophies")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        if data["items"]:
            trophy = data["items"][0]
            assert trophy["id"] == incident_id
            assert "engines" in trophy
            assert set(trophy["engines"].keys()) == {"sentinel", "blastscope", "whatif", "ledger"}
            assert "sealedAt" in trophy
            assert "started" in trophy
            assert "blastRadius" in trophy
            assert "hops" in trophy

    def test_audit_sealed_records_enriched(self, client):
        response = client.post(
            "/api/v1/incidents",
            json={
                "title": "Test",
                "severity": "high",
                "attack_family": "lateral_movement",
            },
        )
        assert response.status_code == 200
        incident_id = response.json()["incident_id"]

        client.post(
            f"/api/v1/incidents/{incident_id}/transition", params={"new_status": "analyzed"}
        )
        client.post(
            f"/api/v1/incidents/{incident_id}/transition", params={"new_status": "simulated"}
        )
        client.post(
            f"/api/v1/incidents/{incident_id}/transition", params={"new_status": "explained"}
        )
        client.post(f"/api/v1/incidents/{incident_id}/transition", params={"new_status": "sealed"})

        response = client.get("/api/v1/audit")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        if data["items"]:
            record = data["items"][0]
            assert "controls_satisfied" in record
            assert "engines" in record
            assert "blast_radius" in record
