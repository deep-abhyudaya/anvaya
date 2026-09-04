"""Tests for SentinelBacktracker self-correction engine."""

from anvaya.demo.orchestrator import DemoOrchestrator
from anvaya.models.enums import IncidentStatus


class TestSelfCorrection:
    def test_full_demo_succeeds(self, db_session):
        """The complete self-correction demo must succeed."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_full_demo()

        assert result["success"] is True
        assert result["final_status"] if "final_status" in result else True
        steps = result.get("steps", [])
        step_names = [s["step"] for s in steps]
        assert "self_correction" in step_names
        assert "seal" in step_names
        assert "verify_audit" in step_names

    def test_pre_patch_detection_misses(self, db_session):
        """Pre-patch detection must miss the self-correction scenario."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_full_demo()
        steps = result.get("steps", [])
        pre_patch = [s for s in steps if s["step"] == "pre_patch_detection"][0]
        assert pre_patch["detected"] is False
        assert pre_patch["result"] == "MISS"

    def test_post_patch_replay_catches(self, db_session):
        """Post-patch replay must catch the identical attack."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_full_demo()
        sc_step = [s for s in result["steps"] if s["step"] == "self_correction"][0]
        sc_result = sc_step["result"]
        assert sc_result["final_status"] == "caught"
        assert sc_result["success"] is True

    def test_incident_is_sealed(self, db_session):
        """Incident must be sealed after the demo."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_full_demo()
        from anvaya.models.incident import Incident
        from sqlmodel import select

        incident_id = result.get("incident_id")
        incident = db_session.exec(
            select(Incident).where(Incident.incident_id == incident_id)
        ).first()
        assert incident is not None
        assert incident.status == IncidentStatus.SEALED
        assert incident.sealed_at is not None

    def test_audit_chain_is_valid_after_demo(self, db_session):
        """Audit chain must be valid after the complete demo."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_full_demo()
        verify_step = [s for s in result["steps"] if s["step"] == "verify_audit"][0]
        assert verify_step["chain_valid"] is True
        assert verify_step["audit_records"] > 0

    def test_replay_is_identical(self, db_session):
        """The replay must be identical (same scenario, same seed)."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_full_demo()
        from anvaya.models.replay import ReplayRun
        from sqlmodel import select

        incident_id = result.get("incident_id")
        replay = db_session.exec(
            select(ReplayRun).where(ReplayRun.incident_id == incident_id)
        ).first()
        assert replay is not None
        assert replay.is_identical is True
        assert replay.pre_patch_detected is False
        assert replay.post_patch_detected is True
