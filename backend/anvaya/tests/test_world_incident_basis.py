"""Unit tests for causal basis computation in the canonical world model."""

import pandas as pd

from anvaya.dataset_profile import build_dataset_profile
from anvaya.world import build_world_model


def _make_incident_df() -> pd.DataFrame:
    """Return a small, deterministic DataFrame that clusters into one incident."""
    rows = []
    for i in range(9):
        rows.append(
            {
                "timestamp": f"2026-01-01T08:0{i}:00",
                "source_ip": "10.0.0.5",
                "destination_ip": "10.0.0.10",
                "host": "HOST-01",
                "user": "eve",
                "process": "ps.exe",
                "command": f"cmd-{i}",
                "action": "network",
                "event_type": "lateral_movement",
                "severity": "critical" if i < 7 else "high",
                "attack_family": "lateral_movement",
                "label": "attack",
            }
        )
    rows.append(
        {
            "timestamp": "2026-01-01T08:10:00",
            "source_ip": "10.0.0.1",
            "destination_ip": "10.0.0.2",
            "host": "HOST-00",
            "user": "alice",
            "process": "ls.exe",
            "command": "ls",
            "action": "normal",
            "event_type": "process",
            "severity": "low",
            "attack_family": "normal",
            "label": "normal",
        }
    )
    return pd.DataFrame(rows)


def test_incident_basis_fields_are_populated() -> None:
    df = _make_incident_df()
    profile = build_dataset_profile(df, "ds-test-001")
    world = build_world_model(df, profile, "proj-001", "ds-test-001", "gen-001")

    assert len(world.incidents) >= 1
    inc = world.incidents[0]

    assert inc.severity_basis
    assert inc.risk_basis
    assert inc.blast_basis

    assert inc.severity_basis["chosen"] == inc.severity
    assert inc.severity_basis["severity_counts"]["critical"] == 7
    assert inc.severity_basis["severity_counts"]["high"] == 2
    assert inc.severity_basis["event_count"] == 9

    assert inc.risk_basis["severity_factor"] == 1.0
    assert inc.risk_basis["event_factor"] == 0.45
    assert inc.risk_basis["weights"] == [0.6, 0.4]
    assert round(
        inc.risk_basis["severity_factor"] * 0.6
        + inc.risk_basis["event_factor"] * 0.4,
        4,
    ) == inc.risk_score

    assert "total_reachable" in inc.blast_basis
    assert "total_nodes" in inc.blast_basis
    assert "critical_exposed" in inc.blast_basis
    assert "weights" in inc.blast_basis
    assert inc.blast_basis.get("origin_node")


def test_incident_basis_is_consistent_with_scores() -> None:
    df = _make_incident_df()
    profile = build_dataset_profile(df, "ds-test-001")
    world = build_world_model(df, profile, "proj-001", "ds-test-001", "gen-001")

    for inc in world.incidents:
        assert inc.severity in inc.severity_basis["severity_counts"]
        assert (
            inc.severity_basis["severity_counts"][inc.severity]
            == max(inc.severity_basis["severity_counts"].values())
        )

        rb = inc.risk_basis
        expected_risk = round(rb["severity_factor"] * 0.6 + rb["event_factor"] * 0.4, 4)
        assert inc.risk_score == expected_risk

        bb = inc.blast_basis
        if bb.get("total_nodes", 0) > 0:
            expected_blast = round(
                bb["critical_ratio"] * 0.6
                + bb["reach_ratio"] * 0.3
                + bb["depth_weight"] * 0.1,
                4,
            )
            assert inc.blast_radius_score == expected_blast


def test_basis_serialization_includes_event_ids() -> None:
    df = _make_incident_df()
    profile = build_dataset_profile(df, "ds-test-001")
    world = build_world_model(df, profile, "proj-001", "ds-test-001", "gen-001")

    for inc in world.incidents:
        assert len(inc.event_ids) == inc.severity_basis["event_count"]
        for eid in inc.event_ids:
            assert eid.startswith("EVT-")
            assert eid.split("-")[-1].isdigit()


def _make_varied_incident_df() -> pd.DataFrame:
    """Return a DataFrame where host/user repeat but source/destination do not.

    Each host/user/family bucket has a dominant severity so the resulting
    incidents cover all four severity rungs and a spread of risk scores.
    """
    groups = [
        # (host, user, family, count, dominant severity, other severities)
        ("HOST-01", "eve", "lateral_movement", 8, "low", ["low", "low", "medium", "high"]),
        ("HOST-01", "bob", "lateral_movement", 4, "medium", ["medium", "low", "high"]),
        ("HOST-02", "bob", "credential_abuse", 4, "high", ["high", "low", "medium"]),
        ("HOST-02", "alice", "credential_abuse", 4, "critical", ["critical", "high", "medium"]),
    ]
    rows = []
    i = 0
    for host, user, family, count, dominant, others in groups:
        severities = [dominant] + others[: count - 1]
        for sev in severities:
            rows.append(
                {
                    "timestamp": f"2026-01-01T08:{i:02d}:00",
                    "source_ip": f"10.{i}.0.1",
                    "destination_ip": f"10.{i}.1.1",
                    "host": host,
                    "user": user,
                    "process": "ps.exe",
                    "command": f"cmd-{i}",
                    "action": "network",
                    "event_type": "lateral_movement",
                    "severity": sev,
                    "attack_family": family,
                    "label": "normal",
                }
            )
            i += 1
    return pd.DataFrame(rows)


def test_low_and_medium_events_become_incidents() -> None:
    df = _make_varied_incident_df()
    profile = build_dataset_profile(df, "ds-test-002")
    world = build_world_model(df, profile, "proj-002", "ds-test-002", "gen-002")

    severities = {inc.severity for inc in world.incidents}
    assert "low" in severities
    assert "medium" in severities


def test_risk_scores_show_real_variation() -> None:
    df = _make_varied_incident_df()
    profile = build_dataset_profile(df, "ds-test-002")
    world = build_world_model(df, profile, "proj-002", "ds-test-002", "gen-002")

    scores = [round(inc.risk_score, 4) for inc in world.incidents]
    unique_scores = set(scores)
    assert len(unique_scores) > 2, f"risk scores are degenerate: {unique_scores}"
    assert any(s > 0.62 for s in scores), "no large-group high-severity incident produced"
    assert any(s < 0.47 for s in scores), "no low-severity / small-group incident produced"
