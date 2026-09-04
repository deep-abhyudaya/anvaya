"""Tests for the ANVAYA World Architect pipeline."""

from __future__ import annotations

from anvaya.world_architect import WorldArchitect


def test_world_build_smoke(db_session):
    """End-to-end smoke test: build a minimal world and verify the manifest."""
    architect = WorldArchitect(db_session)
    manifest = architect.build(
        {
            "seed": 123,
            "normal_count": 2,
            "suspicious_count": 1,
            "attack_count": 2,
            "include_self_correction": False,
        }
    )

    assert manifest["incidents"] > 0
    assert manifest["sealed_incidents"] == manifest["incidents"]
    assert manifest["audit_chain_valid"] is True
    assert manifest["total_events"] > 0
    assert manifest["assets"] > 0
    assert manifest["relationships"] > 0
    assert manifest["graph_nodes"] > 0
    assert manifest["graph_edges"] > 0
    assert manifest["blast_radius_results"] > 0
    assert manifest["counterfactuals"] > 0
    assert manifest["model_versions"] > 0


def test_world_build_includes_self_correction(db_session):
    """The full pipeline should produce a caught self-correction replay."""
    architect = WorldArchitect(db_session)
    manifest = architect.build(
        {
            "seed": 456,
            "normal_count": 1,
            "suspicious_count": 1,
            "attack_count": 0,
            "include_self_correction": True,
        }
    )

    assert manifest["incidents"] == 1
    assert manifest["sealed_incidents"] == 1
    assert manifest["audit_chain_valid"] is True
    assert manifest["detection_rules"] >= 1
    assert manifest["replay_runs"] >= 1
