"""NVIDIA NIM model catalog discovery.

Fetches the list of models exposed by the configured NIM endpoint using the
OpenAI-compatible ``GET /v1/models`` endpoint. The result is cached for a few
minutes so the model registry stays fast and does not hammer the catalog API.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any

import httpx

from anvaya.config import settings
from anvaya.llm.catalog_intelligence import display_name_for_model, get_model_intelligence
from anvaya.llm.logo_domains import logo_domain_for_model
from anvaya.llm.model_identity import infer_family, infer_maker
from anvaya.logging import get_logger

logger = get_logger("anvaya.llm.nvidia_catalog")

_STATIC_NVIDIA_MODELS = [
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.2-1b-instruct",
    "meta/llama-3.2-11b-vision-instruct",
    "meta/llama-3.2-90b-vision-instruct",
    "minimaxai/minimax-m3",
    "mistralai/mistral-nemotron",
    "moonshotai/kimi-k3",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/nemotron-3-nano-30b-a3b",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-mini-4b-instruct",
    "nvidia/nemotron-nano-12b-v2-vl",
    "nvidia/nvidia-nemotron-nano-9b-v2",
    "openai/gpt-oss-20b",
    "poolside/laguna-xs-2.1",
    "stepfun-ai/step-3.7-flash",
    "thinkingmachines/inkling",
]

_NON_CHAT_SUBSTRINGS = (
    "embed",
    "retriever",
    "parse",
    "safety",
    "guard",
    "topic-control",
    "content-safety",
    "reward",
    "nv-embed",
    "nv-embedcode",
    "nv-embedqa",
    "nvclip",
    "clip",
    "nvidia/cosmos-reason",
    "nvidia/ising-calibration",
    "nvidia/nemoretriever",
    "nvidia/nemotron-parse",
    "nvidia/nv-embed",
    "nvidia/nvclip",
    "nvidia/ai-synthetic-video-detector",
    "nvidia/riva-translate",
    "deplot",
    "diffusion",
    "recurrentgemma",
    "bge",
    "starcoder",
    "codegemma",
    "muse",
    "glimmer",
    "cosmos",
    "ising",
    "synthetic",
)

_CHAT_MARKERS = (
    "instruct",
    "chat",
    "vision",
    "vlm",
    "vila",
    "neva",
    "multimodal",
    "large",
    "flash",
    "super",
    "ultra",
    "nano",
    "mini",
    "moe",
    "creative",
    "-it",
    "qa",
    "laguna",
    "minimax",
    "kimi",
    "yi-",
)

_CACHE_TTL_SECONDS = 300


class _CatalogCache:
    """Simple TTL cache for the NVIDIA catalog."""

    def __init__(self, ttl: float = _CACHE_TTL_SECONDS):
        self.ttl = ttl
        self._value: list[str] | None = None
        self._fetched_at: float = 0.0
        self._lock = threading.Lock()

    def get(self) -> list[str] | None:
        with self._lock:
            if self._value and (time.monotonic() - self._fetched_at) < self.ttl:
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


_catalog_cache = _CatalogCache()


def _is_chat_model(model_id: str) -> bool:
    lower = model_id.lower()
    if any(part in lower for part in _NON_CHAT_SUBSTRINGS):
        return False
    return any(marker in lower for marker in _CHAT_MARKERS)


def _extract_size_b(model_id: str) -> float:
    """Heuristic: try to extract parameter size in billions from the model id."""
    lower = model_id.lower()
    matches = re.findall(r"(\d+(?:\.\d+)?)(?:x(\d+(?:\.\d+)?))?b", lower)
    if not matches:
        if "nano" in lower or "mini" in lower or "xs" in lower:
            return 4.0
        if "small" in lower:
            return 7.0
        if "medium" in lower:
            return 30.0
        if "large" in lower or "super" in lower:
            return 70.0
        if "ultra" in lower:
            return 200.0
        return 0.0

    total = 0.0
    for m in matches:
        if m[1]:
            total += float(m[0]) * float(m[1])
        else:
            total += float(m[0])
    return total


def _cost_class(model_id: str) -> str:
    size = _extract_size_b(model_id)
    if size <= 0:
        return "standard"
    if (
        size <= 13
        or "nano" in model_id.lower()
        or "mini" in model_id.lower()
        or "xs" in model_id.lower()
    ):
        return "low"
    if size >= 200:
        return "high"
    if size >= 50:
        return "standard"
    return "low"


def _is_multimodal(model_id: str) -> bool:
    lower = model_id.lower()
    return any(
        part in lower
        for part in (
            "vision",
            "vila",
            "neva",
            "multimodal",
            "vlm",
            "phi-3-vision",
            "kosmos",
            "fuyu",
            "nvidia/llama-3.1-nemotron-nano-vl",
            "nvidia/llama-nemotron-embed-vl",
            "nvidia/nemotron-nano-12b-v2-vl",
        )
    )


def _slug_id(model_id: str) -> str:
    """Create a globally-unique provider-qualified id for the NVIDIA model."""
    return f"nvidia/{model_id}"


def _latency_class(model_id: str) -> str:
    """Estimate latency class from parameter size: smaller = faster."""
    size = _extract_size_b(model_id)
    if size <= 0:
        return "standard"
    if size <= 13 or any(k in model_id.lower() for k in ("nano", "mini", "flash", "xs")):
        return "fast"
    if size <= 70:
        return "standard"
    return "slow"


def _model_config_from_id(model_id: str) -> dict[str, Any]:
    """Return a dict that can be merged into ModelConfig creation."""
    maker = infer_maker(model_id)
    family = infer_family(model_id)
    intelligence = get_model_intelligence(maker, family, model_id, provider="nvidia")
    display_name = display_name_for_model(model_id)
    cfg = {
        "id": _slug_id(model_id),
        "provider": "nvidia",
        "provider_model_id": model_id,
        "model": model_id,
        "maker": maker,
        "family": family,
        "display_name": display_name,
        "description": f"{display_name} on NVIDIA NIM.",
        "purpose": "Chat, tool use, and reasoning through NVIDIA NIM.",
        "capabilities": ["chat", "tools", "streaming", "structured-outputs"],
        "context_window": 128000,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_reasoning": True,
        "supports_multimodal": _is_multimodal(model_id),
        "latency_class": _latency_class(model_id),
        "cost_class": _cost_class(model_id),
        "default_temperature": 0.2,
        "recommended_for": ["sentinel"],
        "logo_domain": logo_domain_for_model(model_id),
        "protocol": "openai-compatible",
        "base_url": settings.nvidia_base_url or "https://integrate.api.nvidia.com/v1",
    }
    cfg.update(intelligence)
    return cfg


def fetch_nvidia_models(use_cache: bool = True) -> list[str]:
    """Return the list of chat-capable NVIDIA NIM model ids.

    If ``NVIDIA_API_KEY`` is set, the catalog is fetched from
    ``NVIDIA_BASE_URL/v1/models`` and cached for 5 minutes. Otherwise a
    curated static catalog is used.
    """
    if use_cache:
        cached = _catalog_cache.get()
        if cached is not None:
            return cached

    if not settings.nvidia_api_key:
        return list(_STATIC_NVIDIA_MODELS)

    base_url = (settings.nvidia_base_url or "https://integrate.api.nvidia.com/v1").rstrip("/")
    url = f"{base_url}/models"
    try:
        response = httpx.get(
            url,
            headers={
                "Authorization": f"Bearer {settings.nvidia_api_key}",
                "Accept": "application/json",
            },
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        model_ids = [m["id"] for m in data if m.get("id")]
        default_model = (settings.nvidia_model or "").strip()
        allowed = set(_STATIC_NVIDIA_MODELS)
        if default_model and default_model not in allowed:
            allowed.add(default_model)
        chat_models = [m for m in model_ids if m in allowed]
        logger.info("nvidia.catalog_fetched", total=len(model_ids), chat_models=len(chat_models))
        _catalog_cache.set(chat_models)
        return chat_models
    except Exception as exc:
        logger.warning("nvidia.catalog_fetch_failed", error=str(exc))
        return list(_STATIC_NVIDIA_MODELS)


def get_nvidia_model_configs() -> list[dict[str, Any]]:
    """Return model config dicts for every NVIDIA model in the catalog.

    Slug collisions are resolved by appending an index so the frontend keys
    remain unique across the model selector.
    """
    models = fetch_nvidia_models()
    seen: dict[str, int] = {}
    configs: list[dict[str, Any]] = []
    for model_id in models:
        cfg = _model_config_from_id(model_id)
        slug = cfg["id"]
        if slug in seen:
            seen[slug] += 1
            cfg["id"] = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
        configs.append(cfg)
    return configs


def invalidate_nvidia_catalog_cache() -> None:
    """Clear the catalog cache (useful for tests or on-demand refresh)."""
    _catalog_cache.clear()
