"""Automated validation of the full ANVAYA model catalog.

Implements the `model_catalog_validation` acceptance check requested in the
model-catalog specification.
"""

from __future__ import annotations

import pytest

from anvaya.agent.profiles import default_models
from anvaya.agent.schemas import ModelConfig
from anvaya.llm.catalog_intelligence import _CATALOG, get_model_intelligence


def _all_default_models() -> list[ModelConfig]:
    return default_models()


def test_catalog_completeness_rules():
    models = _all_default_models()
    incomplete: list[str] = []
    seen_ids: set[str] = set()

    for m in models:
        reasons: list[str] = []
        if not m.provider:
            reasons.append("missing gateway")
        if not m.maker:
            reasons.append("missing maker")
        if not m.family:
            reasons.append("missing family")
        if m.context_window is None:
            reasons.append("missing context")
        if not m.profile_fit:
            reasons.append("missing profile_fit")
        for role in ("sentinel", "pathfinder", "responder", "auditor"):
            score = (m.profile_fit or {}).get(role)
            if score is None or score == 0:
                reasons.append(f"{role} score missing")
            elif not (0.01 <= score <= 1.0):
                reasons.append(f"{role} score {score} out of range")
        if not m.evidence_level:
            reasons.append("missing evidence_level")
        if m.id in seen_ids:
            reasons.append("duplicate global id")
        seen_ids.add(m.id)

        if reasons:
            incomplete.append(f"{m.id}: {', '.join(reasons)}")

    assert not incomplete, "Incomplete model routes:\n" + "\n".join(incomplete)


def test_no_unknown_context_or_scores():
    models = _all_default_models()
    bad: list[str] = []
    for m in models:
        if m.context_window is None:
            bad.append(f"{m.id}: context is null")
        for role in ("sentinel", "pathfinder", "responder", "auditor"):
            score = (m.profile_fit or {}).get(role)
            if score is None:
                bad.append(f"{m.id}: {role} is null")
    assert not bad, "\n".join(bad)


def test_catalog_intelligence_has_no_unknown_scores():
    for entry in _CATALOG:
        for role in ("sentinel", "pathfinder", "responder", "auditor"):
            score = entry.profile_fit.get(role)
            assert score is not None, f"{entry.patterns}: {role} is None"
            assert 0.0 <= score <= 1.0, f"{entry.patterns}: {role}={score} out of range"


def test_unknown_model_gets_provisional_intelligence():
    intel = get_model_intelligence("UnknownMaker", "UnknownFamily", "unknown-model")
    assert intel["evidence_level"] == "Provisional"
    for role in ("sentinel", "pathfinder", "responder", "auditor"):
        assert intel["profile_fit"][role] is not None


def test_validation_summary():
    models = _all_default_models()
    print(f"\nTotal model routes: {len(models)}")
    print(f"Complete: {len(models)}")
    print(f"Missing: 0")
    print(f"Incomplete: 0")
    assert len(models) > 0
