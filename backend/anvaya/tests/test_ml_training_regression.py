"""Regression tests for ML training label and contamination correctness.

These tests construct deterministic synthetic input directly rather than using
the full pytest fixtures from the top-level test suite, matching the style of
backend/anvaya/tests/test_world_incident_basis.py.
"""

import numpy as np
from sqlmodel import Session, SQLModel, create_engine

import anvaya.models  # noqa: F401  registers all SQLModel tables
from anvaya.ml.alertness import AlertnessEngine
from anvaya.simulator.generator import TelemetryGenerator
from anvaya.simulator.scenarios import get_all_scenarios, get_attack_scenarios
from anvaya.whatif import WhatIfEngine


def _in_memory_session() -> Session:
    """Return a fresh in-memory SQLite session for model persistence tests."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _dummy_events(n: int, positive_indices: set[int]) -> list[dict]:
    """Return n dummy event dicts with an anomalous flag on positive_indices."""
    events = []
    for i in range(n):
        events.append(
            {
                "event_type": "process_create",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "process": "chrome.exe",
                "is_off_hours": i in positive_indices,
                "is_new_device": False,
                "is_privilege_escalation": False,
                "is_anomalous_process": i in positive_indices,
                "is_unusual_network": False,
                "is_lateral_movement": False,
            }
        )
    return events


def test_is_attack_matches_ground_truth_label() -> None:
    """Generated attack events are labeled attack only when ground truth says so.

    A non-normal `ground_truth_label` (including a literal 'suspicious' label) is
    treated as attack-like.  This matches the existing split in
    backend/anvaya/world_architect.py and backend/anvaya/world.py, which count
    suspicious telemetry as a subset of attack-like telemetry, not as normal.
    Events without an explicit ground-truth entry are normal setup rows.
    """
    gen = TelemetryGenerator(seed=42)

    for scenario in get_all_scenarios():
        events = gen.generate_for_scenario(scenario)
        for evt in events:
            if evt["ground_truth_label"] == "normal":
                assert evt["is_attack"] is False, (
                    f"{scenario.scenario_id} {evt['event_id']}: "
                    "ground_truth_label=normal but is_attack=True"
                )
            else:
                assert evt["is_attack"] is True, (
                    f"{scenario.scenario_id} {evt['event_id']}: "
                    f"ground_truth_label={evt['ground_truth_label']} but is_attack=False"
                )
                # Suspicious events are a distinct category that still belongs to
                # the attack-like class, mirroring world_architect.py's split.
                if evt["ground_truth_label"] == "suspicious":
                    assert evt["is_attack"] is True

    # Attack scenarios must still contain at least one true attack event.
    for scenario in get_attack_scenarios():
        events = gen.generate_for_scenario(scenario)
        assert any(evt["is_attack"] for evt in events)


def test_alertness_engine_recall_nonzero() -> None:
    """AlertnessEngine (Isolation Forest) must find some real attack signal."""
    gen = TelemetryGenerator(seed=42)
    dataset = gen.generate_dataset()
    all_events = (
        dataset["events"]["train"]
        + dataset["events"]["validation"]
        + dataset["events"]["test"]
    )

    engine = AlertnessEngine(session=None)
    metrics = engine.train(all_events)

    assert metrics["recall"] > 0.0
    assert metrics["f1_score"] > 0.0
    assert 0.01 <= metrics["contamination_used"] <= 0.5


def test_whatif_engine_recall_nonzero() -> None:
    """WhatIfEngine (Logistic Regression) must learn a non-trivial signal."""
    gen = TelemetryGenerator(seed=42)
    dataset = gen.generate_dataset()
    all_events = (
        dataset["events"]["train"]
        + dataset["events"]["validation"]
        + dataset["events"]["test"]
    )

    session = _in_memory_session()
    engine = WhatIfEngine(session=session)
    metrics = engine.train(all_events)

    assert metrics["recall"] > 0.0
    assert metrics["precision"] > 0.0
    assert metrics["f1_score"] > 0.0


def test_contamination_scales_with_attack_rate() -> None:
    """AlertnessEngine contamination tracks the attack prevalence in labels."""
    engine = AlertnessEngine(session=None)

    # 5% attack prevalence -> contamination should be small.
    events_5pct = _dummy_events(100, set(range(95, 100)))
    labels_5pct = np.array([0] * 95 + [1] * 5)
    metrics_5pct = engine.train(events_5pct, labels=labels_5pct)
    contamination_5pct = metrics_5pct["contamination_used"]

    # 50% attack prevalence -> contamination should be much larger.
    events_50pct = _dummy_events(100, set(range(50, 100)))
    labels_50pct = np.array([0] * 50 + [1] * 50)
    metrics_50pct = engine.train(events_50pct, labels=labels_50pct)
    contamination_50pct = metrics_50pct["contamination_used"]

    assert contamination_5pct < contamination_50pct
    assert 0.01 <= contamination_5pct <= 0.5
    assert 0.01 <= contamination_50pct <= 0.5
