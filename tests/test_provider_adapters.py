"""Tests for optional provider adapters and truthful fallback attribution."""

from __future__ import annotations

from unittest.mock import MagicMock

from anvaya.agent.adapters import (
    GmailAdapter,
    LyzrAdapter,
    N8NAdapter,
    TavilyAdapter,
    all_provider_status,
    select_provider,
)
from anvaya.config import settings


def test_tavily_unconfigured_returns_fixture():
    tavily = TavilyAdapter()
    assert tavily.configured() is False
    result = tavily.search("1.2.3.4")
    assert result["provider"] == "anvaya-local-fixture"
    assert "Tavily not configured" in result["note"]
    assert result["records"]


def test_n8n_unconfigured_records_noop():
    n8n = N8NAdapter()
    assert n8n.configured() is False
    result = n8n.trigger("notify", {"incident_id": "INC-123"})
    assert result["status"] == "recorded"
    assert result["source"] == "anvaya-local-handler"
    assert result["fallback_used"] is True


def test_select_provider_prefers_healthy_primary():
    provider, reason = select_provider("n8n", "anvaya")
    assert provider == "anvaya"
    assert "unavailable" in reason


def test_all_provider_status_includes_model_providers():
    status = all_provider_status()
    by_provider = {s["provider"]: s for s in status}
    assert "nvidia" in by_provider
    assert "openai" in by_provider
    assert "anvaya" in by_provider
    assert "tavily" in by_provider
    assert "n8n" in by_provider
    assert "gmail" in by_provider


class FakeGmailService:
    """Minimal fake for the Gmail API users().messages().send chain."""

    def __init__(self):
        self.calls = []

    def users(self):
        return self

    def messages(self):
        return self

    def send(self, **kwargs):
        self.calls.append(kwargs)

        class Request:
            def execute(self):
                return {"id": "msg-123"}

        return Request()


def test_gmail_unconfigured_records_fallback():
    gmail = GmailAdapter()
    assert gmail.configured() is False
    result = gmail.send("team@example.com", "Test subject", "Test body")
    assert result["status"] == "recorded"
    assert result["fallback_used"] is True
    assert "Test body" in result["body"]


def test_gmail_configured_send_success(monkeypatch):
    """A configured Gmail adapter can send via the Gmail API when mocked."""
    monkeypatch.setattr(settings, "gmail_credentials_path", "/fake/creds.json")
    monkeypatch.setattr(settings, "gmail_from_email", "soc@example.com")

    fake = FakeGmailService()
    monkeypatch.setattr(GmailAdapter, "_build_service", lambda self: fake)

    gmail = GmailAdapter()
    assert gmail.healthy() is True
    result = gmail.send("team@example.com", "Incident sealed", "Investigation complete.")

    assert result["status"] == "sent"
    assert result["provider"] == "gmail"
    assert result["fallback_used"] is False
    assert len(fake.calls) == 1
    assert fake.calls[0]["body"]["raw"]


def test_lyzr_unconfigured_returns_fallback():
    lyzr = LyzrAdapter()
    assert lyzr.configured() is False
    result = lyzr.propose("Propose a rule for lateral_movement")
    assert result["fallback_used"] is True
    assert result["provider"] == "anvaya-local-fixture"
    assert result["content"] == {}


def test_lyzr_configured_makes_live_call(monkeypatch):
    """When configured, Lyzr POSTs to its API and parses the JSON response."""
    monkeypatch.setattr(settings, "lyzr_api_key", "test-lyzr-key")
    monkeypatch.setattr(settings, "lyzr_base_url", "https://api.lyzr.test")

    fake_response = MagicMock()
    fake_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '{"name": "Rule-1", "description": "Detects lateral movement"}'
                }
            }
        ]
    }
    fake_response.raise_for_status.return_value = None

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return fake_response

    monkeypatch.setattr("httpx.post", fake_post)

    lyzr = LyzrAdapter()
    assert lyzr.healthy() is True
    result = lyzr.propose("Propose a rule for lateral_movement")
    assert result["provider"] == "lyzr"
    assert result["fallback_used"] is False
    assert result["content"]["name"] == "Rule-1"
    assert len(calls) == 1
    assert calls[0][0][0] == "https://api.lyzr.test/llm/chat/completions"


def test_tavily_configured_makes_live_call(monkeypatch):
    """When configured, Tavily POSTs to the real API and parses the response."""
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")

    fake_response = MagicMock()
    fake_response.text = (
        '{"results": [{"title": "Tavily Result", "url": "https://example.com", '
        '"content": "summary", "score": 0.95}]}'
    )
    fake_response.json.return_value = {
        "results": [
            {
                "title": "Tavily Result",
                "url": "https://example.com",
                "content": "summary",
                "score": 0.95,
            }
        ]
    }
    fake_response.raise_for_status.return_value = None

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return fake_response

    monkeypatch.setattr("httpx.post", fake_post)

    tavily = TavilyAdapter()
    assert tavily.configured() is True
    result = tavily.search("lateral_movement")
    assert result["provider"] == "tavily"
    assert result["record_count"] == 1
    assert result["records"][0]["title"] == "Tavily Result"
    assert len(calls) == 1
    assert calls[0][1]["json"]["api_key"] == "test-key"


def test_n8n_configured_makes_live_call(monkeypatch):
    """When configured, n8n POSTs to the real webhook and reports triggered."""
    monkeypatch.setattr(settings, "n8n_webhook_url", "https://n8n.test/webhook/abc")

    fake_response = MagicMock()
    fake_response.text = '{"status": "ok"}'
    fake_response.json.return_value = {"status": "ok"}
    fake_response.raise_for_status.return_value = None

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return fake_response

    monkeypatch.setattr("httpx.post", fake_post)

    n8n = N8NAdapter()
    assert n8n.configured() is True
    result = n8n.trigger("incident_detected", {"incident_id": "INC-123"})
    assert result["status"] == "triggered"
    assert result["provider"] == "n8n"
    assert result["fallback_used"] is False
    assert len(calls) == 1
    assert calls[0][0][0] == "https://n8n.test/webhook/abc"
