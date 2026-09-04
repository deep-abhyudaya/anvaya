"""Tests for the AgentRouter provider adapter.

These tests verify that AgentRouter models are selectable, route to the correct
protocol, and normalize responses. No real network calls are made.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

from anvaya.agent.profiles import default_models, get_model
from anvaya.agent.schemas import ModelConfig
from anvaya.llm.providers import (
    AgentRouterAnthropicProvider,
    AgentRouterOpenAIProvider,
    get_model_provider_for_config,
    select_model_provider_for_profile,
)



class FakeOpenAIResponse:
    def __init__(
        self,
        content: str = "",
        tool_calls: list[Any] | None = None,
        model: str = "gpt-5.6-sol",
    ) -> None:
        self.model = model
        self.choices = [
            SimpleNamespace(
                finish_reason="tool_calls" if tool_calls else "stop",
                message=SimpleNamespace(
                    content=content or None,
                    tool_calls=tool_calls or [],
                ),
            )
        ]
        self.usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class FakeOpenAIStream:
    def __init__(
        self,
        deltas: list[str],
        tool_calls: list[dict[str, Any]] | None = None,
        model: str = "gpt-5.6-sol",
    ) -> None:
        self.deltas = deltas
        self.tool_calls = tool_calls or []
        self.model = model

    def __iter__(self) -> Iterator[SimpleNamespace]:
        for delta in self.deltas:
            yield SimpleNamespace(
                model=self.model,
                choices=[
                    SimpleNamespace(
                        finish_reason="",
                        delta=SimpleNamespace(
                            content=delta,
                            tool_calls=[],
                        ),
                    )
                ],
            )
        if self.tool_calls:
            yield SimpleNamespace(
                model=self.model,
                choices=[
                    SimpleNamespace(
                        finish_reason="tool_calls",
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=self.tool_calls,
                        ),
                    )
                ],
            )


class FakeOpenAIChat:
    def __init__(self, response: Any = None, stream: Any = None) -> None:
        self.response = response
        self.stream = stream

    def create(self, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            return self.stream
        return self.response


class FakeOpenAIClient:
    def __init__(self, response: Any = None, stream: Any = None, **kwargs: Any) -> None:
        self.chat = SimpleNamespace(completions=FakeOpenAIChat(response, stream))




class FakeUsage:
    input_tokens = 10
    output_tokens = 5


class FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, id: str, name: str, input: dict[str, Any]) -> None:
        self.id = id
        self.name = name
        self.input = input


class FakeMessage:
    def __init__(
        self,
        content: list[Any],
        model: str = "claude-opus-4-8",
        stop_reason: str = "end_turn",
    ) -> None:
        self.content = content
        self.model = model
        self.stop_reason = stop_reason
        self.usage = FakeUsage()


class FakeStream:
    """Yields fake MessageStreamEvent objects and supports the context manager protocol."""

    def __init__(self, events: list[Any]) -> None:
        self._events = events

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def __iter__(self) -> Iterator[Any]:
        for event in self._events:
            yield event


class FakeMessages:
    def __init__(
        self,
        message: FakeMessage | None = None,
        stream: FakeStream | None = None,
    ) -> None:
        self._message = message
        self._stream = stream

    def create(self, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            return self._stream
        return self._message


class FakeAnthropicClient:
    def __init__(
        self,
        message: FakeMessage | None = None,
        stream: FakeStream | None = None,
        **kwargs: Any,
    ) -> None:
        self.messages = FakeMessages(message, stream)




def test_default_models_expose_agentrouter() -> None:
    """The model registry exposes the three AgentRouter models."""
    models = default_models()
    ids = {m.id for m in models}
    assert "agentrouter/gpt-5.6-sol" in ids
    assert "agentrouter/claude-opus-4-8" in ids
    assert "agentrouter/claude-opus-5" in ids

    gpt = get_model("agentrouter/gpt-5.6-sol")
    assert gpt is not None
    assert gpt.protocol == "anthropic-compatible"
    assert gpt.base_url == "https://agentrouter.org"
    assert gpt.supports_tools is True
    assert gpt.supports_streaming is True

    claude = get_model("agentrouter/claude-opus-5")
    assert claude is not None
    assert claude.protocol == "anthropic-compatible"
    assert claude.base_url == "https://agentrouter.org"


def test_create_model_provider_respects_protocol() -> None:
    """Provider construction uses the ModelConfig protocol/base_url fields."""
    gpt = ModelConfig(
        id="agentrouter/gpt-5.6-sol",
        provider="agentrouter",
        model="gpt-5.6-sol",
        display_name="",
        description="",
        purpose="",
        capabilities=["chat", "tools", "streaming", "structured-outputs"],
        context_window=128000,
        supports_tools=True,
        supports_streaming=True,
        supports_reasoning=False,
        recommended_for=["sentinel"],
        protocol="anthropic-compatible",
        base_url="https://agentrouter.org",
    )
    provider = get_model_provider_for_config(gpt)
    assert isinstance(provider, AgentRouterAnthropicProvider)
    assert provider.model == "gpt-5.6-sol"
    assert provider.base_url == "https://agentrouter.org"

    claude = ModelConfig(
        id="agentrouter/claude-opus-5",
        provider="agentrouter",
        model="claude-opus-5",
        display_name="",
        description="",
        purpose="",
        capabilities=["chat", "tools", "streaming", "structured-outputs"],
        context_window=200000,
        supports_tools=True,
        supports_streaming=True,
        supports_reasoning=False,
        recommended_for=["sentinel"],
        protocol="anthropic-compatible",
        base_url="https://agentrouter.org",
    )
    provider = get_model_provider_for_config(claude)
    assert isinstance(provider, AgentRouterAnthropicProvider)
    assert provider.model == "claude-opus-5"
    assert provider.base_url == "https://agentrouter.org"


def test_select_model_provider_prefers_agentrouter(monkeypatch) -> None:
    """When AgentRouter is configured, it is preferred over NVIDIA and local."""
    from anvaya.config import settings

    original = settings.agentrouter_api_key
    settings.agentrouter_api_key = "sk-test"
    try:
        models = default_models()
        model, provider, reason = select_model_provider_for_profile("sentinel", models)
        assert model is not None
        assert model.provider == "agentrouter"
        assert model.id == "agentrouter/gpt-5.6-sol"
    finally:
        settings.agentrouter_api_key = original




def test_agentrouter_openai_sync_chat(monkeypatch) -> None:
    import anvaya.llm.providers as providers

    monkeypatch.setattr(
        providers,
        "OpenAI",
        lambda **kwargs: FakeOpenAIClient(
            response=FakeOpenAIResponse(content="Hello from AgentRouter.")
        ),
    )
    from anvaya.config import settings

    settings.agentrouter_api_key = "sk-test"
    provider = AgentRouterOpenAIProvider(model="gpt-5.6-sol")
    response = provider.chat_completion([{"role": "user", "content": "hi"}])
    assert not isinstance(response, Iterator)
    assert response.error == ""
    assert response.text == "Hello from AgentRouter."
    assert response.provider == "agentrouter"
    assert response.model == "gpt-5.6-sol"
    assert response.tool_calls == []


def test_agentrouter_openai_sync_tool_call(monkeypatch) -> None:
    import anvaya.llm.providers as providers

    tool_calls = [
        SimpleNamespace(
            id="call_1",
            function=SimpleNamespace(
                name="get_telemetry",
                arguments='{"incident_id":"INC-1"}',
            ),
        )
    ]
    monkeypatch.setattr(
        providers,
        "OpenAI",
        lambda **kwargs: FakeOpenAIClient(
            response=FakeOpenAIResponse(tool_calls=tool_calls)
        ),
    )
    from anvaya.config import settings

    settings.agentrouter_api_key = "sk-test"
    provider = AgentRouterOpenAIProvider(model="gpt-5.6-sol")
    tools = [
        {
            "name": "get_telemetry",
            "description": "Fetch telemetry",
            "input_schema": {
                "type": "object",
                "properties": {"incident_id": {"type": "string"}},
                "required": ["incident_id"],
            },
        }
    ]
    response = provider.chat_completion(
        [{"role": "user", "content": "check incident"}], tools=tools
    )
    assert not isinstance(response, Iterator)
    assert response.error == ""
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "get_telemetry"
    assert response.tool_calls[0]["arguments"]["incident_id"] == "INC-1"


def test_agentrouter_openai_streaming(monkeypatch) -> None:
    import anvaya.llm.providers as providers

    stream = FakeOpenAIStream(deltas=["Hello", " from", " AgentRouter"])
    monkeypatch.setattr(
        providers,
        "OpenAI",
        lambda **kwargs: FakeOpenAIClient(stream=stream),
    )
    from anvaya.config import settings

    settings.agentrouter_api_key = "sk-test"
    provider = AgentRouterOpenAIProvider(model="gpt-5.6-sol")
    result = provider.chat_completion([{"role": "user", "content": "hi"}], stream=True)
    assert isinstance(result, Iterator)
    chunks = list(result)
    text = "".join(c.text for c in chunks)
    assert text == "Hello from AgentRouter"
    assert all(c.provider == "agentrouter" for c in chunks)




def test_agentrouter_anthropic_sync_chat(monkeypatch) -> None:
    import anvaya.llm.providers as providers

    message = FakeMessage(content=[FakeTextBlock("Hello from Claude.")])
    monkeypatch.setattr(
        providers,
        "Anthropic",
        lambda **kwargs: FakeAnthropicClient(message=message),
    )
    from anvaya.config import settings

    settings.agentrouter_api_key = "sk-test"
    provider = AgentRouterAnthropicProvider(model="claude-opus-4-8")
    response = provider.chat_completion([{"role": "user", "content": "hi"}])
    assert not isinstance(response, Iterator)
    assert response.error == ""
    assert response.text == "Hello from Claude."
    assert response.provider == "agentrouter"
    assert response.model == "claude-opus-4-8"


def test_agentrouter_anthropic_sync_tool_call(monkeypatch) -> None:
    import anvaya.llm.providers as providers

    message = FakeMessage(
        content=[
            FakeTextBlock("I will fetch telemetry."),
            FakeToolUseBlock("tu_1", "get_telemetry", {"incident_id": "INC-1"}),
        ],
        stop_reason="tool_use",
    )
    monkeypatch.setattr(
        providers,
        "Anthropic",
        lambda **kwargs: FakeAnthropicClient(message=message),
    )
    from anvaya.config import settings

    settings.agentrouter_api_key = "sk-test"
    provider = AgentRouterAnthropicProvider(model="claude-opus-4-8")
    tools = [
        {
            "name": "get_telemetry",
            "description": "Fetch telemetry",
            "input_schema": {
                "type": "object",
                "properties": {"incident_id": {"type": "string"}},
                "required": ["incident_id"],
            },
        }
    ]
    response = provider.chat_completion(
        [{"role": "user", "content": "check incident"}], tools=tools
    )
    assert not isinstance(response, Iterator)
    assert response.error == ""
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "get_telemetry"
    assert response.tool_calls[0]["arguments"]["incident_id"] == "INC-1"


def test_agentrouter_anthropic_streaming(monkeypatch) -> None:
    import anvaya.llm.providers as providers

    events = [
        SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(model="claude-opus-4-8", id="msg_1"),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="text_delta", text="Hello from Claude."),
        ),
        SimpleNamespace(type="message_stop"),
    ]
    stream = FakeStream(events)
    monkeypatch.setattr(
        providers,
        "Anthropic",
        lambda **kwargs: FakeAnthropicClient(stream=stream),
    )
    from anvaya.config import settings

    settings.agentrouter_api_key = "sk-test"
    provider = AgentRouterAnthropicProvider(model="claude-opus-4-8")
    result = provider.chat_completion([{"role": "user", "content": "hi"}], stream=True)
    assert isinstance(result, Iterator)
    chunks = list(result)
    text = "".join(c.text for c in chunks)
    assert text == "Hello from Claude."
    assert all(c.provider == "agentrouter" for c in chunks)




def test_agentrouter_openai_returns_error_without_credentials() -> None:
    from anvaya.config import settings

    original = settings.agentrouter_api_key
    settings.agentrouter_api_key = ""
    try:
        provider = AgentRouterOpenAIProvider(model="gpt-5.6-sol")
        response = provider.chat_completion([{"role": "user", "content": "hi"}])
        assert not isinstance(response, Iterator)
        assert response.error != ""
        assert response.category == "AGENTROUTER_NOT_CONFIGURED"
    finally:
        settings.agentrouter_api_key = original


def test_agentrouter_anthropic_returns_error_without_credentials() -> None:
    from anvaya.config import settings

    original = settings.agentrouter_api_key
    settings.agentrouter_api_key = ""
    try:
        provider = AgentRouterAnthropicProvider(model="claude-opus-4-8")
        response = provider.chat_completion([{"role": "user", "content": "hi"}])
        assert not isinstance(response, Iterator)
        assert response.error != ""
        assert response.category == "AGENTROUTER_NOT_CONFIGURED"
    finally:
        settings.agentrouter_api_key = original


def test_agentrouter_anthropic_converts_openai_image_url_to_image_source() -> None:
    """Anthropic-compatible models receive OpenAI-style image_url parts
    as Anthropic image source parts."""
    from anvaya.llm.providers import AgentRouterAnthropicProvider

    b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAY"
    url = f"data:image/png;base64,{b64}"
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What is in this image?"},
                {"type": "image_url", "image_url": {"url": url}},
            ],
        },
    ]
    system, chat_messages = AgentRouterAnthropicProvider._prepare_messages(messages, None)
    assert system == "You are a helpful assistant."
    assert len(chat_messages) == 1
    user = chat_messages[0]
    assert user["role"] == "user"
    assert user["content"][0] == {"type": "text", "text": "What is in this image?"}
    assert user["content"][1]["type"] == "image"
    assert user["content"][1]["source"]["type"] == "base64"
    assert user["content"][1]["source"]["media_type"] == "image/png"
    assert user["content"][1]["source"]["data"] == b64
