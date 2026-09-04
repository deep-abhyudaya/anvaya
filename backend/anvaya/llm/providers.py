"""Model provider abstraction with NVIDIA NIM, AgentRouter, and local fallback.

Each provider is an OpenAI- or Anthropic-compatible chat completion client for
tool use and structured outputs. Results are normalized so the rest of the agent
layer is provider-agnostic.
"""

from __future__ import annotations

import json
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from time import perf_counter
from typing import TYPE_CHECKING, Any

from anthropic import (
    Anthropic,
)
from anthropic import (
    APIError as AnthropicAPIError,
)
from anthropic import (
    AuthenticationError as AnthropicAuthenticationError,
)
from anthropic import (
    BadRequestError as AnthropicBadRequestError,
)
from anthropic import (
    NotFoundError as AnthropicNotFoundError,
)
from anthropic import (
    RateLimitError as AnthropicRateLimitError,
)
from openai import (
    APIError,
    APIStatusError,
    AuthenticationError,
    BadRequestError,
    NotFoundError,
    OpenAI,
    RateLimitError,
)

from anvaya.config import settings
from anvaya.logging import get_logger

if TYPE_CHECKING:
    from anvaya.agent.schemas import ModelConfig

logger = get_logger("anvaya.llm.providers")


class RateLimiter:
    """Token-bucket rate limiter for provider API calls.

    A bucket with ``capacity`` tokens is refilled at ``rate`` tokens per second.
    ``acquire()`` blocks until a token is available unless ``blocking=False``,
    in which case it returns ``False`` immediately.
    """

    def __init__(self, rpm: float = 40.0, burst: int | None = None):
        self.rate = rpm / 60.0
        self.capacity = float(burst if burst is not None else max(1, int(rpm)))
        self._tokens = float(self.capacity)
        self._last_update = time.monotonic()
        self._lock = threading.Lock()

    def _add_tokens(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_update
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_update = now

    def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        """Acquire one token. Blocks by default."""
        start = time.monotonic()
        while True:
            with self._lock:
                self._add_tokens()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                deficit = 1.0 - self._tokens

            if not blocking:
                return False

            remaining = None
            if timeout is not None:
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    return False

            wait = deficit / self.rate if self.rate > 0 else 1.0
            if remaining is not None:
                wait = min(wait, remaining)
            wait = max(0.001, wait)
            time.sleep(wait)


class NormalizedModelResponse:
    """Provider-agnostic model output."""

    def __init__(
        self,
        text: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
        finish_reason: str = "",
        usage: dict[str, Any] | None = None,
        provider: str = "",
        model: str = "",
        streaming_supported: bool = False,
        error: str = "",
        category: str = "",
        request_id: str = "",
    ):
        self.text = text
        self.tool_calls = tool_calls or []
        self.finish_reason = finish_reason or ("tool_calls" if tool_calls else "stop")
        self.usage = usage or {}
        self.provider = provider
        self.model = model
        self.streaming_supported = streaming_supported
        self.error = error
        self.category = category
        self.request_id = request_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "tool_calls": self.tool_calls,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "provider": self.provider,
            "model": self.model,
            "category": self.category,
            "request_id": self.request_id,
            "streaming_supported": self.streaming_supported,
            "error": self.error,
        }


def _join_stream_text(existing: str, delta: str) -> str:
    """Join streaming text chunks, inserting a space when the provider drops them.

    Some OpenAI/Anthropic-compatible endpoints return token deltas without the
    leading space that standard tokenizers include. This causes the streamed text
    to be concatenated as "Theagentwill" instead of "The agent will". We insert
    a single space when two alphanumeric spans would otherwise be joined, and
    after sentence-terminating punctuation before the next alphanumeric span.
    """
    if not existing or not delta:
        return delta
    if existing[-1].isspace() or delta[0].isspace():
        return delta
    if existing[-1].isalnum() and delta[0].isalnum():
        return f" {delta}"
    if existing[-1] in ",.;:!?" and delta[0].isalnum():
        return f" {delta}"
    return delta


class ModelProvider(ABC):
    """Abstract model provider."""

    name: str = "unknown"

    @abstractmethod
    def configured(self) -> bool:
        """Return True if the provider has credentials and a model configured."""
        ...

    def healthy(self) -> bool:
        """Return True if the provider is reachable.

        The default is conservative: credentials present. Subclasses can perform
        live health checks when it is safe to do so.
        """
        return self.configured()

    def availability(self) -> str:
        if not self.configured():
            return "unavailable"
        if self.healthy():
            return "available"
        return "configured"

    @abstractmethod
    def capabilities(self) -> list[str]: ...

    @abstractmethod
    def supports_capability(self, capability: str) -> bool: ...

    @abstractmethod
    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        response_format: dict[str, str] | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> NormalizedModelResponse | Iterator[NormalizedModelResponse]:
        """Run a chat completion and return a normalized response.

        When ``stream=True`` an iterator of partial deltas is returned.
        """
        ...




class OpenAICompatibleProvider(ModelProvider):
    """Base for OpenAI-compatible endpoints."""

    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        model: str,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        capabilities: list[str] | None = None,
        rate_limiter: RateLimiter | None = None,
        supports_multimodal: bool = False,
    ):
        self.name = name
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._capabilities = capabilities or ["chat", "tools", "streaming", "structured-outputs"]
        if supports_multimodal and "multimodal" not in self._capabilities:
            self._capabilities.append("multimodal")
        self.rate_limiter = rate_limiter
        self._client: OpenAI | None = None

    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def _get_client(self) -> OpenAI:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "api_key": self.api_key,
                "timeout": self.timeout,
                "max_retries": self.max_retries,
            }
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def _request_id_from_exc(self, exc: Exception) -> str:
        response = getattr(exc, "response", None)
        if response is not None:
            return (
                response.headers.get("x-request-id")
                or response.headers.get("request-id")
                or ""
            )
        if hasattr(exc, "request_id"):
            return str(exc.request_id or "")
        return ""

    def _map_openai_error(self, exc: Exception) -> NormalizedModelResponse:
        """Classify OpenAI-compatible provider errors with a provider-scoped category."""
        status: int | None = None
        category = f"{self.name.upper()}_PROVIDER_ERROR"

        auth_or_401 = isinstance(exc, AuthenticationError) or (
            isinstance(exc, APIStatusError) and getattr(exc, "status_code", None) == 401
        )
        if auth_or_401:
            category = f"{self.name.upper()}_AUTH_FAILED"
            status = 401
        elif isinstance(exc, NotFoundError):
            category = f"{self.name.upper()}_MODEL_NOT_FOUND"
            status = 404
        elif isinstance(exc, BadRequestError):
            category = f"{self.name.upper()}_PROTOCOL_ERROR"
            status = 400
        elif isinstance(exc, RateLimitError):
            category = f"{self.name.upper()}_RATE_LIMITED"
            status = 429
        elif isinstance(exc, APIStatusError):
            status = getattr(exc, "status_code", None)
            if status in (408, 504):
                category = f"{self.name.upper()}_TIMEOUT"
            elif status == 401:
                category = f"{self.name.upper()}_AUTH_FAILED"
            elif status == 404:
                category = f"{self.name.upper()}_MODEL_NOT_FOUND"
            elif status == 429:
                category = f"{self.name.upper()}_RATE_LIMITED"

        message = str(exc)
        body = getattr(exc, "body", None)
        if body and isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict) and err.get("message"):
                message = err["message"]
            elif body.get("msg"):
                message = body["msg"]

        logger.warning(
            f"{self.name}.error",
            category=category,
            status=status,
            model=self.model,
            base_url=self.base_url,
            request_id=self._request_id_from_exc(exc),
            error=message,
        )
        return NormalizedModelResponse(
            error=f"{self.name} {category}: {message}",
            provider=self.name,
            model=self.model,
            category=category,
            request_id=self._request_id_from_exc(exc),
        )

    def capabilities(self) -> list[str]:
        return list(self._capabilities)

    def supports_capability(self, capability: str) -> bool:
        return capability in self._capabilities

    def _format_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        openai_tools = []
        for t in tools:
            parameters = t.get("input_schema") or t.get("parameters", {})
            if isinstance(parameters, list):
                properties = {}
                required = []
                for p in parameters:
                    properties[p["name"]] = {
                        "type": p.get("type", "string"),
                        "description": p.get("description", ""),
                    }
                    if p.get("enum"):
                        properties[p["name"]]["enum"] = p["enum"]
                    if p.get("required", True):
                        required.append(p["name"])
                parameters = {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": parameters,
                    },
                }
            )
        return openai_tools

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        response_format: dict[str, str] | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> NormalizedModelResponse | Iterator[NormalizedModelResponse]:
        if not self.configured():
            return NormalizedModelResponse(
                error=f"{self.name} is not configured",
                provider=self.name,
                model=self.model,
                category=f"{self.name.upper()}_NOT_CONFIGURED",
            )

        if self.rate_limiter and not self.rate_limiter.acquire(blocking=True, timeout=60.0):
            return NormalizedModelResponse(
                error=f"{self.name} rate limit: request timed out waiting for capacity",
                provider=self.name,
                model=self.model,
            )

        client = self._get_client()
        if timeout:
            client.timeout = timeout

        params: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }
        openai_tools = self._format_tools(tools)
        if openai_tools:
            params["tools"] = openai_tools
            params["tool_choice"] = "auto"
        if response_format:
            params["response_format"] = response_format

        try:
            started = perf_counter()
            if stream:
                return self._stream_response(client, params, started)
            return self._sync_response(client, params, started)
        except (
            RateLimitError,
            AuthenticationError,
            NotFoundError,
            BadRequestError,
            APIError,
        ) as exc:
            return self._map_openai_error(exc)
        except Exception as exc:
            logger.warning(f"{self.name}.completion_error", error=str(exc))
            return NormalizedModelResponse(
                error=f"{self.name} completion error: {exc}",
                provider=self.name,
                model=self.model,
                category=f"{self.name.upper()}_PROVIDER_ERROR",
            )

    def _sync_response(
        self, client: OpenAI, params: dict[str, Any], started: float
    ) -> NormalizedModelResponse:
        response = client.chat.completions.create(**params)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        message = response.choices[0].message
        usage = dict(response.usage) if response.usage else {}
        usage["duration_ms"] = duration_ms

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments
                try:
                    parsed = json.loads(args) if isinstance(args, str) else args
                except json.JSONDecodeError:
                    parsed = {}
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": parsed,
                    }
                )

        return NormalizedModelResponse(
            text=message.content or "",
            tool_calls=tool_calls,
            finish_reason=response.choices[0].finish_reason or "",
            usage=usage,
            provider=self.name,
            model=response.model or self.model,
            streaming_supported=self.supports_capability("streaming"),
        )

    def _stream_response(
        self, client: OpenAI, params: dict[str, Any], started: float
    ) -> Iterator[NormalizedModelResponse]:
        full_text = ""
        tool_calls: dict[str, dict[str, Any]] = {}
        model = self.model
        try:
            for chunk in client.chat.completions.create(**params):
                if chunk.model:
                    model = chunk.model
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta and delta.content:
                    chunk = _join_stream_text(full_text, delta.content)
                    full_text += chunk
                    yield NormalizedModelResponse(
                        text=chunk,
                        provider=self.name,
                        model=model,
                        streaming_supported=True,
                        finish_reason=choice.finish_reason or "",
                    )
                if delta and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = str(tc.index)
                        if idx not in tool_calls:
                            tool_calls[idx] = {
                                "id": tc.id or f"call_{idx}",
                                "name": tc.function.name or "",
                                "arguments": tc.function.arguments or "",
                            }
                        else:
                            existing = tool_calls[idx]
                            if tc.id:
                                existing["id"] = tc.id
                            if tc.function.name:
                                existing["name"] = tc.function.name
                            if tc.function.arguments:
                                existing["arguments"] += tc.function.arguments
        except (
            RateLimitError,
            AuthenticationError,
            NotFoundError,
            BadRequestError,
            APIError,
        ) as exc:
            yield self._map_openai_error(exc)
            return
        except Exception as exc:
            logger.warning(f"{self.name}.stream_error", error=str(exc))
            yield NormalizedModelResponse(
                error=f"{self.name} stream error: {exc}",
                provider=self.name,
                model=model,
                category=f"{self.name.upper()}_PROVIDER_ERROR",
            )
            return

        parsed_tool_calls = []
        for tc in tool_calls.values():
            try:
                args = (
                    json.loads(tc["arguments"])
                    if isinstance(tc["arguments"], str)
                    else tc["arguments"]
                )
            except json.JSONDecodeError:
                args = {}
            parsed_tool_calls.append({"id": tc["id"], "name": tc["name"], "arguments": args})

        duration_ms = round((perf_counter() - started) * 1000, 2)
        yield NormalizedModelResponse(
            text="",
            tool_calls=parsed_tool_calls,
            finish_reason="tool_calls" if parsed_tool_calls else "stop",
            usage={"duration_ms": duration_ms},
            provider=self.name,
            model=model,
            streaming_supported=True,
        )


class NVIDIAProvider(OpenAICompatibleProvider):
    """NVIDIA NIM model provider (OpenAI-compatible endpoint)."""

    def __init__(self, model: str | None = None, supports_multimodal: bool = False) -> None:
        super().__init__(
            name="nvidia",
            api_key=settings.nvidia_api_key,
            model=model or settings.nvidia_model,
            base_url=settings.nvidia_base_url or "https://integrate.api.nvidia.com/v1",
            timeout=settings.nvidia_timeout_ms / 1000,
            max_retries=settings.nvidia_max_retries,
            capabilities=["chat", "tools", "streaming", "structured-outputs"],
            rate_limiter=RateLimiter(rpm=float(settings.nvidia_rate_limit_rpm)),
            supports_multimodal=supports_multimodal,
        )


class OpenAIProvider(OpenAICompatibleProvider):
    """OpenAI model provider."""

    def __init__(self, model: str | None = None, supports_multimodal: bool = False) -> None:
        super().__init__(
            name="openai",
            api_key=settings.openai_api_key,
            model=model or settings.openai_model,
            capabilities=["chat", "tools", "streaming", "structured-outputs"],
            supports_multimodal=supports_multimodal,
        )


class OpenCodeProvider(OpenAICompatibleProvider):
    """OpenCode provider (OpenAI-compatible, free-tier through Zen)."""

    def __init__(self, model: str | None = None, supports_multimodal: bool = False) -> None:
        from anvaya.llm.opencode_catalog import get_opencode_model_configs

        resolved_model = model or settings.opencode_model
        if not resolved_model:
            free = get_opencode_model_configs()
            resolved_model = free[0]["model"] if free else ""
        super().__init__(
            name="opencode",
            api_key=settings.opencode_api_key,
            model=resolved_model,
            base_url=settings.opencode_base_url or "https://opencode.ai/zen/v1",
            timeout=settings.opencode_timeout_ms / 1000,
            max_retries=2,
            capabilities=["chat", "tools", "streaming", "structured-outputs"],
            supports_multimodal=supports_multimodal,
        )

    def _get_client(self) -> OpenAI:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "api_key": self.api_key,
                "timeout": self.timeout,
                "max_retries": self.max_retries,
                "base_url": self.base_url,
            }
            self._client = OpenAI(**kwargs)
        return self._client

    def _is_rate_limited(self, response: NormalizedModelResponse) -> bool:
        if not response.error:
            return False
        category = response.category or ""
        if "RATE_LIMITED" in category:
            return True
        return "rate limit" in response.error.lower() or "429" in response.error

    def _stream_with_retry(self, **kwargs: Any) -> Iterator[NormalizedModelResponse]:
        for attempt in range(3):
            iterator = super().chat_completion(**kwargs)
            try:
                first = next(iterator)
            except StopIteration:
                return
            if self._is_rate_limited(first):
                logger.warning("opencode.rate_limited_retry", attempt=attempt + 1)
                time.sleep(min(1.5 * (2 ** attempt), 8.0))
                continue
            yield first
            yield from iterator
            return

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        response_format: dict[str, str] | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> NormalizedModelResponse | Iterator[NormalizedModelResponse]:
        if stream:
            return self._stream_with_retry(
                messages=messages,
                tools=tools,
                temperature=temperature,
                response_format=response_format,
                stream=True,
                timeout=timeout,
            )

        for attempt in range(3):
            result = super().chat_completion(
                messages,
                tools=tools,
                temperature=temperature,
                response_format=response_format,
                stream=False,
                timeout=timeout,
            )
            if isinstance(result, Iterator):
                return result
            if self._is_rate_limited(result):
                logger.warning("opencode.rate_limited_retry", attempt=attempt + 1)
                time.sleep(min(1.5 * (2 ** attempt), 8.0))
                continue
            return result
        return result


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter provider (OpenAI-compatible, supports free tier models)."""

    def __init__(self, model: str | None = None, supports_multimodal: bool = False) -> None:
        from anvaya.llm.openrouter_catalog import get_free_openrouter_models

        resolved_model = model or settings.openrouter_model
        if not resolved_model:
            free = get_free_openrouter_models()
            resolved_model = free[0]["model"] if free else "openai/gpt-4o-mini"
        super().__init__(
            name="openrouter",
            api_key=settings.openrouter_api_key,
            model=resolved_model,
            base_url="https://openrouter.ai/api/v1",
            timeout=settings.openrouter_timeout_ms / 1000,
            max_retries=2,
            capabilities=["chat", "tools", "streaming", "structured-outputs"],
            supports_multimodal=supports_multimodal,
        )

    def _get_client(self) -> OpenAI:
        if self._client is None:
            kwargs: dict[str, Any] = {
                "api_key": self.api_key,
                "timeout": self.timeout,
                "max_retries": self.max_retries,
                "base_url": self.base_url,
                "default_headers": {
                    "HTTP-Referer": "http://localhost",
                    "X-Title": "ANVAYA",
                },
            }
            self._client = OpenAI(**kwargs)
        return self._client

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        response_format: dict[str, str] | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> NormalizedModelResponse | Iterator[NormalizedModelResponse]:
        """Run a chat completion, falling back to openrouter/free on 403."""
        from collections.abc import Iterator

        original_model = self.model

        def _call(model: str, stream_flag: bool):
            self.model = model
            return super(OpenRouterProvider, self).chat_completion(
                messages,
                tools=tools,
                temperature=temperature,
                response_format=response_format,
                stream=stream_flag,
                timeout=timeout,
            )

        def _is_restricted(response_or_chunk) -> bool:
            error = getattr(response_or_chunk, "error", "") or ""
            if original_model == "openrouter/free":
                return False
            restricted_signals = [
                "403",
                "429",
                "rate limit",
                "rate-limit",
                "only available on agentic",
                "unavailable",
                "temporarily rate-limited",
                "limit_source",
            ]
            return any(signal in error for signal in restricted_signals)

        try:
            response = _call(original_model, stream)

            if not stream:
                if _is_restricted(response):
                    logger.warning(
                        "openrouter.403_fallback",
                        original=original_model,
                        fallback="openrouter/free",
                    )
                    return _call("openrouter/free", False)
                return response

            if not isinstance(response, Iterator):
                if _is_restricted(response):
                    return _call("openrouter/free", True)
                return response

            iterator = iter(response)
            try:
                first = next(iterator)
            except StopIteration:
                self.model = original_model
                return iter([])

            if _is_restricted(first):
                logger.warning(
                    "openrouter.403_fallback", original=original_model, fallback="openrouter/free"
                )
                self.model = original_model
                return _call("openrouter/free", True)

            def _rest():
                yield first
                for chunk in iterator:
                    yield chunk

            self.model = original_model
            return _rest()
        finally:
            self.model = original_model


class SeekAIProvider(OpenAICompatibleProvider):
    """SeekAI gateway (OpenAI-compatible, model-agnostic gateway)."""

    def __init__(self, model: str | None = None, supports_multimodal: bool = False) -> None:
        from anvaya.llm.seekai_catalog import get_seekai_model_configs

        resolved_model = model or settings.seekai_model
        if not resolved_model:
            configs = get_seekai_model_configs()
            available = [c for c in configs if c.get("availability") == "available"]
            resolved_model = (
                available[0]["model"]
                if available
                else (configs[0]["model"] if configs else "")
            )
        super().__init__(
            name="seekai",
            api_key=settings.seekai_api_key,
            model=resolved_model,
            base_url=settings.seekai_base_url or "https://seekai.cc/v1",
            timeout=settings.seekai_timeout_ms / 1000,
            max_retries=2,
            capabilities=["chat", "tools", "streaming", "structured-outputs"],
            rate_limiter=RateLimiter(rpm=float(settings.seekai_rate_limit_rpm)),
            supports_multimodal=supports_multimodal,
        )


class GMICloudProvider(OpenAICompatibleProvider):
    """GMI Cloud gateway (OpenAI-compatible inference gateway)."""

    def __init__(self, model: str | None = None, supports_multimodal: bool = False) -> None:
        from anvaya.llm.gmicloud_catalog import get_gmicloud_model_configs

        resolved_model = model or settings.gmicloud_model
        if not resolved_model:
            configs = get_gmicloud_model_configs()
            available = [c for c in configs if c.get("availability") == "available"]
            resolved_model = (
                available[0]["model"]
                if available
                else (configs[0]["model"] if configs else "")
            )
        super().__init__(
            name="gmicloud",
            api_key=settings.gmicloud_api_key,
            model=resolved_model,
            base_url=settings.gmicloud_base_url or "https://api.gmi-serving.com/v1",
            timeout=settings.gmicloud_timeout_ms / 1000,
            max_retries=2,
            capabilities=["chat", "tools", "streaming", "structured-outputs"],
            rate_limiter=RateLimiter(rpm=float(settings.gmicloud_rate_limit_rpm)),
            supports_multimodal=supports_multimodal,
        )


class EmperoProvider(OpenAICompatibleProvider):
    """Empero community endpoint (OpenAI-compatible public endpoint).

    The official endpoint documents an optional public token ``free``.  No
    user secret is required, but the endpoint logs prompts/completions for
    training, so it is always tagged with a public-community privacy class.
    """

    def __init__(self, model: str | None = None, supports_multimodal: bool = False) -> None:
        from anvaya.llm.empero_catalog import get_empero_model_configs

        resolved_model = model or settings.empero_model
        if not resolved_model:
            configs = get_empero_model_configs()
            resolved_model = configs[0]["model"] if configs else ""
        api_key = settings.empero_api_key or "free"
        if api_key == "disabled":
            resolved_model = ""
        super().__init__(
            name="empero",
            api_key="" if api_key == "disabled" else api_key,
            model=resolved_model,
            base_url=settings.empero_base_url or "https://free.empero.org/v1",
            timeout=settings.empero_timeout_ms / 1000,
            max_retries=2,
            capabilities=["chat", "tools", "streaming", "structured-outputs"],
            rate_limiter=RateLimiter(rpm=float(settings.empero_rate_limit_rpm)),
            supports_multimodal=supports_multimodal,
        )




class AgentRouterOpenAIProvider(OpenAICompatibleProvider):
    """AgentRouter OpenAI-compatible models (e.g. gpt-5.6-sol)."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        supports_multimodal: bool = False,
    ) -> None:
        from anvaya.config import settings

        super().__init__(
            name="agentrouter",
            api_key=api_key or settings.agentrouter_api_key,
            model=model or settings.agentrouter_model,
            base_url=base_url or "https://co.agentrouter.org/v1",
            timeout=settings.agentrouter_timeout_ms / 1000,
            max_retries=settings.agentrouter_max_retries,
            capabilities=["chat", "tools", "streaming", "structured-outputs"],
            rate_limiter=RateLimiter(rpm=float(settings.agentrouter_rate_limit_rpm)),
            supports_multimodal=supports_multimodal,
        )


class AgentRouterAnthropicProvider(ModelProvider):
    """AgentRouter Anthropic-compatible models (e.g. claude-opus-4-8, claude-opus-5).

    Uses the official Anthropic Python SDK so AgentRouter's Messages endpoint is
    resolved correctly (the SDK appends ``/v1/messages`` to the provided base
    URL). The provider name remains ``agentrouter`` at all times; only the
    transport protocol changes.
    """

    DEFAULT_BASE_URL = "https://agentrouter.org"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        supports_multimodal: bool = False,
    ) -> None:
        from anvaya.config import settings

        self.name = "agentrouter"
        self.api_key = api_key or settings.agentrouter_api_key
        self.model = model or settings.agentrouter_model
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = settings.agentrouter_timeout_ms / 1000
        self.max_retries = settings.agentrouter_max_retries
        self._capabilities = ["chat", "tools", "streaming", "structured-outputs"]
        if supports_multimodal and "multimodal" not in self._capabilities:
            self._capabilities.append("multimodal")
        self.rate_limiter = RateLimiter(rpm=float(settings.agentrouter_rate_limit_rpm))
        self._client: Anthropic | None = None

    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def capabilities(self) -> list[str]:
        return list(self._capabilities)

    def supports_capability(self, capability: str) -> bool:
        if capability == "structured-outputs":
            return self.supports_capability("tools")
        return capability in self._capabilities

    def _get_client(self) -> Anthropic:
        if self._client is None:
            self._client = Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        return self._client

    @staticmethod
    def _format_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if not tools:
            return None
        anthropic_tools: list[dict[str, Any]] = []
        for t in tools:
            parameters = t.get("input_schema") or t.get("parameters", {})
            if isinstance(parameters, list):
                properties = {}
                required = []
                for p in parameters:
                    properties[p["name"]] = {
                        "type": p.get("type", "string"),
                        "description": p.get("description", ""),
                    }
                    if p.get("enum"):
                        properties[p["name"]]["enum"] = p["enum"]
                    if p.get("required", True):
                        required.append(p["name"])
                parameters = {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            anthropic_tools.append(
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": parameters,
                }
            )
        return anthropic_tools

    @staticmethod
    def _prepare_messages(
        messages: list[dict[str, Any]],
        response_format: dict[str, str] | None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Extract system prompt and ensure only user/assistant remain in messages."""
        system_parts: list[str] = []
        chat_messages: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                if isinstance(content, str):
                    system_parts.append(content)
                elif isinstance(content, list):
                    texts = [part.get("text", "") for part in content if part.get("type") == "text"]
                    system_parts.append(" ".join(texts))
                continue
            if role in ("user", "assistant"):
                if isinstance(content, list):
                    content = [
                        AgentRouterAnthropicProvider._convert_content_part(part)
                        for part in content
                    ]
                    chat_messages.append({"role": role, "content": content})
                elif isinstance(content, (str, list)):
                    chat_messages.append({"role": role, "content": content})
                else:
                    chat_messages.append({"role": role, "content": str(content)})

        if response_format and response_format.get("type") == "json_object":
            system_parts.append("You must output a valid JSON object.")

        system = "\n\n".join(system_parts) if system_parts else None
        return system, chat_messages

    @staticmethod
    def _convert_content_part(part: dict[str, Any]) -> dict[str, Any]:
        """Convert OpenAI-style image_url parts to Anthropic image source parts."""
        if part.get("type") != "image_url":
            return part
        image_url = part.get("image_url", {}) or {}
        url = image_url.get("url", "")
        if not url.startswith("data:"):
            return part
        try:
            header, b64 = url.split(",", 1)
            media_type = header.replace("data:", "").replace(";base64", "")
            if not media_type:
                media_type = "image/png"
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            }
        except ValueError:
            return part

    def _normalize_message(
        self, message: Any, model: str, duration_ms: float
    ) -> NormalizedModelResponse:
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        request_id = getattr(message, "id", "")
        for idx, block in enumerate(message.content or []):
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", "") or "")
            elif getattr(block, "type", None) == "tool_use":
                tool_id = getattr(block, "id", None) or f"call_{idx}"
                tool_calls.append(
                    {
                        "id": tool_id,
                        "name": getattr(block, "name", ""),
                        "arguments": getattr(block, "input", {}) or {},
                    }
                )
        usage: dict[str, Any] = {}
        if message.usage:
            usage = {
                "input_tokens": getattr(message.usage, "input_tokens", 0),
                "output_tokens": getattr(message.usage, "output_tokens", 0),
            }
        usage["duration_ms"] = duration_ms
        return NormalizedModelResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=message.stop_reason or ("tool_calls" if tool_calls else "stop"),
            usage=usage,
            provider="agentrouter",
            model=message.model or model,
            streaming_supported=True,
            request_id=request_id,
        )

    def _request_id_from_exc(self, exc: Exception) -> str:
        response = getattr(exc, "response", None)
        if response is not None:
            return (
                response.headers.get("x-request-id")
                or response.headers.get("request-id")
                or ""
            )
        return ""

    def _map_error(self, exc: Exception, request_id: str = "") -> NormalizedModelResponse:
        status: int | None = None
        category = "AGENTROUTER_PROVIDER_ERROR"
        if isinstance(exc, AnthropicAuthenticationError):
            category = "AGENTROUTER_AUTH_FAILED"
            status = getattr(exc, "status_code", 401)
        elif isinstance(exc, AnthropicNotFoundError):
            category = "AGENTROUTER_MODEL_NOT_FOUND"
            status = getattr(exc, "status_code", 404)
        elif isinstance(exc, AnthropicRateLimitError):
            category = "AGENTROUTER_RATE_LIMITED"
            status = getattr(exc, "status_code", 429)
        elif isinstance(exc, AnthropicBadRequestError):
            category = "AGENTROUTER_PROTOCOL_ERROR"
            status = getattr(exc, "status_code", 400)
        elif isinstance(exc, AnthropicAPIError) and hasattr(exc, "status_code"):
            status = exc.status_code
            if status == 408 or status == 504:
                category = "AGENTROUTER_TIMEOUT"
            else:
                category = "AGENTROUTER_PROVIDER_ERROR"

        message = str(exc)
        body = getattr(exc, "body", None)
        if body and isinstance(body, dict):
            if isinstance(body.get("error"), dict):
                msg = body.get("error", {}).get("message")
            else:
                msg = body.get("msg")
            if msg:
                message = msg

        logger.warning(
            "agentrouter.anthropic.error",
            category=category,
            status=status,
            model=self.model,
            base_url=self.base_url,
            request_id=request_id,
            error=message,
        )
        return NormalizedModelResponse(
            error=f"AgentRouter {category}: {message}",
            provider="agentrouter",
            model=self.model,
            category=category,
            request_id=request_id,
        )

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        response_format: dict[str, str] | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> NormalizedModelResponse | Iterator[NormalizedModelResponse]:
        if not self.configured():
            return NormalizedModelResponse(
                error="AgentRouter is not configured",
                provider="agentrouter",
                model=self.model,
                category="AGENTROUTER_NOT_CONFIGURED",
            )

        if self.rate_limiter and not self.rate_limiter.acquire(blocking=True, timeout=60.0):
            return NormalizedModelResponse(
                error="AgentRouter rate limit: request timed out waiting for capacity",
                provider="agentrouter",
                model=self.model,
                category="AGENTROUTER_RATE_LIMITED",
            )

        system, chat_messages = self._prepare_messages(messages, response_format)
        anthropic_tools = self._format_tools(tools)
        max_tokens = 4096

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": chat_messages,
            "stream": stream,
        }
        if system:
            kwargs["system"] = system
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
            kwargs["tool_choice"] = {"type": "auto"}

        client = self._get_client()

        try:
            started = perf_counter()
            if stream:
                return self._stream_response(client, kwargs, started)

            response = client.messages.create(**kwargs)
            duration_ms = round((perf_counter() - started) * 1000, 2)
            return self._normalize_message(response, self.model, duration_ms)
        except AnthropicAPIError as exc:
            return self._map_error(exc, self._request_id_from_exc(exc))
        except Exception as exc:
            logger.warning("agentrouter.anthropic.completion_error", error=str(exc))
            return NormalizedModelResponse(
                error=f"AgentRouter Anthropic completion error: {exc}",
                provider="agentrouter",
                model=self.model,
                category="AGENTROUTER_PROVIDER_ERROR",
            )

    def _stream_response(
        self, client: Anthropic, kwargs: dict[str, Any], started: float
    ) -> Iterator[NormalizedModelResponse]:
        full_text = ""
        tool_inputs: dict[str, str] = {}
        tool_ids: dict[str, str] = {}
        tool_names: dict[str, str] = {}
        model = self.model
        request_id = ""
        try:
            with client.messages.create(**kwargs) as stream:
                for event in stream:
                    if event.type == "message_start":
                        if event.message.model:
                            model = event.message.model
                        if event.message.id:
                            request_id = event.message.id
                    elif event.type == "content_block_start":
                        idx = str(event.index)
                        block = event.content_block
                        if block.type == "tool_use":
                            tool_ids[idx] = block.id or f"call_{idx}"
                            tool_names[idx] = block.name or ""
                            tool_inputs[idx] = ""
                    elif event.type == "content_block_delta":
                        idx = str(event.index)
                        if event.delta.type == "text_delta":
                            chunk = _join_stream_text(full_text, event.delta.text)
                            full_text += chunk
                            yield NormalizedModelResponse(
                                text=chunk,
                                provider="agentrouter",
                                model=model,
                                streaming_supported=True,
                                request_id=request_id,
                            )
                        elif event.delta.type == "input_json_delta":
                            tool_inputs[idx] = tool_inputs.get(idx, "") + event.delta.partial_json
                    elif event.type == "message_stop":
                        pass

            parsed_tool_calls = []
            for idx, raw in tool_inputs.items():
                try:
                    arguments = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    arguments = {}
                parsed_tool_calls.append(
                    {
                        "id": tool_ids.get(idx, f"call_{idx}"),
                        "name": tool_names.get(idx, ""),
                        "arguments": arguments,
                    }
                )

            duration_ms = round((perf_counter() - started) * 1000, 2)
            yield NormalizedModelResponse(
                text="",
                tool_calls=parsed_tool_calls,
                finish_reason="tool_calls" if parsed_tool_calls else "stop",
                usage={"duration_ms": duration_ms},
                provider="agentrouter",
                model=model,
                streaming_supported=True,
                request_id=request_id,
            )
        except AnthropicAPIError as exc:
            yield self._map_error(exc, self._request_id_from_exc(exc))
        except Exception as exc:
            logger.warning("agentrouter.anthropic.stream_error", error=str(exc))
            yield NormalizedModelResponse(
                error=f"AgentRouter Anthropic stream error: {exc}",
                provider="agentrouter",
                model=model,
                category="AGENTROUTER_PROVIDER_ERROR",
                request_id=request_id,
            )


class LyzrProvider(OpenAICompatibleProvider):
    """Lyzr agent platform (OpenAI-compatible endpoint when configured)."""

    def __init__(self, model: str | None = None) -> None:
        super().__init__(
            name="lyzr",
            api_key=settings.lyzr_api_key,
            model=model or "lyzr-agent",
            base_url=settings.lyzr_base_url or None,
            capabilities=["chat", "tools"],
        )


class LocalProvider(ModelProvider):
    """Deterministic local model fallback.

    This provider does not call an LLM; it signals that the agent should fall
    back to the local policy orchestrator. It is always available so the UI
    can always show a working model.
    """

    name = "anvaya-local"

    def configured(self) -> bool:
        return True

    def healthy(self) -> bool:
        return True

    def capabilities(self) -> list[str]:
        return ["chat", "tool-selection", "execution", "fallback"]

    def supports_capability(self, capability: str) -> bool:
        return capability in self.capabilities()

    def chat_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        response_format: dict[str, str] | None = None,
        stream: bool = False,
        timeout: float | None = None,
    ) -> NormalizedModelResponse:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                content = m.get("content", "")
                if isinstance(content, list):
                    texts = [part.get("text", "") for part in content if part.get("type") == "text"]
                    last_user = " ".join(texts)
                else:
                    last_user = str(content)
                break

        hint = "(image attached but ignored by local fallback)" if self._has_image(messages) else ""
        text = (
            "I'm running in ANVAYA local fallback mode. "
            "Connect an OpenAI, NVIDIA NIM, OpenRouter, or Lyzr API key "
            "for a richer model response.\n\n"
            f"You asked: {last_user} {hint}".strip()
        )
        return NormalizedModelResponse(
            text=text,
            tool_calls=[],
            finish_reason="stop",
            provider=self.name,
            model="local-policy",
            streaming_supported=False,
        )

    @staticmethod
    def _has_image(messages: list[dict[str, Any]]) -> bool:
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if part.get("type") == "image_url" or part.get("type") == "image":
                        return True
            if isinstance(content, dict) and content.get("type") in ("image_url", "image"):
                return True
        return False




_PROVIDER_CACHE: dict[str, ModelProvider] = {}


def create_model_provider(
    provider: str,
    model: str,
    supports_multimodal: bool = False,
    config: ModelConfig | None = None,
) -> ModelProvider:
    """Create a provider instance bound to a specific provider/model pair.

    This allows the agent panel to select any model in the registry and have it
    actually called, rather than being forced to the provider's default env var.
    """
    provider = provider.lower()
    protocol = ""
    base_url = ""
    if config:
        protocol = (config.protocol or "").lower()
        base_url = config.base_url or ""

    if provider == "nvidia":
        return NVIDIAProvider(model=model, supports_multimodal=supports_multimodal)
    if provider == "agentrouter":
        if protocol == "anthropic-compatible":
            return AgentRouterAnthropicProvider(
                model=model, base_url=base_url or None, supports_multimodal=supports_multimodal
            )
        return AgentRouterOpenAIProvider(
            model=model, base_url=base_url or None, supports_multimodal=supports_multimodal
        )
    if provider == "openai":
        return OpenAIProvider(model=model, supports_multimodal=supports_multimodal)
    if provider == "lyzr":
        return LyzrProvider(model=model)
    if provider == "openrouter":
        return OpenRouterProvider(model=model, supports_multimodal=supports_multimodal)
    if provider == "opencode":
        return OpenCodeProvider(model=model, supports_multimodal=supports_multimodal)
    if provider == "seekai":
        return SeekAIProvider(model=model, supports_multimodal=supports_multimodal)
    if provider == "gmicloud":
        return GMICloudProvider(model=model, supports_multimodal=supports_multimodal)
    if provider == "empero":
        return EmperoProvider(model=model, supports_multimodal=supports_multimodal)
    return LocalProvider()


def get_model_provider_for_config(config: Any) -> ModelProvider | None:
    """Create a model provider from a ModelConfig object."""
    if not config:
        return None
    return create_model_provider(
        config.provider,
        config.model,
        supports_multimodal=getattr(config, "supports_multimodal", False),
        config=config,
    )


def get_model_provider(name: str) -> ModelProvider | None:
    """Return a provider instance by name using the configured default model."""
    name = name.lower()
    if name in _PROVIDER_CACHE:
        return _PROVIDER_CACHE[name]

    provider: ModelProvider | None = None
    if name == "nvidia":
        provider = NVIDIAProvider()
    elif name == "agentrouter":
        provider = AgentRouterOpenAIProvider()
    elif name == "openai":
        provider = OpenAIProvider()
    elif name == "lyzr":
        provider = LyzrProvider()
    elif name == "openrouter":
        provider = OpenRouterProvider()
    elif name == "opencode":
        provider = OpenCodeProvider()
    elif name == "seekai":
        provider = SeekAIProvider()
    elif name == "gmicloud":
        provider = GMICloudProvider()
    elif name == "empero":
        provider = EmperoProvider()
    elif name in ("anvaya", "anvaya-local", "local"):
        provider = LocalProvider()

    if provider:
        _PROVIDER_CACHE[name] = provider
    return provider


def get_available_providers() -> dict[str, ModelProvider]:
    """Return all configured and healthy model providers.

    The active catalog is NVIDIA, AgentRouter, OpenCode, OpenRouter, SeekAI,
    GMI Cloud, Empero, and ANVAYA local. Direct OpenAI and Lyzr providers are
    no longer exposed in the model selector.
    """
    return {
        name: provider
        for name in [
            "nvidia",
            "agentrouter",
            "opencode",
            "openrouter",
            "seekai",
            "gmicloud",
            "empero",
            "anvaya",
        ]
        if (provider := get_model_provider(name)) is not None and provider.configured()
    }


def requires_reasoning(profile_id: str) -> list[str]:
    """Return required capabilities for a given agent profile."""
    required = ["chat", "tools"]
    if profile_id == "sentinel":
        required.extend(["streaming", "structured-outputs"])
    if profile_id in ("pathfinder", "responder"):
        required.append("structured-outputs")
    return required


def is_model_compatible(model: Any, required: list[str]) -> tuple[bool, str]:
    """Check whether a ModelConfig supports the required capabilities."""
    missing = []
    for cap in required:
        if cap == "chat":
            ok = True
        elif cap == "tools":
            ok = getattr(model, "supports_tools", False)
        elif cap == "streaming":
            ok = getattr(model, "supports_streaming", False)
        elif cap == "reasoning":
            ok = getattr(model, "supports_reasoning", False)
        elif cap == "multimodal":
            ok = getattr(model, "supports_multimodal", False)
        elif cap == "structured-outputs":
            ok = getattr(model, "supports_tools", False)
        else:
            ok = cap in (model.capabilities or [])
        if not ok:
            missing.append(cap)
    if missing:
        return False, f"Missing capabilities: {', '.join(missing)}"
    return True, ""


def select_model_provider_for_profile(
    profile_id: str, models: list[Any]
) -> tuple[Any, ModelProvider | None, str]:
    """Select the best available and capable model for a profile.

    Returns (model_config, provider_instance, reason).
    """
    required = requires_reasoning(profile_id)

    def _env_model_for_provider(provider: str) -> str:
        if provider == "seekai":
            return (settings.seekai_model or "").strip()
        if provider == "gmicloud":
            return (settings.gmicloud_model or "").strip()
        return ""

    def _provider_order(provider: str) -> int:
        return {
            "agentrouter": 0,
            "nvidia": 1,
            "opencode": 2,
            "seekai": 3,
            "gmicloud": 4,
            "openrouter": 5,
            "empero": 6,
        }.get(provider, 7)

    candidates = []
    for m in models:
        provider = get_model_provider_for_config(m)
        if provider is None:
            continue
        if not provider.configured():
            continue
        compatible, reason = is_model_compatible(m, required)
        if not compatible:
            continue
        order = _provider_order(m.provider)
        availability_rank = 0 if getattr(m, "availability", "") == "available" else 1
        env_default = _env_model_for_provider(m.provider)
        default_rank = 0 if env_default and m.model == env_default else 1
        candidates.append((order, availability_rank, default_rank, m, provider))

    if candidates:
        candidates.sort(key=lambda x: x[:3])
        return candidates[0][3], candidates[0][4], "selected"

    local = get_model_provider("anvaya")
    local_model = next((m for m in models if m.provider == "anvaya"), None)
    if local_model:
        return local_model, local, "no-capable-external-model-local-fallback"
    return None, None, "no-suitable-model-available"
