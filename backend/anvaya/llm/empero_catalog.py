"""Empero community endpoint catalog.

Empero operates an OpenAI-compatible public endpoint at
``https://free.empero.org/v1``.  It does not require a user-specific secret;
any API key is accepted (the canonical value is ``free``).

Because this is a public/community endpoint, every model is tagged:

- ``cost_class``: ``free``
- ``access_class``: ``community_free``
- ``privacy_class``: ``public_community_endpoint``

and the UI is warned that prompts and completions are logged for training.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from anvaya.config import settings
from anvaya.llm.catalog_intelligence import display_name_for_model, get_model_intelligence
from anvaya.llm.model_identity import logo_domain_for_maker
from anvaya.llm.model_identity import infer_family, infer_maker
from anvaya.logging import get_logger

logger = get_logger("anvaya.llm.empero_catalog")

_EMPERO_BASE_URL = "https://free.empero.org/v1"
_PUBLIC_TOKEN = "free"
_LIST_TTL_SECONDS = 120

_EMPERO_CAPABILITIES = ["chat", "tools", "streaming", "reasoning"]

_EMPERO_MODELS: list[dict[str, Any]] = [
    {
        "provider_model_id": "glm-5.3-flash",
        "display_name": "GLM 5.3 Flash",
        "family": "GLM 5",
        "maker": "Z AI",
        "description": (
            "Z AI GLM 5.3 Flash, a fast multimodal open-weights model "
            "with million-token context.  Serves the Empero community endpoint."
        ),
        "context_window": 1_048_576,
        "max_tokens": 131_072,
        "supports_multimodal": True,
    },
    {
        "provider_model_id": "Qwen/Qwen3.8-27B-FP8",
        "display_name": "Qwen 3.8 27B FP8",
        "family": "Qwen 3.8",
        "maker": "Alibaba",
        "description": (
            "Qwen 3.8 27B FP8 hosted on the Empero public community endpoint. "
            "Free to use; prompts and completions are logged for training."
        ),
        "context_window": 131_072,
        "max_tokens": 32_768,
        "supports_multimodal": False,
        "aliases": ["qwen3.8-fp8", "free"],
    },
]


class _TTLCache:
    """Simple TTL cache for Empero discovery."""

    def __init__(self, ttl: float):
        self.ttl = ttl
        self._value: list[str] | None = None
        self._fetched_at: float = 0.0
        self._lock = threading.Lock()

    def get(self) -> list[str] | None:
        with self._lock:
            if self._value is not None and (time.monotonic() - self._fetched_at) < self.ttl:
                return list(self._value)
            return None

    def set(self, value: list[str]) -> None:
        with self._lock:
            self._value = list(value)
            self._fetched_at = time.monotonic()

    def clear(self) -> None:
        with self._lock:
            self._value = None
            self._fetched_at = 0.0


_empero_list_cache = _TTLCache(_LIST_TTL_SECONDS)


def _empero_headers() -> dict[str, str]:
    api_key = settings.empero_api_key
    if not api_key:
        api_key = _PUBLIC_TOKEN
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }


def _fetch_empero_model_ids() -> list[str]:
    """Return the live Empero model list, or an empty list if unavailable."""
    cached = _empero_list_cache.get()
    if cached is not None:
        return cached

    if settings.empero_api_key == "disabled":
        _empero_list_cache.set([])
        return []

    base_url = (settings.empero_base_url or _EMPERO_BASE_URL).rstrip("/")
    url = f"{base_url}/models"
    try:
        response = httpx.get(
            url,
            headers=_empero_headers(),
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        model_ids = [m["id"] for m in data.get("data", []) if m.get("id")]
        logger.info("empero.list_fetched", count=len(model_ids))
        _empero_list_cache.set(model_ids)
        return model_ids
    except Exception as exc:
        logger.warning("empero.list_fetch_failed", error=str(exc))
        _empero_list_cache.set([])
        return []


def _model_config_from_entry(entry: dict[str, Any], available_ids: set[str]) -> dict[str, Any]:
    model_id = entry["provider_model_id"]
    family = entry.get("family") or infer_family(model_id)
    maker = entry.get("maker") or infer_maker(model_id, family)
    display_name = entry.get("display_name") or display_name_for_model(model_id)
    context = int(entry.get("context_window", 1_000_000))
    max_tokens = entry.get("max_tokens")

    intelligence = get_model_intelligence(
        maker,
        family,
        model_id,
        provider="empero",
        raw_name=display_name,
    )
    intelligence.pop("display_name", None)

    if model_id in available_ids or any(a in available_ids for a in entry.get("aliases", [])):
        availability = "available"
    elif settings.empero_api_key != "disabled":
        availability = "configured"
    else:
        availability = "unavailable"

    cfg: dict[str, Any] = {
        "id": f"empero/{model_id}",
        "provider": "empero",
        "provider_model_id": model_id,
        "model": model_id,
        "maker": maker,
        "family": family,
        "display_name": display_name,
        "description": entry.get("description", ""),
        "purpose": f"{display_name} via the Empero public community endpoint.",
        "capabilities": _EMPERO_CAPABILITIES,
        "context_window": context,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_reasoning": True,
        "supports_multimodal": entry.get("supports_multimodal", False),
        "latency_class": "standard",
        "cost_class": "free",
        "availability": availability,
        "default_temperature": 0.2,
        "recommended_for": ["sentinel"],
        "logo_domain": logo_domain_for_maker(maker),
        "protocol": "openai-compatible",
        "base_url": settings.empero_base_url or _EMPERO_BASE_URL,
        "pricing": {
            "input_per_million": 0.0,
            "cached_input_per_million": 0.0,
            "output_per_million": 0.0,
        },
        "pricing_mode": "per_token",
        "gateway_type": "community endpoint",
        "privacy_class": "public_community_endpoint",
        "access_class": "community_free",
        "aliases": entry.get("aliases", []),
    }
    if max_tokens is not None:
        cfg["max_tokens"] = int(max_tokens)
    cfg.update(intelligence)
    return cfg


def get_empero_model_configs() -> list[dict[str, Any]]:
    """Return ModelConfig creation dicts for the Empero catalog."""
    available_ids = set(_fetch_empero_model_ids())
    seen: dict[str, int] = {}
    configs: list[dict[str, Any]] = []
    for entry in _EMPERO_MODELS:
        cfg = _model_config_from_entry(entry, available_ids)
        slug = cfg["id"]
        if slug in seen:
            seen[slug] += 1
            cfg["id"] = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
        configs.append(cfg)
    return configs


def invalidate_empero_cache() -> None:
    """Clear Empero discovery cache."""
    _empero_list_cache.clear()
