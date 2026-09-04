"""Tests for incident state machine and lifecycle."""

import pytest
from anvaya.models.enums import IncidentStatus, SelfCorrectionStatus
from anvaya.models.incident import Incident


class TestIncidentLifecycle:
    def test_incident_starts_as_detected(self):
        incident = Incident(incident_id="INC-001", title="Test")
        assert incident.status == IncidentStatus.DETECTED

    def test_valid_lifecycle_transition(self):
        incident = Incident(incident_id="INC-001", title="Test")
        incident.transition_to(IncidentStatus.ANALYZED)
        assert incident.status == IncidentStatus.ANALYZED

    def test_full_lifecycle(self):
        incident = Incident(incident_id="INC-001", title="Test")
        incident.transition_to(IncidentStatus.ANALYZED)
        incident.transition_to(IncidentStatus.SIMULATED)
        incident.transition_to(IncidentStatus.EXPLAINED)
        incident.transition_to(IncidentStatus.SEALED)
        assert incident.status == IncidentStatus.SEALED
        assert incident.sealed_at is not None
        assert incident.is_sealed()

    def test_invalid_lifecycle_transition(self):
        incident = Incident(incident_id="INC-001", title="Test")
        with pytest.raises(ValueError, match="Invalid lifecycle transition"):
            incident.transition_to(IncidentStatus.SEALED)

    def test_detected_can_transition_to_active(self):
        incident = Incident(incident_id="INC-001", title="Test")
        incident.transition_to(IncidentStatus.ACTIVE)
        assert incident.status == IncidentStatus.ACTIVE

    def test_active_can_transition_to_analyzed(self):
        incident = Incident(incident_id="INC-001", title="Test")
        incident.transition_to(IncidentStatus.ACTIVE)
        incident.transition_to(IncidentStatus.ANALYZED)
        assert incident.status == IncidentStatus.ANALYZED

    def test_active_cannot_skip_to_sealed(self):
        incident = Incident(incident_id="INC-001", title="Test")
        incident.transition_to(IncidentStatus.ACTIVE)
        with pytest.raises(ValueError, match="Invalid lifecycle transition"):
            incident.transition_to(IncidentStatus.SEALED)

    def test_cannot_transition_from_sealed(self):
        incident = Incident(incident_id="INC-001", title="Test")
        incident.transition_to(IncidentStatus.ANALYZED)
        incident.transition_to(IncidentStatus.SIMULATED)
        incident.transition_to(IncidentStatus.EXPLAINED)
        incident.transition_to(IncidentStatus.SEALED)
        with pytest.raises(ValueError):
            incident.transition_to(IncidentStatus.DETECTED)


class TestSelfCorrectionStateMachine:
    def test_starts_as_none(self):
        incident = Incident(incident_id="INC-001", title="Test")
        assert incident.self_correction_status == SelfCorrectionStatus.NONE

    def test_valid_self_correction_flow(self):
        incident = Incident(incident_id="INC-001", title="Test")
        incident.self_correct_to(SelfCorrectionStatus.MISS)
        incident.self_correct_to(SelfCorrectionStatus.GROUND_TRUTH_CONFIRMED)
        incident.self_correct_to(SelfCorrectionStatus.BACKTRACKING)
        incident.self_correct_to(SelfCorrectionStatus.EVIDENCE_IDENTIFIED)
        incident.self_correct_to(SelfCorrectionStatus.RULE_PROPOSED)
        incident.self_correct_to(SelfCorrectionStatus.RULE_VALIDATED)
        incident.self_correct_to(SelfCorrectionStatus.REPLAYING)
        incident.self_correct_to(SelfCorrectionStatus.CAUGHT)
        assert incident.self_correction_status == SelfCorrectionStatus.CAUGHT

    def test_invalid_self_correction_transition(self):
        incident = Incident(incident_id="INC-001", title="Test")
        with pytest.raises(ValueError, match="Invalid self-correction transition"):
            incident.self_correct_to(SelfCorrectionStatus.CAUGHT)

    def test_still_missed_can_retry(self):
        incident = Incident(incident_id="INC-001", title="Test")
        incident.self_correct_to(SelfCorrectionStatus.MISS)
        incident.self_correct_to(SelfCorrectionStatus.GROUND_TRUTH_CONFIRMED)
        incident.self_correct_to(SelfCorrectionStatus.BACKTRACKING)
        incident.self_correct_to(SelfCorrectionStatus.EVIDENCE_IDENTIFIED)
        incident.self_correct_to(SelfCorrectionStatus.RULE_PROPOSED)
        incident.self_correct_to(SelfCorrectionStatus.STILL_MISSED)
        incident.self_correct_to(SelfCorrectionStatus.BACKTRACKING)
        assert incident.self_correction_status == SelfCorrectionStatus.BACKTRACKING
