"""Tests for the agent planner and model-driven plan selection."""

from __future__ import annotations

from anvaya.agent.planner import (
    DeterministicPlanner,
    ModelPlanner,
    resolve_planner,
)
from anvaya.agent.profiles import get_profile


def test_resolve_planner_falls_back_to_deterministic_without_credentials():
    from anvaya.config import settings

    original_agentrouter = settings.agentrouter_api_key
    original_nvidia = settings.nvidia_api_key
    original_opencode = settings.opencode_api_key
    original_openrouter = settings.openrouter_api_key
    settings.agentrouter_api_key = ""
    settings.nvidia_api_key = ""
    settings.opencode_api_key = ""
    settings.openrouter_api_key = ""
    try:
        profile = get_profile("sentinel")
        planner, model = resolve_planner(profile)
        assert isinstance(planner, DeterministicPlanner)
        assert model is not None
        assert model.provider == "anvaya"
    finally:
        settings.agentrouter_api_key = original_agentrouter
        settings.nvidia_api_key = original_nvidia
        settings.opencode_api_key = original_opencode
        settings.openrouter_api_key = original_openrouter


def test_deterministic_planner_builds_plan():
    class FakeResult:
        def first(self):
            return None

    class FakeSession:
        def exec(self, stmt):
            return FakeResult()

    planner = DeterministicPlanner()
    plan = planner.build_plan(
        session=FakeSession(),
        incident_id="INC-UNKNOWN",
        context={},
        profile=get_profile("sentinel"),
    )
    assert plan == []


def test_model_planner_parses_valid_plan():
    class FakeProvider:
        name = "fake"

        def chat_completion(self, *args, **kwargs):
            from anvaya.llm.providers import NormalizedModelResponse

            return NormalizedModelResponse(
                provider="fake",
                model="fake",
                text=(
                    '{"plan": [{"tool": "get_incident", '
                    '"inputs": {"incident_id": "INC-123"}, '
                    '"label": "Load incident"}]}'
                ),
            )

    profile = get_profile("sentinel")
    from anvaya.agent.profiles import get_model

    model = get_model("anvaya/local-policy")
    planner = ModelPlanner(FakeProvider(), model, profile)  # type: ignore[arg-type]
    plan = planner.build_plan(
        session=None,
        incident_id="INC-123",
        context={"objective": "investigate"},
        profile=profile,
    )
    assert plan is not None
    assert len(plan) == 1
    assert plan[0]["tool"] == "get_incident"
    assert plan[0]["inputs"]["incident_id"] == "INC-123"
