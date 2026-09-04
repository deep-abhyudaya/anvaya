"""Provider adapters and health checks for optional external services.

Each adapter exposes:
- name
- configured() -> bool
- healthy() -> bool
- fallback_message() -> str

The core ANVAYA local executor is always available and is the final fallback.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from anvaya.config import settings
from anvaya.logging import get_logger

logger = get_logger("anvaya.agent.adapters")


class ProviderAdapter:
    """Base class for an external provider adapter."""

    name: str = "unknown"
    env_var: str = ""
    fallback_reason: str = ""

    def configured(self) -> bool:
        """Return True if the provider has credentials/configuration."""
        if not self.env_var:
            return False
        return bool(os.environ.get(self.env_var))

    def healthy(self) -> bool:
        """Return True if the provider is reachable/usable.

        Default implementation: configured. Subclasses can perform live checks.
        """
        return self.configured()

    def availability(self) -> str:
        """Return truthful availability: available, configured, unavailable, fallback."""
        if not self.configured():
            return "unavailable"
        if self.healthy():
            return "available"
        return "fallback"

    def fallback_message(self) -> str:
        return f"{self.name} unavailable — using ANVAYA local fallback"


class SwytchcodeAdapter(ProviderAdapter):
    """Swytchcode external tool/API integration layer."""

    name = "Swytchcode"
    env_var = "SWYTCHCODE_API_KEY"
    fallback_reason = "Swytchcode not configured"

    def configured(self) -> bool:
        return bool(settings.swytchcode_api_key and settings.swytchcode_base_url)

    def healthy(self) -> bool:
        return False

    def execute(self, tool: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Attempt to execute a tool via Swytchcode, or fall back to local."""
        if not self.healthy():
            return {
                "status": "unavailable",
                "provider": "anvaya",
                "fallback_used": True,
                "fallback_reason": self.fallback_message(),
            }
        try:
            url = f"{settings.swytchcode_base_url.rstrip('/')}/v1/execute"
            response = httpx.post(
                url,
                headers={"Authorization": f"Bearer {settings.swytchcode_api_key}"},
                json={"tool": tool, "inputs": inputs},
                timeout=15.0,
            )
            response.raise_for_status()
            return {
                "status": "success",
                "provider": "swytchcode",
                "fallback_used": False,
                "result": response.json(),
            }
        except Exception as exc:
            logger.warning("swytchcode.execute_failed", error=str(exc))
            return {
                "status": "failed",
                "provider": "anvaya",
                "fallback_used": True,
                "fallback_reason": f"Swytchcode request failed: {exc}",
            }


class TavilyAdapter(ProviderAdapter):
    """Tavily live web/threat-intelligence search."""

    name = "Tavily"
    env_var = "TAVILY_API_KEY"
    fallback_reason = "Tavily not configured"

    def configured(self) -> bool:
        return bool(settings.tavily_api_key)

    def healthy(self) -> bool:
        return self.configured()

    def search(
        self, indicator: str, indicator_type: str = "auto", query_context: str = ""
    ) -> dict[str, Any]:
        """Search threat intelligence via Tavily or return a labeled local fixture."""
        if not self.healthy():
            return {
                "indicator": indicator,
                "source": "anvaya-local-fixture",
                "provider": "anvaya-local-fixture",
                "note": "Tavily not configured; returning curated fixture",
                "confidence": "low",
                "records": [
                    {
                        "type": indicator_type or "technique",
                        "value": indicator,
                        "source": "ANVAYA scenario catalog",
                        "confidence": 0.85,
                    }
                ],
            }

        try:
            response = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.tavily_api_key,
                    "query": query_context or f"threat intelligence {indicator}",
                    "search_depth": "basic",
                    "max_results": 5,
                },
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            return {
                "indicator": indicator,
                "source": "tavily",
                "provider": "tavily",
                "records": [
                    {
                        "type": indicator_type or "web",
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "summary": r.get("content", ""),
                        "relevance": r.get("score", 0.0),
                    }
                    for r in results
                ],
                "record_count": len(results),
            }
        except Exception as exc:
            logger.warning("tavily.search_failed", error=str(exc))
            return {
                "indicator": indicator,
                "source": "anvaya-local-fixture",
                "provider": "anvaya-local-fixture",
                "note": f"Tavily request failed: {exc}; using local fixture",
                "confidence": "low",
                "records": [
                    {
                        "type": indicator_type or "technique",
                        "value": indicator,
                        "source": "ANVAYA scenario catalog",
                        "confidence": 0.85,
                    }
                ],
            }


class LyzrAdapter(ProviderAdapter):
    """Lyzr agent-platform orchestration."""

    name = "lyzr"
    env_var = "LYZR_API_KEY"
    fallback_reason = "Lyzr not configured"

    def configured(self) -> bool:
        return bool(settings.lyzr_api_key)

    def healthy(self) -> bool:
        return self.configured()

    def propose(self, prompt: str, response_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ask Lyzr to propose a structured output from a prompt."""
        if not self.healthy():
            return {
                "provider": "anvaya-local-fixture",
                "source": "anvaya-local-fixture",
                "note": "Lyzr not configured; returning deterministic fallback",
                "fallback_used": True,
                "fallback_reason": self.fallback_message(),
                "content": {},
            }

        base_url = settings.lyzr_base_url or "https://api.lyzr.com/v2"
        try:
            response = httpx.post(
                f"{base_url}/llm/chat/completions",
                headers={
                    "Authorization": f"ApiKey {settings.lyzr_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "{}")
            parsed = json.loads(content) if isinstance(content, str) else content
            return {
                "provider": "lyzr",
                "source": "lyzr",
                "note": "Lyzr reasoning returned successfully",
                "fallback_used": False,
                "content": parsed,
            }
        except Exception as exc:
            logger.warning("lyzr.propose_failed", error=str(exc))
            return {
                "provider": "anvaya-local-fixture",
                "source": "anvaya-local-fixture",
                "note": f"Lyzr request failed: {exc}; using fallback",
                "fallback_used": True,
                "fallback_reason": f"Lyzr request failed: {exc}",
                "content": {},
            }


class N8NAdapter(ProviderAdapter):
    """n8n workflow automation."""

    name = "n8n"
    env_var = "N8N_WEBHOOK_URL"
    fallback_reason = "n8n not configured"

    def configured(self) -> bool:
        return bool(settings.n8n_webhook_url)

    def healthy(self) -> bool:
        return self.configured()

    def trigger(self, workflow: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to the n8n webhook or record a local no-op fallback."""
        if not self.healthy():
            return {
                "workflow": workflow,
                "status": "recorded",
                "source": "anvaya-local-handler",
                "note": "n8n not configured; workflow recorded locally",
                "fallback_used": True,
                "fallback_reason": self.fallback_message(),
            }

        url = settings.n8n_webhook_url
        body = {
            "workflow": workflow,
            "payload": payload,
            "timestamp": _now_iso(),
        }
        try:
            response = httpx.post(
                url,
                json=body,
                timeout=15.0,
            )
            response.raise_for_status()
            return {
                "workflow": workflow,
                "status": "triggered",
                "provider": "n8n",
                "source": "n8n",
                "note": "n8n workflow triggered",
                "response": response.json() if response.text else {},
                "fallback_used": False,
            }
        except Exception as exc:
            logger.warning("n8n.trigger_failed", error=str(exc))
            return {
                "workflow": workflow,
                "status": "recorded",
                "source": "anvaya-local-handler",
                "note": f"n8n request failed: {exc}; workflow recorded locally",
                "fallback_used": True,
                "fallback_reason": f"n8n request failed: {exc}",
            }


class GmailAdapter(ProviderAdapter):
    """Gmail API integration for SOC notifications."""

    name = "gmail"
    env_var = "GMAIL_CREDENTIALS_PATH"
    fallback_reason = "Gmail not configured or dependencies not installed"

    def configured(self) -> bool:
        return settings.is_gmail_enabled()

    def healthy(self) -> bool:
        return self.configured()

    def _build_service(self):
        """Authenticate and return a Gmail API service resource."""
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        scopes = ["https://www.googleapis.com/auth/gmail.send"]
        creds = Credentials.from_service_account_file(
            settings.gmail_credentials_path,
            scopes=scopes,
        )
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def send(self, to: str, subject: str, body: str) -> dict[str, Any]:
        """Send a notification email via Gmail API or record a local fallback."""
        if not self.healthy():
            return {
                "to": to,
                "subject": subject,
                "status": "recorded",
                "provider": "anvaya-local-handler",
                "source": "anvaya-local-handler",
                "note": "Gmail not configured; email recorded locally",
                "fallback_used": True,
                "fallback_reason": self.fallback_message(),
                "body": body,
            }

        try:
            import base64
            from email.mime.text import MIMEText

            service = self._build_service()
            message = MIMEText(body, "plain", "utf-8")
            message["to"] = to
            message["from"] = settings.gmail_from_email
            message["subject"] = subject
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            return {
                "to": to,
                "subject": subject,
                "status": "sent",
                "provider": "gmail",
                "source": "gmail",
                "note": f"Email sent to {to}",
                "fallback_used": False,
            }
        except Exception as exc:
            logger.warning("gmail.send_failed", error=str(exc))
            return {
                "to": to,
                "subject": subject,
                "status": "recorded",
                "provider": "anvaya-local-handler",
                "source": "anvaya-local-handler",
                "note": f"Gmail send failed: {exc}; email recorded locally",
                "fallback_used": True,
                "fallback_reason": f"Gmail send failed: {exc}",
                "body": body,
            }


class OpenAIAdapter(ProviderAdapter):
    """OpenAI LLM integration used inside Sentinel."""

    name = "OpenAI"
    env_var = "OPENAI_API_KEY"
    fallback_reason = "OpenAI not configured"

    def configured(self) -> bool:
        return bool(settings.openai_api_key)

    def healthy(self) -> bool:
        return self.configured()


class OpenRouterAdapter(ProviderAdapter):
    """OpenRouter integration for free and paid models."""

    name = "OpenRouter"
    env_var = "OPENROUTER_API_KEY"
    fallback_reason = "OpenRouter not configured"

    def configured(self) -> bool:
        return bool(settings.openrouter_api_key)

    def healthy(self) -> bool:
        return self.configured()


class AnvayaLocalAdapter(ProviderAdapter):
    """Core ANVAYA local executor. Always available."""

    name = "ANVAYA"
    env_var = ""
    fallback_reason = ""

    def configured(self) -> bool:
        return True

    def healthy(self) -> bool:
        return True

    def availability(self) -> str:
        return "available"


ADAPTERS: dict[str, ProviderAdapter] = {
    "swytchcode": SwytchcodeAdapter(),
    "tavily": TavilyAdapter(),
    "lyzr": LyzrAdapter(),
    "n8n": N8NAdapter(),
    "gmail": GmailAdapter(),
    "openai": OpenAIAdapter(),
    "openrouter": OpenRouterAdapter(),
    "anvaya": AnvayaLocalAdapter(),
}


def get_adapter(name: str) -> ProviderAdapter | None:
    """Get an adapter by provider name."""
    return ADAPTERS.get(name.lower())


def adapter_status() -> list[dict[str, Any]]:
    """Return the current status of all adapters."""
    return [
        {
            "name": a.name,
            "provider": key,
            "configured": a.configured(),
            "healthy": a.healthy(),
            "availability": a.availability(),
            "fallback_message": a.fallback_message(),
        }
        for key, a in ADAPTERS.items()
    ]


def all_provider_status() -> list[dict[str, Any]]:
    """Return the status of every tool and model provider.

    Tool providers come from the adapter registry. The active model providers
    exposed to the UI are NVIDIA, AgentRouter, OpenCode, OpenRouter, SeekAI,
    GMI Cloud, Empero, and ANVAYA local. Direct OpenAI, Anthropic, and Lyzr
    providers are intentionally not listed.
    """
    from anvaya.llm.providers import get_model_provider

    status = list(adapter_status())

    for key in [
        "nvidia",
        "agentrouter",
        "opencode",
        "openrouter",
        "seekai",
        "gmicloud",
        "empero",
        "anvaya",
    ]:
        provider = get_model_provider(key)
        if not provider:
            continue

        configured = provider.configured()
        healthy = provider.healthy()
        availability = provider.availability()

        privacy_class = "standard"
        gateway_type = "inference gateway"
        access_class = "standard"
        protocol = "openai-compatible"
        if key == "seekai":
            gateway_type = "aggregator"
        if key == "gmicloud":
            access_class = "standard"
        if key == "empero":
            privacy_class = "public_community_endpoint"
            access_class = "community_free"
            gateway_type = "community endpoint"

        status.append(
            {
                "name": provider.name,
                "provider": key,
                "configured": configured,
                "healthy": healthy,
                "availability": availability,
                "fallback_message": "",
                "kind": "model",
                "privacy_class": privacy_class,
                "access_class": access_class,
                "gateway_type": gateway_type,
                "protocol": protocol,
                "base_url": getattr(provider, "base_url", ""),
                "model_count": 0,
            }
        )

    try:
        from anvaya.agent.profiles import default_models

        all_models = default_models()
        for entry in status:
            if entry.get("kind") == "model":
                entry["model_count"] = sum(
                    1 for m in all_models if m.provider == entry["provider"]
                )
    except Exception as exc:
        logger.warning("all_provider_status.model_count_failed", error=str(exc))

    return status


def select_provider(tool_provider: str, tool_fallback: str) -> tuple[str, str]:
    """Select the actual provider to use for a tool.

    Returns (provider, fallback_reason). If the primary is unavailable, the
    fallback is used with a recorded reason.
    """
    adapter = get_adapter(tool_provider)
    if adapter and adapter.healthy():
        return tool_provider, ""

    fallback_adapter = get_adapter(tool_fallback)
    if fallback_adapter and fallback_adapter.healthy():
        return (
            tool_fallback,
            adapter.fallback_message() if adapter else f"{tool_provider} unavailable",
        )

    return "anvaya", f"{tool_provider} unavailable and fallback {tool_fallback} unavailable"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
