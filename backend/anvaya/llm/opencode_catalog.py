"""OpenCode model catalog.

OpenCode's dynamic catalog is discovered through two official sources:

1. ``GET https://opencode.ai/zen/v1/models`` (with an API key) returns the
   currently available model IDs.
2. ``https://models.dev/api.json`` returns rich metadata for OpenCode models
   (family, capabilities, context limits, pricing, etc.).

ANVAYA exposes only the free-tier OpenCode models, where the metadata reports
``cost.input``, ``cost.output``, and ``cost.cache_read`` all equal to ``0``.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from anvaya.config import settings
from anvaya.llm.catalog_intelligence import get_model_intelligence
from anvaya.llm.logo_domains import logo_domain_for_model
from anvaya.llm.model_identity import infer_family, infer_maker, logo_domain_for_maker
from anvaya.logging import get_logger

logger = get_logger("anvaya.llm.opencode_catalog")

OPENCODE_BASE_URL = "https://opencode.ai/zen/v1"
MODELS_DEV_URL = "https://models.dev/api.json"

_LIST_TTL_SECONDS = 60
_METADATA_TTL_SECONDS = 300


class _TTLCache:
    """Simple generic TTL cache."""

    def __init__(self, ttl: float):
        self.ttl = ttl
        self._value: Any = None
        self._fetched_at: float = 0.0
        self._lock = threading.Lock()

    def get(self) -> Any:
        with self._lock:
            if self._value is not None and (time.monotonic() - self._fetched_at) < self.ttl:
                return self._value
            return None

    def set(self, value: Any) -> None:
        with self._lock:
            self._value = value
            self._fetched_at = time.monotonic()

    def clear(self) -> None:
        with self._lock:
            self._value = None
            self._fetched_at = 0.0


_list_cache = _TTLCache(_LIST_TTL_SECONDS)
_metadata_cache = _TTLCache(_METADATA_TTL_SECONDS)


def _fetch_model_list() -> list[str]:
    """Fetch the live OpenCode model list; returns the current model IDs."""
    cached = _list_cache.get()
    if cached is not None:
        return cached

    if not settings.opencode_api_key:
        _list_cache.set([])
        return []

    base_url = (settings.opencode_base_url or OPENCODE_BASE_URL).rstrip("/")
    try:
        response = httpx.get(
            f"{base_url}/models",
            headers={
                "Authorization": f"Bearer {settings.opencode_api_key}",
                "Accept": "application/json",
            },
            timeout=20.0,
        )
        response.raise_for_status()
        model_ids = [m["id"] for m in response.json().get("data", []) if m.get("id")]
        logger.info("opencode.list_fetched", count=len(model_ids))
        _list_cache.set(model_ids)
        return model_ids
    except Exception as exc:
        logger.warning("opencode.list_fetch_failed", error=str(exc))
        _list_cache.set([])
        return []


def _fetch_metadata() -> dict[str, Any]:
    """Fetch rich model metadata from models.dev and return the opencode section."""
    cached = _metadata_cache.get()
    if cached is not None:
        return cached

    try:
        response = httpx.get(
            MODELS_DEV_URL,
            headers={"User-Agent": "ANVAYA/1.0", "Accept": "application/json"},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json().get("opencode", {})
        models = data.get("models", {})
        _metadata_cache.set(dict(models))
        logger.info("opencode.metadata_fetched", count=len(models))
        return dict(models)
    except Exception as exc:
        logger.warning("opencode.metadata_fetch_failed", error=str(exc))
        _metadata_cache.set({})
        return {}


def _is_free(cost: dict[str, Any] | None) -> bool:
    if not cost:
        return False
    try:
        return (
            float(cost.get("input", -1)) == 0.0
            and float(cost.get("output", -1)) == 0.0
            and float(cost.get("cache_read", 0)) == 0.0
        )
    except (ValueError, TypeError):
        return False


def _cost_class(cost: dict[str, Any] | None) -> str:
    if not cost:
        return "standard"
    try:
        total = float(cost.get("input", 0)) + float(cost.get("output", 0))
    except (ValueError, TypeError):
        return "standard"
    if total == 0.0:
        return "free"
    if total < 0.5:
        return "low"
    if total < 5.0:
        return "standard"
    if total < 20.0:
        return "high"
    return "premium"


def _is_multimodal(meta: dict[str, Any]) -> bool:
    modalities = meta.get("modalities") or {}
    inputs = modalities.get("input", [])
    return "image" in inputs or meta.get("attachment") is True


def _supports_structured_output(meta: dict[str, Any]) -> bool:
    return bool(meta.get("structured_output") or meta.get("tool_call"))


def _latency_class(meta: dict[str, Any]) -> str:
    """Best-effort latency class from family/size hints in metadata."""
    family = (meta.get("family") or "").lower()
    name = (meta.get("name") or meta.get("id") or "").lower()
    if any(k in family or k in name for k in ("flash", "nano", "mini", "xs", "lite")):
        return "fast"
    if any(k in family or k in name for k in ("opus", "ultra", "pro", "large")):
        return "slow"
    return "standard"


def _opencode_protocol(model_id: str, meta: dict[str, Any]) -> str:
    """Determine which OpenCode Zen endpoint a model expects.

    OpenCode Zen serves models across three different endpoints:
    ``/v1/chat/completions`` (OpenAI-compatible), ``/v1/responses`` (OpenAI
    Responses API), and ``/v1/messages`` (Anthropic Messages API).  Gemini
    models require a Google-compatible client and are not yet supported.
    """
    mid = model_id.lower()
    family = (meta.get("family") or "").lower()

    if mid.startswith("claude-") or mid.startswith("qwen3"):
        return "anthropic-compatible"

    if mid.startswith("gemini-"):
        return "opencode-google"

    if mid.startswith("gpt-") or mid.startswith("grok-4") or "muse-spark-1.2" in mid:
        return "opencode-responses"

    chat_families = {
        "deepseek",
        "deepseek-flash",
        "deepseek-pro",
        "glm",
        "kimi",
        "minimax",
        "grok-build",
    }
    if (
        any(mid.startswith(pre) for pre in ("deepseek-v4", "glm-5", "kimi-k2", "minimax-m"))
        or mid == "grok-build-0.1"
        or any(f in family for f in chat_families)
    ):
        return "openai-compatible"

    if meta.get("reasoning") or meta.get("interleaved"):
        return "opencode-responses"

    return "openai-compatible"


def _model_config_from_meta(model_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Build a ModelConfig creation dict from OpenCode metadata."""
    family = (meta.get("family") or infer_family(model_id)).replace("-", " ").title()
    maker = infer_maker(model_id, family)
    logo_domain = (
        logo_domain_for_maker(maker) if maker else logo_domain_for_model(f"opencode/{model_id}")
    )
    cost = meta.get("cost") or {}
    limit = meta.get("limit") or {}
    context = limit.get("context", 128000)

    raw_name = meta.get("name") or ""
    intelligence = get_model_intelligence(
        maker, family, model_id, provider="opencode", raw_name=raw_name
    )

    capabilities: list[str] = ["chat"]
    if meta.get("tool_call"):
        capabilities.extend(["tools", "structured-outputs"])
    elif _supports_structured_output(meta):
        capabilities.append("structured-outputs")
    capabilities.append("streaming")
    if meta.get("reasoning"):
        capabilities.append("reasoning")
    if _is_multimodal(meta):
        capabilities.append("multimodal")

    config: dict[str, Any] = {
        "id": f"opencode/{model_id}",
        "provider": "opencode",
        "provider_model_id": model_id,
        "model": model_id,
        "maker": maker,
        "family": family,
        "display_name": (meta.get("name") or model_id).replace("-free", " Free"),
        "description": (
            meta.get("description")
            or f"{family} via OpenCode Zen."
        ),
        "purpose": "Chat, tool use, and reasoning through OpenCode Zen.",
        "capabilities": capabilities,
        "context_window": int(context) if isinstance(context, (int, float, str)) else 128000,
        "supports_tools": bool(meta.get("tool_call")),
        "supports_streaming": True,
        "supports_reasoning": bool(meta.get("reasoning")),
        "supports_multimodal": _is_multimodal(meta),
        "latency_class": _latency_class(meta),
        "cost_class": _cost_class(cost),
        "default_temperature": 0.2,
        "recommended_for": ["sentinel"],
        "logo_domain": logo_domain,
        "protocol": _opencode_protocol(model_id, meta),
        "base_url": settings.opencode_base_url or OPENCODE_BASE_URL,
        "pricing": {
            "input_per_million": float(cost["input"]) if "input" in cost else None,
            "cached_input_per_million": float(cost["cache_read"]) if "cache_read" in cost else None,
            "output_per_million": float(cost["output"]) if "output" in cost else None,
        },
    }
    config.update(intelligence)
    return config


def get_opencode_model_configs() -> list[dict[str, Any]]:
    """Return ModelConfig dicts for free OpenCode models available on this key."""
    model_ids = _fetch_model_list()
    metadata = _fetch_metadata()

    seen: dict[str, int] = {}
    configs: list[dict[str, Any]] = []
    for model_id in model_ids:
        meta = metadata.get(model_id) or {}
        cost = meta.get("cost") or {}
        if not _is_free(cost):
            continue
        cfg = _model_config_from_meta(model_id, meta)
        slug = cfg["id"]
        if slug in seen:
            seen[slug] += 1
            cfg["id"] = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
        configs.append(cfg)
    return configs


def invalidate_opencode_cache() -> None:
    """Clear OpenCode catalog caches."""
    _list_cache.clear()
    _metadata_cache.clear()
