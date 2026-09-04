"""Unit tests for per-element causal reason rendering."""

from types import SimpleNamespace

import pytest

from anvaya.generations.builder import ArtifactBuilder
from anvaya.generations.manifests import ArtifactManifestStep


def _builder() -> ArtifactBuilder:
    """Return a builder instance usable for _element_reason testing."""
    generation = SimpleNamespace(
        project_id="proj-001",
        generation_id="gen-001",
        dataset_id=None,
        target_artifact_type="incidents",
    )
    return ArtifactBuilder(
        session=None,  # type: ignore[arg-type]
        generation=generation,  # type: ignore[arg-type]
        execution=None,  # type: ignore[arg-type]
        project=None,  # type: ignore[arg-type]
    )


def _step() -> ArtifactManifestStep:
    return ArtifactManifestStep(
        artifact_type="incidents",
        name="Full Incident List",
        purpose="Render the complete incident table.",
        building="Loading the full incident list into the workspace.",
    )


def test_causal_reason_references_severity_risk_and_rows() -> None:
    builder = _builder()
    item = {
        "incident_id": "INC-TEST-001",
        "title": "Test Incident",
        "severity": "critical",
        "risk_score": 0.84,
        "blast_radius_score": 0.32,
        "event_ids": ["EVT-ds-4818", "EVT-ds-4819", "EVT-ds-4820"],
        "severity_basis": {
            "severity_counts": {"critical": 3},
            "chosen": "critical",
            "event_count": 3,
        },
        "risk_basis": {
            "severity_factor": 1.0,
            "event_factor": 0.15,
            "weights": [0.6, 0.4],
            "risk_score": 0.84,
        },
        "blast_basis": {
            "origin_node": "10.0.0.5",
            "total_reachable": 12,
            "total_nodes": 50,
            "critical_exposed": 3,
            "critical_ratio": 0.1,
            "reach_ratio": 0.24,
            "max_depth": 2,
            "depth_weight": 0.4,
            "weights": [0.6, 0.3, 0.1],
        },
    }

    reason = builder._element_reason(_step(), item, 0, 3, "Test Incident")

    assert reason.startswith("Preparing Test Incident")
    assert "Classified critical" in reason
    assert "3 of 3 source events flagged critical severity" in reason
    assert "rows 4818–4820" in reason
    assert "risk 0.84 = severity 1.00×0.6 + event density 0.15×0.4" in reason
    assert "blast radius 0.32 from 10.0.0.5" in reason


def test_causal_reason_falls_back_when_no_basis() -> None:
    builder = _builder()
    item = {
        "incident_id": "INC-TEST-002",
        "title": "Plain Incident",
        "severity": "high",
    }

    reason = builder._element_reason(_step(), item, 1, 3, "Plain Incident")

    assert reason.startswith("Preparing Plain Incident")
    assert "severity high" in reason
    assert "Classified" not in reason
    assert "risk" not in reason
    assert "blast" not in reason


def test_row_reference_for_non_contiguous_events() -> None:
    builder = _builder()
    item = {
        "incident_id": "INC-TEST-003",
        "title": "Scattered Incident",
        "severity": "high",
        "risk_score": 0.7,
        "event_ids": ["EVT-ds-10", "EVT-ds-12", "EVT-ds-15"],
        "severity_basis": {
            "severity_counts": {"high": 3},
            "chosen": "high",
            "event_count": 3,
        },
        "risk_basis": {
            "severity_factor": 0.75,
            "event_factor": 0.15,
            "weights": [0.6, 0.4],
            "risk_score": 0.7,
        },
    }

    reason = builder._element_reason(_step(), item, 0, 1, "Scattered Incident")

    assert "Classified high" in reason
    assert "3 source events" in reason
    assert "rows 10" not in reason and "rows 15" not in reason


def test_row_reference_for_malformed_event_ids() -> None:
    builder = _builder()
    item = {
        "incident_id": "INC-TEST-004",
        "title": "Malformed Incident",
        "severity": "medium",
        "risk_score": 0.5,
        "event_ids": ["BAD-ID", "ALSO-BAD"],
        "severity_basis": {
            "severity_counts": {"medium": 2},
            "chosen": "medium",
            "event_count": 2,
        },
        "risk_basis": {
            "severity_factor": 0.5,
            "event_factor": 0.1,
            "weights": [0.6, 0.4],
            "risk_score": 0.5,
        },
    }

    reason = builder._element_reason(_step(), item, 0, 1, "Malformed Incident")

    assert "2 source events" in reason
    assert "rows" not in reason


def test_rank_text_variants() -> None:
    builder = _builder()
    item = {
        "incident_id": "INC-TEST-005",
        "title": "Solo Incident",
        "severity": "low",
        "severity_basis": {
            "severity_counts": {"low": 1},
            "chosen": "low",
            "event_count": 1,
        },
    }

    assert "highest priority" in builder._element_reason(_step(), item, 0, 3, "Solo")
    assert "final entry" in builder._element_reason(_step(), item, 2, 3, "Solo")
    assert "rank 2" in builder._element_reason(_step(), item, 1, 3, "Solo")


def test_orbit_risk_basis_reason() -> None:
    builder = _builder()
    item = {
        "orbit_id": "ORB-10.0.0.5-10.0.0.10",
        "source": "10.0.0.5",
        "target": "10.0.0.10",
        "risk_score": 0.92,
        "risk_basis": {
            "interaction_strength": 0.8,
            "related_incident_count": 1,
            "incident_weight": 0.1,
            "risk_score": 0.92,
        },
    }

    reason = builder._element_reason(_step(), item, 0, 1, "ORB-10.0.0.5-10.0.0.10")
    assert "risk 0.92 = interaction strength 0.80 × (1 + 1 incidents × 0.1)" in reason
