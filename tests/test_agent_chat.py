"""Tests for the agent panel's chat/Ask mode and expanded model registry."""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="function")
def client():
    db_path = tempfile.mktemp(suffix=".db")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["DEBUG"] = "false"
    os.environ["NVIDIA_API_KEY"] = ""
    os.environ["OPENAI_API_KEY"] = ""

    import importlib

    import anvaya.config
    import anvaya.db
    import anvaya.main

    importlib.reload(anvaya.config)
    importlib.reload(anvaya.db)
    importlib.reload(anvaya.main)

    from anvaya.db import init_db
    from anvaya.main import app

    init_db()
    with TestClient(app) as c:
        yield c
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass


def test_chat_without_incident(client):
    """Chat mode must work without an incident and produce a response event."""
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "What does 72% mean?",
            "model_id": "anvaya-local-orchestrator",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert data["execution_id"]
    assert "response" in data

    events = client.get(f"/api/v1/agent/executions/{data['execution_id']}/events").json()["items"]
    types = [e["type"] for e in events]
    assert "chat.user" in types
    assert "chat.assistant" in types
    assert "agent.started" in types


def test_chat_with_unavailable_model_falls_back(client):
    """Requesting an unavailable external model falls back to local."""
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "Explain the blast radius.",
            "model_id": "nvidia-glm-5-2",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert "local fallback" in data["response"].lower()


def test_chat_rejects_empty_message(client):
    response = client.post("/api/v1/agent/chat", json={"message": ""})
    assert response.status_code == 400


def test_model_registry_includes_multimodal_models(client):
    """The model registry now includes multimodal NVIDIA and AgentRouter entries."""
    response = client.get("/api/v1/agent/models")
    assert response.status_code == 200
    data = response.json()
    by_id = {m["id"]: m for m in data["items"]}

    assert "agentrouter/claude-opus-5" in by_id
    assert "nvidia/meta/llama-3.2-90b-vision-instruct" in by_id
    assert by_id["nvidia/meta/llama-3.2-90b-vision-instruct"]["supports_multimodal"] is True
    assert "nvidia/meta/llama-3.2-11b-vision-instruct" in by_id
    assert by_id["nvidia/meta/llama-3.2-11b-vision-instruct"]["supports_multimodal"] is True
    assert "anvaya/local-policy" in by_id
    assert by_id["anvaya/local-policy"]["supports_multimodal"] is False


def test_rate_limiter_blocks_after_capacity():
    """The token bucket rate limiter blocks when capacity is exhausted."""
    from anvaya.llm.providers import RateLimiter

    limiter = RateLimiter(rpm=60.0, burst=1)
    assert limiter.acquire(blocking=False) is True
    assert limiter.acquire(blocking=False) is False
    assert limiter.acquire(blocking=True, timeout=0.05) is False


def test_rate_limiter_refills():
    """The token bucket refills over time."""
    import time

    from anvaya.llm.providers import RateLimiter

    limiter = RateLimiter(rpm=600.0, burst=1)
    assert limiter.acquire(blocking=False) is True
    time.sleep(0.15)
    assert limiter.acquire(blocking=False) is True


def test_chat_with_image_uses_multimodal_note_for_local(client):
    """Attaching an image to chat is accepted; when the model is not multimodal a note is added."""
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "What is in this image?",
            "model_id": "anvaya-local-orchestrator",
            "images": [
                "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAY"
                "AAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed"
    assert "image" in data["response"].lower() or "does not support" in data["response"].lower()


def test_chat_artifact_context_slicer_respects_top_and_bottom():
    """Reach/segments context must sort by the right score and select top/bottom N."""
    from anvaya.agent.chat import ChatEngine

    class Dummy(ChatEngine):
        def __init__(self):
            pass

    engine = Dummy()
    payload = {
        "items": [
            {
                "name": "app-03",
                "state": "CRITICAL",
                "attackScore": 1.0,
                "defenseScore": 0.0,
                "hops": 0,
                "adjacent": [],
            },
            {
                "name": "web-01",
                "state": "CRITICAL",
                "attackScore": 1.0,
                "defenseScore": 0.0,
                "hops": 0,
                "adjacent": [],
            },
            {
                "name": "10.0.0.1",
                "state": "REACHABLE",
                "attackScore": 0.125,
                "defenseScore": 0.88,
                "hops": 0,
                "adjacent": [],
            },
            {
                "name": "10.0.0.2",
                "state": "REACHABLE",
                "attackScore": 0.125,
                "defenseScore": 0.88,
                "hops": 0,
                "adjacent": [],
            },
        ]
    }

    top = engine._summarize_ranked_items(payload, "explain the first two reach draft")
    assert "app-03" in top
    assert "10.0.0.1" not in top
    assert "Showing the top 2" in top

    bottom = engine._summarize_ranked_items(payload, "explain the bottom two reach draft")
    assert "10.0.0.1" in bottom
    assert "app-03" not in bottom
    assert "Showing the bottom 2" in bottom

    defense = engine._summarize_ranked_items(payload, "explain the top two reach in defense mode")
    assert "neutralization score" in defense
    assert "10.0.0.1" in defense


def test_chat_creates_chat_mode_execution(client):
    """A new chat execution must be marked with mode='chat'."""
    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "hello", "model_id": "anvaya-local-orchestrator"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    execution = client.get(f"/api/v1/agent/executions/{data['execution_id']}").json()
    assert execution["mode"] == "chat"


def test_chat_continues_existing_execution(client):
    """Sending a follow-up with the same execution_id must append to the chat."""
    first = client.post(
        "/api/v1/agent/chat",
        json={"message": "hello", "model_id": "anvaya-local-orchestrator"},
    ).json()
    execution_id = first["execution_id"]

    second = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "follow up",
            "model_id": "anvaya-local-orchestrator",
            "execution_id": execution_id,
        },
    ).json()

    assert second["execution_id"] == execution_id
    events = client.get(f"/api/v1/agent/executions/{execution_id}/events").json()["items"]
    types = [e["type"] for e in events]
    assert types.count("chat.user") == 2
    assert types.count("chat.assistant") == 2
    assert types.count("agent.started") == 1


def test_chat_stream_creates_chat_mode_execution(client):
    """A new streaming chat execution is marked with mode='chat'."""

    def read_stream(payload):
        response = client.post("/api/v1/agent/chat/stream", json=payload)
        assert response.status_code == 200, response.text
        events = []
        for line in response.text.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
        return events

    first = read_stream({"message": "hello", "model_id": "anvaya-local-orchestrator"})
    execution_id = next(
        e["payload"]["execution_id"] for e in first if e["payload"].get("execution_id")
    )
    execution = client.get(f"/api/v1/agent/executions/{execution_id}").json()
    assert execution["mode"] == "chat"


def test_chat_stream_continues_existing_execution(client):
    """The streaming endpoint must also support chat continuation."""

    def read_stream(payload):
        response = client.post("/api/v1/agent/chat/stream", json=payload)
        assert response.status_code == 200, response.text
        events = []
        for line in response.text.split("\n"):
            line = line.strip()
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
        return events

    first = read_stream({"message": "hello", "model_id": "anvaya-local-orchestrator"})
    execution_id = next(
        e["payload"]["execution_id"] for e in first if e["payload"].get("execution_id")
    )

    second = read_stream(
        {
            "message": "follow up",
            "model_id": "anvaya-local-orchestrator",
            "execution_id": execution_id,
        }
    )
    assert all(
        e["payload"].get("execution_id") == execution_id
        for e in second
        if "execution_id" in e["payload"]
    )

    stored = client.get(f"/api/v1/agent/executions/{execution_id}/events").json()["items"]
    assert [e["type"] for e in stored].count("chat.user") == 2


def test_chat_system_prompt_includes_artifact_context_instructions(client):
    """The shared system prompt must contain artifact and dataset context guidance.

    The selected page context is now included directly in the user message so
    remote free-tier models cannot miss it.
    """
    from anvaya.agent.chat import ChatEngine
    from anvaya.db import get_session_sync

    engine = ChatEngine(get_session_sync())
    system = engine._system_prompt("hello", "selected text from page", "")
    assert "reach board" in system
    assert "artifact context" in system
    assert "dataset context" in system

    user_content = engine._build_user_content(
        "hello",
        [],
        None,
        None,
        context_text="selected text from page",
        project_id="",
    )
    assert isinstance(user_content, str)
    assert "selected text from page" in user_content


def test_chat_does_not_continue_non_chat_execution(client):
    """Passing an agentic execution_id must start a new chat instead of appending."""
    agentic = client.post(
        "/api/v1/agent/execute",
        json={"objective": "investigate something", "model_id": "anvaya-local-orchestrator"},
    ).json()
    agentic_id = agentic["execution_id"]

    chat = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "hello",
            "model_id": "anvaya-local-orchestrator",
            "execution_id": agentic_id,
        },
    ).json()

    assert chat["execution_id"] != agentic_id
    execution = client.get(f"/api/v1/agent/executions/{chat['execution_id']}").json()
    assert execution["mode"] == "chat"


def test_chat_multimodal_model_includes_image_content_in_user_message():
    """A multimodal model must receive the image as an OpenAI-style image_url part."""
    from anvaya.agent.chat import ChatEngine
    from anvaya.agent.profiles import get_model

    b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAY"
    raw_img = f"data:image/png;base64,{b64}"
    model = get_model("agentrouter/claude-opus-5")
    assert model is not None
    assert model.supports_multimodal is True

    class Dummy(ChatEngine):
        def __init__(self):
            pass

    engine = Dummy()
    provider = None
    content = engine._build_user_content(
        "What is in this image?",
        [raw_img],
        provider,
        model,
        context_text="",
        project_id="",
    )
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == raw_img


def test_chat_multimodal_flag_is_false_for_non_vision_models():
    """Non-vision models must not include image content."""
    from anvaya.agent.chat import ChatEngine
    from anvaya.agent.profiles import get_model

    model = get_model("anvaya/local-policy")
    assert model is not None
    assert model.supports_multimodal is False

    class Dummy(ChatEngine):
        def __init__(self):
            pass

    engine = Dummy()
    content = engine._build_user_content(
        "What is in this image?",
        ["data:image/png;base64,xxx"],
        None,
        model,
    )
    assert isinstance(content, list)
    assert len(content) == 1
    assert content[0]["type"] == "text"
    assert "does not support multimodal" in content[0]["text"]
    assert all(part.get("type") != "image_url" for part in content)


def test_chat_with_multimodal_anthropic_model_sends_image_source(client, monkeypatch):
    """An image attached in Ask mode reaches Anthropic-compatible models as image source parts."""
    import anvaya.llm.providers as providers
    from anvaya.config import settings

    captured: dict[str, object] = {}

    class FakeUsage:
        input_tokens = 10
        output_tokens = 5

    class FakeTextBlock:
        type = "text"
        text = "I see a chart with a red spike."

    class FakeMessage:
        content = [FakeTextBlock()]
        model = "claude-opus-5"
        stop_reason = "end_turn"
        usage = FakeUsage()

    class FakeMessages:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return FakeMessage()

    class FakeAnthropicClient:
        def __init__(self, **kwargs):
            pass

        messages = FakeMessages()

    monkeypatch.setattr(providers, "Anthropic", FakeAnthropicClient)
    monkeypatch.setattr(settings, "agentrouter_api_key", "sk-test")

    b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAY"
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "What is in this image?",
            "model_id": "agentrouter/claude-opus-5",
            "images": [f"data:image/png;base64,{b64}"],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "completed"

    kwargs = captured.get("kwargs")
    assert kwargs is not None, "Anthropic client.messages.create was not called"
    user_msg = kwargs["messages"][-1]
    assert user_msg["role"] == "user"
    assert user_msg["content"][0]["type"] == "text"
    image_part = user_msg["content"][1]
    assert image_part["type"] == "image"
    assert image_part["source"]["type"] == "base64"
    assert image_part["source"]["media_type"] == "image/png"
    assert image_part["source"]["data"] == b64
