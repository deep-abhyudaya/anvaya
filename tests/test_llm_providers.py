"""Tests for the model provider layer and capability gating."""

from __future__ import annotations

from anvaya.agent.profiles import default_models
from anvaya.agent.schemas import ModelConfig
from anvaya.llm.providers import (
    AgentRouterAnthropicProvider,
    AgentRouterOpenAIProvider,
    EmperoProvider,
    GMICloudProvider,
    LocalProvider,
    NVIDIAProvider,
    SeekAIProvider,
    get_model_provider,
    is_model_compatible,
    select_model_provider_for_profile,
)


def test_local_provider_is_always_available():
    provider = LocalProvider()
    assert provider.configured() is True
    assert provider.healthy() is True
    assert provider.availability() == "available"
    assert provider.supports_capability("chat") is True


def test_nvidia_provider_unconfigured():
    provider = NVIDIAProvider()
    assert provider.configured() is False
    assert provider.healthy() is False
    assert provider.availability() == "unavailable"
    response = provider.chat_completion([{"role": "user", "content": "test"}])
    assert response.error != ""
    assert response.provider == "nvidia"


def test_agentrouter_openai_provider_unconfigured():
    provider = AgentRouterOpenAIProvider()
    assert provider.configured() is False
    response = provider.chat_completion([{"role": "user", "content": "test"}])
    assert response.error != ""


def test_agentrouter_anthropic_provider_unconfigured():
    provider = AgentRouterAnthropicProvider()
    assert provider.configured() is False
    response = provider.chat_completion([{"role": "user", "content": "test"}])
    assert response.error != ""


def test_get_model_provider():
    assert get_model_provider("nvidia") is not None
    assert get_model_provider("agentrouter") is not None
    assert get_model_provider("anvaya") is not None
    assert get_model_provider("unknown") is None


def test_is_model_compatible():
    model = ModelConfig(
        id="test",
        provider="anvaya",
        model="local-policy",
        display_name="Test",
        description="",
        purpose="",
        capabilities=["chat", "tools"],
        context_window=0,
        supports_tools=True,
        supports_streaming=False,
        supports_reasoning=False,
        recommended_for=[],
    )
    ok, _ = is_model_compatible(model, ["chat", "tools"])
    assert ok is True

    ok, reason = is_model_compatible(model, ["chat", "tools", "streaming"])
    assert ok is False
    assert "streaming" in reason


def test_select_model_provider_for_profile_without_credentials():
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
        models = default_models()
        model, provider, _ = select_model_provider_for_profile("sentinel", models)
        assert model is not None
        assert model.provider == "anvaya"
        assert isinstance(provider, LocalProvider)
    finally:
        settings.agentrouter_api_key = original_agentrouter
        settings.nvidia_api_key = original_nvidia
        settings.opencode_api_key = original_opencode
        settings.openrouter_api_key = original_openrouter


def test_default_models_include_nvidia_candidates():
    models = default_models()
    ids = {m.id for m in models}
    assert "nvidia/meta/llama-3.1-8b-instruct" in ids
    assert "nvidia/meta/llama-3.2-11b-vision-instruct" in ids
    assert "agentrouter/gpt-5.6-sol" in ids
    assert "agentrouter/claude-opus-5" in ids
    assert "anvaya/local-policy" in ids


def test_default_models_capabilities_are_unique():
    for m in default_models():
        assert len(m.capabilities) == len(set(m.capabilities)), (
            f"{m.id} has duplicate capabilities: {m.capabilities}"
        )


def test_seekai_provider_unconfigured():
    provider = SeekAIProvider()
    assert provider.configured() is False
    assert provider.availability() == "unavailable"
    response = provider.chat_completion([{"role": "user", "content": "test"}])
    assert response.error != ""
    assert response.provider == "seekai"


def test_gmicloud_provider_unconfigured():
    provider = GMICloudProvider()
    assert provider.configured() is False
    assert provider.availability() == "unavailable"
    response = provider.chat_completion([{"role": "user", "content": "test"}])
    assert response.error != ""
    assert response.provider == "gmicloud"


def test_empero_provider_unconfigured():
    provider = EmperoProvider()
    assert provider.configured() is False
    assert provider.availability() == "unavailable"
    response = provider.chat_completion([{"role": "user", "content": "test"}])
    assert response.error != ""
    assert response.provider == "empero"


def test_get_model_provider_new_providers():
    assert get_model_provider("seekai") is not None
    assert get_model_provider("gmicloud") is not None
    assert get_model_provider("empero") is not None


def test_default_models_include_seekai_catalog():
    models = default_models()
    assert any("seekai" in m.id for m in models)
    assert any(m.provider == "seekai" for m in models)


def test_seekai_catalog_preserves_user_model_ids():
    from anvaya.llm.seekai_catalog import get_seekai_model_configs

    configs = get_seekai_model_configs()
    ids = {c["provider_model_id"] for c in configs}
    assert "claude-fable-5" in ids
    assert "claude-opus-4-8" in ids
    assert "deepseek-v4-pro-0813" in ids
    assert "gpt-5.6-sol" in ids


def test_gmicloud_minimax_m3_is_promotional_free():
    from anvaya.llm.gmicloud_catalog import get_gmicloud_model_configs

    configs = get_gmicloud_model_configs()
    minimax = [c for c in configs if "MiniMax-M3" in c.get("provider_model_id", "")]
    assert minimax, "MiniMax M3 must appear in the GMI Cloud catalog"
    assert minimax[0]["cost_class"] == "free"
    assert minimax[0]["access_class"] == "promotional_free"


def test_empero_models_are_community_free_and_public():
    from anvaya.llm.empero_catalog import get_empero_model_configs

    configs = get_empero_model_configs()
    assert configs
    for c in configs:
        assert c["cost_class"] == "free"
        assert c["access_class"] == "community_free"
        assert c["privacy_class"] == "public_community_endpoint"


def test_seekai_catalog_merges_live_only_model_ids(monkeypatch):
    from anvaya.llm import seekai_catalog

    def _fake_fetch():
        return ["gemini-3-6-flash", "unknown-live-model"]

    monkeypatch.setattr(seekai_catalog, "_fetch_seekai_model_ids", _fake_fetch)
    configs = seekai_catalog.get_seekai_model_configs()
    ids = {c["provider_model_id"] for c in configs}
    by_id = {c["provider_model_id"]: c for c in configs}

    assert "gemini-3-6-flash" in ids
    assert "unknown-live-model" in ids
    assert "claude-opus-5" not in ids
    assert by_id["unknown-live-model"]["display_name"]


def test_gmicloud_catalog_surfaces_all_live_chat_models(monkeypatch):
    from anvaya.config import settings
    from anvaya.llm import gmicloud_catalog

    fake_models = [
        {"id": "deepseek-ai/DeepSeek-R1", "name": "DeepSeek R1"},
        {"id": "MiniMaxAI/MiniMax-M3", "name": "MiniMax M3", "is_free": True},
    ]

    monkeypatch.setattr(gmicloud_catalog, "_fetch_gmicloud_models", lambda: fake_models)
    original_key = settings.gmicloud_api_key
    original_free_only = settings.gmicloud_free_only
    try:
        settings.gmicloud_api_key = "fake-key"
        settings.gmicloud_free_only = False
        configs = gmicloud_catalog.get_gmicloud_model_configs()
        ids = {c["provider_model_id"] for c in configs}

        assert "deepseek-ai/DeepSeek-R1" in ids
        assert "MiniMaxAI/MiniMax-M3" in ids
    finally:
        settings.gmicloud_api_key = original_key
        settings.gmicloud_free_only = original_free_only


def test_agentrouter_providers_propagate_multimodal_capability():
    """Multimodal ModelConfig must produce providers that declare multimodal support."""
    from anvaya.agent.profiles import get_model
    from anvaya.llm.providers import get_model_provider_for_config

    claude = get_model("agentrouter/claude-opus-5")
    assert claude is not None
    assert claude.supports_multimodal is True
    provider = get_model_provider_for_config(claude)
    assert provider is not None
    assert provider.supports_capability("multimodal") is True

    gpt = get_model("agentrouter/gpt-5.6-sol")
    assert gpt is not None
    assert gpt.supports_multimodal is True
    provider = get_model_provider_for_config(gpt)
    assert provider is not None
    assert provider.supports_capability("multimodal") is True


def test_join_stream_text_inserts_missing_spaces():
    from anvaya.llm.providers import _join_stream_text

    assert _join_stream_text("The", "agent") == " agent"
    assert _join_stream_text("will", "delete") == " delete"

    assert _join_stream_text("The", " agent") == " agent"

    assert _join_stream_text("end.", "New") == " New"
    assert _join_stream_text("hi,", "world") == " world"

    assert _join_stream_text("word", ".") == "."
    assert _join_stream_text("don", "'t") == "'t"
    assert _join_stream_text("(", "word") == "word"

    assert _join_stream_text("", "hello") == "hello"
    assert _join_stream_text("hello ", "world") == "world"
