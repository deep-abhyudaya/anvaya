"""Unit tests for per-step live thinking text and new selectors."""

from types import SimpleNamespace

import pytest

from anvaya.generations.builder import ArtifactBuilder
from anvaya.generations.manifests import INCIDENTS_MANIFEST, ArtifactManifestStep


def _builder() -> ArtifactBuilder:
    """Return a builder instance usable for _step_thinking_text testing."""
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


def _step(artifact_type: str) -> ArtifactManifestStep:
    """Find the step in INCIDENTS_MANIFEST by artifact_type."""
    for step in INCIDENTS_MANIFEST:
        if step.artifact_type == artifact_type:
            return step
    raise ValueError(f"No step for {artifact_type}")


def _incidents() -> list[dict]:
    return [
        {
            "incident_id": "INC-1",
            "severity": "critical",
            "attack_family": "lateral_movement",
            "host": "10.0.0.5",
            "user": "alice",
        },
        {
            "incident_id": "INC-2",
            "severity": "high",
            "attack_family": "lateral_movement",
            "host": "10.0.0.6",
            "user": "bob",
        },
        {
            "incident_id": "INC-3",
            "severity": "critical",
            "attack_family": "exfiltration",
            "host": "10.0.0.5",
            "user": "alice",
        },
    ]


def _payload() -> dict:
    return {
        "incidents": _incidents(),
        "incident_count": 3,
        "row_count": 120,
    }



def test_severity_model_selector() -> None:
    step = _step("severity_model")
    assert step.selector is not None
    delta = step.selector(_payload(), 1)
    assert delta == {"severity_distribution": {"critical": 2, "high": 1, "medium": 0, "low": 0}}


def test_attack_families_selector() -> None:
    step = _step("attack_families")
    assert step.selector is not None
    delta = step.selector(_payload(), 1)
    assert delta == {"family_counts": {"exfiltration": 1, "lateral_movement": 2}}


def test_hosts_selector() -> None:
    step = _step("hosts")
    assert step.selector is not None
    delta = step.selector(_payload(), 1)
    assert delta["host_count"] == 2
    assert set(delta["top_hosts"]) == {"10.0.0.5", "10.0.0.6"}
    assert delta["top_hosts"][0] == "10.0.0.5"


def test_users_selector() -> None:
    step = _step("users")
    assert step.selector is not None
    delta = step.selector(_payload(), 1)
    assert delta["user_count"] == 2
    assert set(delta["top_users"]) == {"alice", "bob"}
    assert delta["top_users"][0] == "alice"



def test_foundation_thinking_text() -> None:
    builder = _builder()
    step = _step("foundation")
    text = builder._step_thinking_text(step, 0, _payload())
    assert text is not None
    assert "3 incidents" in text
    assert "120 dataset rows" in text


def test_severity_model_thinking_text() -> None:
    builder = _builder()
    step = _step("severity_model")
    text = builder._step_thinking_text(step, 1, _payload())
    assert text is not None
    assert "Classifying severity across 3 incidents" in text
    assert "2 critical" in text
    assert "1 high" in text


def test_attack_families_thinking_text() -> None:
    builder = _builder()
    step = _step("attack_families")
    text = builder._step_thinking_text(step, 1, _payload())
    assert text is not None
    assert "3 incidents" in text
    assert "2 lateral_movement" in text
    assert "1 exfiltration" in text


def test_hosts_thinking_text() -> None:
    builder = _builder()
    step = _step("hosts")
    text = builder._step_thinking_text(step, 1, _payload())
    assert text is not None
    assert "2 affected hosts" in text
    assert "10.0.0.5" in text


def test_users_thinking_text() -> None:
    builder = _builder()
    step = _step("users")
    text = builder._step_thinking_text(step, 1, _payload())
    assert text is not None
    assert "2 involved users" in text
    assert "alice" in text


def test_blast_thinking_text() -> None:
    builder = _builder()
    step = _step("blast")
    text = builder._step_thinking_text(step, 1, _payload())
    assert text is not None
    assert "3 incidents" in text
    assert "blast-radius" in text


def test_risk_thinking_text() -> None:
    builder = _builder()
    step = _step("risk")
    text = builder._step_thinking_text(step, 1, _payload())
    assert text is not None
    assert "3 incidents" in text
    assert "risk score" in text


def test_incidents_thinking_text() -> None:
    builder = _builder()
    step = _step("incidents")
    text = builder._step_thinking_text(step, 1, _payload())
    assert text is not None
    assert "3 incidents" in text


def test_no_selector_falls_back_to_static() -> None:
    """Steps without selectors (or no data) return None so the caller keeps static text."""
    builder = _builder()
    step = ArtifactManifestStep(
        artifact_type="stats",
        name="Incident Statistics",
        purpose="Surface status counts.",
        building="Aggregating status counts.",
    )
    assert builder._step_thinking_text(step, 0, _payload()) is None


def test_thinking_pause_scales_with_length() -> None:
    from anvaya.generations.builder import (
        STEP_THINK_PAUSE_BASE,
        STEP_THINK_PAUSE_MAX,
    )

    builder = _builder()
    short = builder._step_think_pause("short")
    none_text = builder._step_think_pause(None)
    long = builder._step_think_pause("x" * 200)
    assert none_text == pytest.approx(STEP_THINK_PAUSE_BASE, 0.05)
    assert short == pytest.approx(STEP_THINK_PAUSE_BASE + len("short") / 40.0, 0.05)
    assert STEP_THINK_PAUSE_BASE < long <= STEP_THINK_PAUSE_MAX
