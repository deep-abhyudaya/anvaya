"""Tests for BlastScope graph engine."""

from anvaya.blastscope import BlastScopeEngine
from anvaya.models.asset import Asset, AssetRelationship
from anvaya.models.enums import AssetType
from anvaya.models.incident import Incident


class TestBlastScope:
    def test_blastscope_runs_on_incident(self, db_session):
        incident = Incident(
            incident_id="INC-TEST-001",
            title="Test Blast",
            host="WS-001",
            scenario_id="TEST-001",
        )
        db_session.add(incident)

        ws = Asset(
            asset_id="WS-001", name="Workstation 1", asset_type=AssetType.HOST, hostname="WS-001"
        )
        srv = Asset(
            asset_id="SRV-DB01",
            name="DB Server",
            asset_type=AssetType.DATABASE,
            is_critical=True,
            hostname="SRV-DB01",
        )
        db_session.add(ws)
        db_session.add(srv)

        rel = AssetRelationship(
            source_asset_id="WS-001",
            target_asset_id="SRV-DB01",
            relationship_type="network",
            is_observed=True,
        )
        db_session.add(rel)
        db_session.commit()

        engine = BlastScopeEngine(db_session)
        result = engine.run("INC-TEST-001")

        assert result["incident_id"] == "INC-TEST-001"
        assert result["total_reachable"] >= 1
        assert "impact_score" in result

    def test_blastscope_persists_result(self, db_session):
        incident = Incident(
            incident_id="INC-TEST-002",
            title="Test Persist",
            host="WS-002",
            scenario_id="TEST-002",
        )
        db_session.add(incident)
        db_session.commit()

        engine = BlastScopeEngine(db_session)
        engine.run("INC-TEST-002")

        result = engine.get_result("INC-TEST-002")
        assert "incident_id" in result
        assert result["incident_id"] == "INC-TEST-002"

    def test_blastscope_updates_incident_score(self, db_session):
        incident = Incident(
            incident_id="INC-TEST-003",
            title="Test Score",
            host="WS-003",
            scenario_id="TEST-003",
        )
        db_session.add(incident)
        db_session.commit()

        engine = BlastScopeEngine(db_session)
        engine.run("INC-TEST-003")

        from sqlmodel import select

        updated = db_session.exec(
            select(Incident).where(Incident.incident_id == "INC-TEST-003")
        ).first()
        assert updated.blast_radius_score > 0
