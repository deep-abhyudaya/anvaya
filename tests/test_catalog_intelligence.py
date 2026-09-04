"""Tests for benchmark-grounded model catalog intelligence."""

from __future__ import annotations

import pytest
from anvaya.llm.catalog_intelligence import (
    display_name_for_model,
    get_model_intelligence,
    has_role_fit,
)


@pytest.mark.parametrize(
    "maker,family,model_id,expected_sentinel,expected_quality",
    [
        ("Anthropic", "Claude Opus", "claude-opus-5", 0.98, "frontier"),
        ("Anthropic", "Claude Opus", "claude-opus-4.8", 0.94, "frontier"),
        ("OpenAI", "GPT-5.6", "gpt-5.6-sol", 0.92, "frontier"),
        ("Moonshot AI", "Kimi K3", "kimi-k3", 0.94, "frontier"),
        ("Z AI", "GLM 5.2", "glm-5.2", 0.86, "strong"),
        ("DeepSeek", "DeepSeek V4", "deepseek-v4-flash", 0.86, "strong"),
        ("Meta", "Muse Spark", "muse-spark-1.2", 0.87, "strong"),
        ("NVIDIA", "Nemotron 3", "nemotron-3-ultra", 0.89, "strong"),
        ("NVIDIA", "Nemotron 3.5", "nemotron-3.5-lightning", 0.72, "specialist"),
        ("Meta", "Llama 3.1", "llama-3.1-70b-instruct", 0.68, "utility"),
        ("Meta", "Llama 3.1", "llama-3.1-8b-instruct", 0.42, "utility"),
        ("MiniMax", "MiniMax M3", "minimax-m3", 0.75, "utility"),
        ("Unknown / undisclosed", "Ox Alpha", "ox-alpha", 0.70, "specialist"),
    ],
)
def test_catalog_matches_known_models(maker, family, model_id, expected_sentinel, expected_quality):
    intelligence = get_model_intelligence(maker, family, model_id)
    assert intelligence["profile_fit"]["sentinel"] == expected_sentinel
    assert intelligence["quality_class"] == expected_quality
    assert intelligence["evidence_confidence"] != "Unknown"
    assert has_role_fit(intelligence) is True


def test_unknown_model_returns_low_confidence_and_no_role_fit():
    intelligence = get_model_intelligence("Unknown", "Mystery", "mystery-model-x")
    assert has_role_fit(intelligence) is False
    assert intelligence["evidence_confidence"] == "Unknown"
    assert intelligence["recommendation_confidence"] == "Low"
    assert intelligence["quality_class"] == "unknown"


def test_insufficient_evidence_has_na_role_fit():
    intelligence = get_model_intelligence("Poolside", "Laguna 2.1", "laguna-xs-2.1")
    assert intelligence["profile_fit"]["sentinel"] is None
    assert has_role_fit(intelligence) is False
    assert intelligence["evidence_confidence"] == "Low"


def test_router_has_no_role_fit():
    intelligence = get_model_intelligence("OpenRouter", "Free Models Router", "free-models-router")
    assert has_role_fit(intelligence) is False
    assert intelligence["profile_fit"]["pathfinder"] is None


def test_gateway_variants_share_underlying_evidence():
    """The same underlying model should retain the same evidence profile across gateways."""
    maker, family, model_id = "Meta", "Muse Spark", "muse-spark-1.2"
    opencode = get_model_intelligence(maker, family, model_id, provider="opencode")
    nvidia = get_model_intelligence(maker, family, model_id, provider="nvidia")
    assert opencode["profile_fit"] == nvidia["profile_fit"]
    assert opencode["evidence_confidence"] == nvidia["evidence_confidence"]


def test_profile_fit_values_are_within_range():
    intelligence = get_model_intelligence("Anthropic", "Claude Opus", "claude-opus-5")
    for v in intelligence["profile_fit"].values():
        assert v is None or (0.0 <= v <= 1.0)


def test_public_evidence_is_attributed():
    intelligence = get_model_intelligence("NVIDIA", "Nemotron 3", "nemotron-3-ultra")
    sources = {ev["source"] for ev in intelligence["benchmark_evidence"]}
    assert "Provider-reported" in sources


def test_cost_is_separate_from_quality():
    """Cost class must not be embedded in the intelligence dict."""
    intelligence = get_model_intelligence("Meta", "Muse Spark", "muse-spark-1.2")
    assert "cost_class" not in intelligence


@pytest.mark.parametrize(
    "raw_name,expected",
    [
        ("LiquidAI: LFM2.5-2.6B (free)", "LFM2.5-2.6B"),
        ("Google: Gemma 4 26B A4B (free)", "Gemma 4 26B A4B"),
        ("Poolside: Laguna S 2.1 (free)", "Laguna S 2.1"),
        ("Z.ai: GLM 5.2 (free)", "GLM 5.2"),
        ("Moonshot AI: Kimi K3 (free)", "Kimi K3"),
        ("OpenAI: GPT-5.6-sol (free)", "GPT-5.6-sol"),
        ("Anthropic: Claude Opus 5 (free)", "Claude Opus 5"),
        ("NVIDIA: Nemotron 3 Ultra (free)", "Nemotron 3 Ultra"),
        ("Meta: Muse Spark 1.2 Free", "Muse Spark 1.2"),
        ("DeepSeek V4 Flash Free", "DeepSeek V4 Flash"),
    ],
)
def test_display_name_strips_maker_and_free(raw_name, expected):
    assert display_name_for_model("provider/model", raw_name=raw_name) == expected


def test_display_name_falls_back_to_catalog_pattern():
    intelligence = get_model_intelligence("NVIDIA", "Nemotron 3", "nemotron-3-ultra-550b-a55b")
    assert intelligence["display_name"] == "Nemotron 3 Ultra"


def test_display_name_for_unknown_model():
    assert display_name_for_model("some-vendor/mystery-model-x") == "Mystery Model X"


def test_display_name_capitalises_oss_acronym():
    assert display_name_for_model("openai/gpt-oss-20b") == "GPT OSS 20B"
    assert display_name_for_model("nvidia/openai/gpt-oss-20b") == "GPT OSS 20B"
