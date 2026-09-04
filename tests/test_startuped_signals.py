"""Tests for the Startuped behavioral signal adapter."""

from __future__ import annotations

import queue
from typing import Any

import httpx
import pytest

from anvaya import startuped_signals


@pytest.fixture()
def signal_queue(monkeypatch: pytest.MonkeyPatch) -> queue.Queue[Any]:
    test_queue: queue.Queue[Any] = queue.Queue()
    monkeypatch.setattr(startuped_signals, "_queue", test_queue)
    monkeypatch.setattr(startuped_signals, "_api_key", lambda: "sk_test")
    monkeypatch.setattr(startuped_signals, "_ensure_worker", lambda: None)
    return test_queue


def test_post_payload_uses_canonical_host_and_client_header(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = kwargs["headers"]
        captured["json"] = kwargs["json"]
        return httpx.Response(201, json={"success": True, "signal": {"id": "sig-1"}})

    monkeypatch.setattr(startuped_signals.httpx, "post", fake_post)
    monkeypatch.setattr(startuped_signals, "_api_key", lambda: "sk_test")

    result = startuped_signals._post_payload({"name": "test-signal"})

    assert result["ok"] is True
    assert result["signal_id"] == "sig-1"
    assert captured["url"] == "https://www.startuped.ai/api/v1/marketing/signals"
    assert captured["headers"]["X-Startuped-Client"] == "sdk-python"
    assert captured["headers"]["Authorization"] == "Bearer sk_test"


def test_api_request_signal_maps_project_creation(signal_queue: queue.Queue[Any]) -> None:
    startuped_signals.emit_api_request_signal("POST", "/api/v1/projects", 201)
    payload = signal_queue.get_nowait()

    assert payload["name"] == "anvaya.project.created"
    assert payload["type"] == "conversion"
    assert payload["metadata"]["surface"] == "backend"


def test_api_request_signal_ignores_get_and_errors(signal_queue: queue.Queue[Any]) -> None:
    startuped_signals.emit_api_request_signal("GET", "/api/v1/projects", 200)
    startuped_signals.emit_api_request_signal("POST", "/api/v1/projects", 500)

    assert signal_queue.empty()


def test_agent_event_signal_maps_reasoning_lifecycle(signal_queue: queue.Queue[Any]) -> None:
    startuped_signals.emit_agent_event_signal(
        {
            "execution_id": "exec-1",
            "sequence": 1,
            "type": "agent.reasoning_started",
            "timestamp": "2026-09-04T00:00:00Z",
            "label": "Reasoning started",
        }
    )
    payload = signal_queue.get_nowait()

    assert payload["name"] == "anvaya.agent.reasoning.step.started"
    assert payload["metadata"]["executionId"] == "exec-1"


def test_agent_event_signal_maps_tool_completion(signal_queue: queue.Queue[Any]) -> None:
    startuped_signals.emit_agent_event_signal(
        {
            "execution_id": "exec-1",
            "type": "tool.completed",
            "tool_name": "detect_anomalies",
            "label": "Detection complete",
        }
    )
    payload = signal_queue.get_nowait()

    assert payload["name"] == "anvaya.agent.tool.completed"
    assert payload["metadata"]["tool"] == "detect_anomalies"


def test_emit_startuped_signal_is_non_blocking_and_generates_key(
    signal_queue: queue.Queue[Any],
) -> None:
    queued = startuped_signals.emit_startuped_signal(
        "anvaya.ui.interaction",
        "User clicked a control",
        strength=10,
        value="Low",
        metadata={"surface": "frontend"},
    )

    assert queued is True
    payload = signal_queue.get_nowait()
    assert payload["signalKey"].startswith("anvaya:anvaya.ui.interaction:")
    assert payload["metadata"]["eventId"]
