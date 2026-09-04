"""Tests for the multi-incident batch demo."""

from __future__ import annotations

from typing import Any

from anvaya.demo.orchestrator import DemoOrchestrator
from anvaya.models.audit import AuditRecord
from anvaya.models.incident import Incident
from anvaya.models.replay import ReplayRun
from sqlmodel import select


def _incident_status(incident: dict[str, Any]) -> str:
    """Return the narratable final status for an incident result."""
    steps = {s.get("step"): s for s in incident.get("steps", [])}
    pre = steps.get("pre_patch_detection", {})
    sc = steps.get("self_correction", {}).get("result") or {}
    if pre.get("detected"):
        return "caught_pre_patch"
    if sc.get("final_status") == "caught":
        return "missed_then_corrected"
    return sc.get("final_status", "unknown")


class TestDemoBatch:
    def test_batch_creates_requested_incidents(self, db_session):
        """The batch demo creates the requested number of real Incident records."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_batch_demo(count=5)

        assert result["success"] is True
        assert len(result["incidents"]) == 5

        incident_ids = {inc["incident_id"] for inc in result["incidents"]}
        db_incidents = db_session.exec(select(Incident)).all()
        assert len(db_incidents) >= 5
        for inc_id in incident_ids:
            assert any(i.incident_id == inc_id for i in db_incidents)

    def test_batch_summary_counts_sum_to_total(self, db_session):
        """The summary caught/missed/failed counts must sum to the total."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_batch_demo(count=5)

        summary = result.get("summary", {})
        total = summary.get("total", 0)
        caught = summary.get("caught_immediately", 0)
        missed_corrected = summary.get("missed_then_corrected", 0)
        failed = summary.get("failed_self_correction", 0)

        assert total == 5
        assert caught + missed_corrected + failed == total

    def test_batch_incidents_have_audit_chains(self, db_session):
        """Every batch incident must have a valid audit chain."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_batch_demo(count=5)

        for incident in result["incidents"]:
            inc_id = incident["incident_id"]
            audit_records = db_session.exec(
                select(AuditRecord).where(AuditRecord.incident_id == inc_id)
            ).all()
            assert len(audit_records) > 0, f"Incident {inc_id} has no audit records"

            verify_step = next(
                (s for s in incident.get("steps", []) if s.get("step") == "verify_audit"),
                {},
            )
            assert verify_step.get("chain_valid") is True

    def test_batch_incidents_have_replays(self, db_session):
        """Missed-then-corrected incidents must have replay runs recorded."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_batch_demo(count=5)

        for incident in result["incidents"]:
            status = _incident_status(incident)
            if status == "missed_then_corrected":
                replays = db_session.exec(
                    select(ReplayRun).where(ReplayRun.incident_id == incident["incident_id"])
                ).all()
                assert len(replays) > 0
                assert any(r.post_patch_detected for r in replays)

    def test_batch_uses_only_attack_scenarios(self, db_session):
        """The default batch uses only the four ATK-* scenario templates."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_batch_demo(count=8)

        summary = result.get("summary", {})
        templates = summary.get("templates_used", [])
        assert all(s.startswith("ATK-") for s in templates)
        assert len(templates) <= 4

    def test_batch_filtered_by_scenario_id(self, db_session):
        """The scenarios option can restrict the batch to a single template."""
        orchestrator = DemoOrchestrator(db_session)
        result = orchestrator.run_batch_demo(count=3, scenarios="ATK-001")

        assert result["success"] is True
        assert len(result["incidents"]) == 3
        for incident in result["incidents"]:
            assert incident["scenario_id"] == "ATK-001"
