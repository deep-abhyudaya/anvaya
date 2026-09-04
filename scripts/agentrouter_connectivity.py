#!/usr/bin/env python3
"""Manual backend connectivity test for AgentRouter.

This script uses ANVAYA's provider abstraction to verify that the configured
AGENTROUTER_API_KEY can reach each registered AgentRouter model. It never logs
the secret key. Run it from the repo root with:

    .venv/bin/python scripts/agentrouter_connectivity.py

The script reports HTTP-equivalent status, provider error category, and request
ID for each check. A non-zero exit code is returned if any model fails.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Any

from anvaya.agent.profiles import default_models
from anvaya.config import settings
from anvaya.llm.providers import (
    ModelProvider,
    NormalizedModelResponse,
    get_model_provider_for_config,
)


def log_check(
    *,
    model: str,
    protocol: str,
    base_url: str,
    status: int | None,
    category: str,
    request_id: str,
    error: str,
    text: str,
) -> None:
    """Emit a safe, one-line diagnostic."""
    print(
        f"[agentrouter] model={model} protocol={protocol} base_url={base_url} "
        f"status={status} category={category} request_id={request_id} "
        f"error={error!r} text={text!r}"
    )


def _iter_stream(provider: ModelProvider, messages: list[dict[str, Any]]) -> str:
    """Consume a streaming response and return the full text."""
    result = provider.chat_completion(messages, stream=True)
    if not isinstance(result, Iterator):
        return result.text or result.error or ""
    text_parts: list[str] = []
    for chunk in result:
        text_parts.append(chunk.text)
    return "".join(text_parts)


def main() -> int:
    if not settings.agentrouter_api_key:
        print("[agentrouter] AGENTROUTER_API_KEY is not set; skipping connectivity test.")
        return 0

    agentrouter_models = [m for m in default_models() if m.provider == "agentrouter"]
    if not agentrouter_models:
        print("[agentrouter] No AgentRouter models are registered.")
        return 1

    all_ok = True
    for model in agentrouter_models:
        provider = get_model_provider_for_config(model)
        if provider is None:
            log_check(
                model=model.model,
                protocol=model.protocol,
                base_url=model.base_url or "",
                status=None,
                category="AGENTROUTER_PROVIDER_NOT_FOUND",
                request_id="",
                error="No provider implementation for this model config",
                text="",
            )
            all_ok = False
            continue

        response = _single_response(
            provider,
            [{"role": "user", "content": "Reply with exactly the word OK."}],
        )
        log_check(
            model=model.model,
            protocol=model.protocol,
            base_url=provider.base_url,
            status=_status_from_category(response.category),
            category=response.category,
            request_id=response.request_id,
            error=response.error,
            text=response.text.strip()[:80],
        )
        if response.error:
            all_ok = False
            continue

        stream_text = _iter_stream(
            provider,
            [{"role": "user", "content": "Count 1, 2, 3."}],
        )
        print(
            f"[agentrouter] stream model={model.model} text={stream_text!r}"
        )

        tools = [
            {
                "name": "get_status",
                "description": "Return the status of a service.",
                "input_schema": {
                    "type": "object",
                    "properties": {"service": {"type": "string"}},
                    "required": ["service"],
                },
            }
        ]
        tool_response = _single_response(
            provider,
            [
                {
                    "role": "user",
                    "content": "What is the status of the database? Use get_status.",
                }
            ],
            tools=tools,
        )
        print(
            f"[agentrouter] tool model={model.model} "
            f"tool_calls={tool_response.tool_calls} "
            f"error={tool_response.error!r}"
        )
        if tool_response.tool_calls:
            print(
                f"[agentrouter] tool_result model={model.model} "
                f"name={tool_response.tool_calls[0]['name']} "
                f"args={tool_response.tool_calls[0]['arguments']}"
            )

    return 0 if all_ok else 1


def _single_response(
    provider: ModelProvider,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> NormalizedModelResponse:
    result = provider.chat_completion(messages, tools=tools)
    if isinstance(result, Iterator):
        return NormalizedModelResponse(
            error="Unexpected streaming response for non-streaming call",
            provider=provider.name,
            model=provider.model,
        )
    return result


def _status_from_category(category: str) -> int | None:
    """Best-effort mapping from our error category to an HTTP status code."""
    mapping = {
        "AGENTROUTER_AUTH_FAILED": 401,
        "AGENTROUTER_NOT_CONFIGURED": None,
        "AGENTROUTER_RATE_LIMITED": 429,
        "AGENTROUTER_MODEL_NOT_FOUND": 404,
        "AGENTROUTER_PROTOCOL_ERROR": 400,
        "AGENTROUTER_TIMEOUT": 408,
        "AGENTROUTER_PROVIDER_ERROR": 502,
    }
    for key, status in mapping.items():
        if key in category:
            return status
    return None


if __name__ == "__main__":
    sys.exit(main())
