"""GMI Cloud model catalog.

GMI Cloud exposes an OpenAI-compatible gateway at ``https://api.gmi-serving.com/v1``.
Model discovery is performed with ``GET /v1/models`` when ``GMI_API_KEY`` is set.
The catalog is normalized into ANVAYA's standard ModelConfig shape.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx

from anvaya.config import settings
from anvaya.llm.catalog_intelligence import display_name_for_model, get_model_intelligence
from anvaya.llm.model_identity import infer_family, infer_maker, logo_domain_for_maker
from anvaya.logging import get_logger

logger = get_logger("anvaya.llm.gmicloud_catalog")

_GMICLOUD_BASE_URL = "https://api.gmi-serving.com/v1"

_LIST_TTL_SECONDS = 120

_GMICLOUD_CAPABILITIES = ["chat", "tools", "streaming", "reasoning"]

_PROMOTIONAL_FREE_IDS = {
    "MiniMaxAI/MiniMax-M3",
    "MiniMaxAI/MiniMax-M2.7",
}

_GMICLOUD_FALLBACK: list[dict[str, Any]] = [
    {
        "id": "MiniMaxAI/MiniMax-M3",
        "name": "MiniMaxAI/MiniMax-M3",
        "context_length": 1_048_576,
        "is_free": True,
        "pricing": {
            "prompt": "0",
            "completion": "0",
            "request": "0",
            "image": "0",
            "input_cache_read": "0",
            "input_cache_write": "0",
        },
    },
    {
        "id": "MiniMaxAI/MiniMax-M2.7",
        "name": "MiniMaxAI/MiniMax-M2.7",
        "context_length": 196_608,
        "is_free": True,
        "pricing": {
            "prompt": "0",
            "completion": "0",
            "request": "0",
            "image": "0",
            "input_cache_read": "0",
            "input_cache_write": "0",
        },
    },
]


class _TTLCache:
    """Simple TTL cache for GMI Cloud discovery."""

    def __init__(self, ttl: float):
        self.ttl = ttl
        self._value: list[dict[str, Any]] | None = None
        self._fetched_at: float = 0.0
        self._lock = threading.Lock()

    def get(self) -> list[dict[str, Any]] | None:
        with self._lock:
            if self._value is not None and (time.monotonic() - self._fetched_at) < self.ttl:
                return [dict(m) for m in self._value]
            return None

    def set(self, value: list[dict[str, Any]]) -> None:
        with self._lock:
            self._value = [dict(m) for m in value]
            self._fetched_at = time.monotonic()

    def clear(self) -> None:
        with self._lock:
            self._value = None
            self._fetched_at = 0.0


_gmicloud_list_cache = _TTLCache(_LIST_TTL_SECONDS)


def _gmicloud_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }


def _per_million(per_token: float | None) -> float | None:
    """Convert a per-token price to a per-million-token price."""
    if per_token is None:
        return None
    try:
        return float(per_token) * 1_000_000
    except (ValueError, TypeError):
        return None


def _cost_class_from_total(total: float | None, is_free: bool, model_id: str) -> str:
    if is_free or (total is not None and total == 0.0):
        return "free"
    if total is None:
        return "standard"
    if total < 0.5:
        return "low"
    if total < 5.0:
        return "standard"
    if total < 20.0:
        return "high"
    return "premium"


def _multimodal(model_id: str, raw_name: str) -> bool:
    """Best-effort multimodal flag from verified/public model metadata."""
    lower = f"{model_id} {raw_name}".lower()
    return any(
        marker in lower
        for marker in [
            "minimax-m3",
            "gemini",
            "gpt-5.6",
            "gpt-5-6",
            "gpt-5.4",
            "gpt-5-5",
            "vision",
            "multimodal",
            "vlm",
        ]
    )


def _latency_class(model_id: str) -> str:
    lower = model_id.lower()
    if any(k in lower for k in ("flash", "nano", "mini", "xs", "lite")):
        return "fast"
    if any(k in lower for k in ("opus", "ultra", "pro", "large")):
        return "slow"
    return "standard"


def _fetch_gmicloud_models() -> list[dict[str, Any]]:
    """Return the live GMI Cloud model list, or an empty list if unavailable."""
    cached = _gmicloud_list_cache.get()
    if cached is not None:
        return cached

    api_key = settings.gmicloud_api_key
    if not api_key:
        _gmicloud_list_cache.set([])
        return []

    base_url = (settings.gmicloud_base_url or _GMICLOUD_BASE_URL).rstrip("/")
    url = f"{base_url}/models"
    try:
        response = httpx.get(
            url,
            headers=_gmicloud_headers(api_key),
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json().get("data", [])
        logger.info("gmicloud.list_fetched", count=len(data))
        _gmicloud_list_cache.set(data)
        return data
    except Exception as exc:
        logger.warning("gmicloud.list_fetch_failed", error=str(exc))
        _gmicloud_list_cache.set([])
        return []


def _family_from_model(model_id: str, raw_name: str) -> str:
    """Return a clean family for a GMI Cloud model."""
    tail = model_id.split("/")[-1] if "/" in model_id else model_id
    name = raw_name or tail
    name = name.replace("-", " ").replace("_", " ")
    name = name.replace("FP8", "").replace("BF16", "").replace(" INT4", "")
    name = name.replace("preview", "").replace("lite", "")
    tokens = name.split()
    tokens = [t for t in tokens if t]
    if tokens and tokens[-1].lower() in ("27b", "max", "pro", "flash", "lite"):
        tokens = tokens[:-1]
    if not tokens:
        return infer_family(model_id)
    return " ".join(tokens[:2]).title()


def _model_config_from_raw(model: dict[str, Any]) -> dict[str, Any] | None:
    """Build a ModelConfig creation dict from a GMI Cloud /v1/models entry."""
    model_id = model.get("id")
    if not model_id:
        return None

    lower = model_id.lower()
    if any(part in lower for part in ("embed", "retriever", "safety", "parse")):
        return None

    raw_name = (model.get("name") or model_id).strip()
    family = _family_from_model(model_id, raw_name)
    maker = infer_maker(model_id, family)
    display_name = display_name_for_model(model_id, raw_name=raw_name)
    context = model.get("context_length") or 128000
    try:
        context = int(context)
    except (ValueError, TypeError):
        context = 128000

    pricing = model.get("pricing") or {}
    prompt = _per_million(pricing.get("prompt"))
    completion = _per_million(pricing.get("completion"))
    cached = _per_million(pricing.get("input_cache_read"))
    total = 0.0
    if prompt is not None and completion is not None:
        total = float(prompt or 0) + float(completion or 0)

    raw_is_free = bool(model.get("is_free"))
    is_free = raw_is_free and (model_id in _PROMOTIONAL_FREE_IDS)
    cost_class = _cost_class_from_total(total, is_free, model_id)
    access_class = "promotional_free" if is_free else "standard"
    if not is_free and model_id in _PROMOTIONAL_FREE_IDS:
        cost_class = "free"
        access_class = "promotional_free"

    intelligence = get_model_intelligence(
        maker,
        family,
        model_id,
        provider="gmicloud",
        raw_name=raw_name,
    )
    intelligence.pop("display_name", None)

    cfg: dict[str, Any] = {
        "id": f"gmicloud/{model_id}",
        "provider": "gmicloud",
        "provider_model_id": model_id,
        "model": model_id,
        "maker": maker,
        "family": family,
        "display_name": display_name,
        "description": f"{display_name} on GMI Cloud.",
        "purpose": "Chat, tool use, and reasoning through GMI Cloud.",
        "capabilities": _GMICLOUD_CAPABILITIES,
        "context_window": context,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_reasoning": True,
        "supports_multimodal": _multimodal(model_id, raw_name),
        "latency_class": _latency_class(model_id),
        "cost_class": cost_class,
        "availability": (
            "available"
            if (settings.gmicloud_api_key and is_free)
            else ("configured" if settings.gmicloud_api_key else "unavailable")
        ),
        "default_temperature": 0.2,
        "recommended_for": ["sentinel"],
        "logo_domain": logo_domain_for_maker(maker),
        "protocol": "openai-compatible",
        "base_url": settings.gmicloud_base_url or _GMICLOUD_BASE_URL,
        "pricing": {
            "input_per_million": prompt,
            "cached_input_per_million": cached,
            "output_per_million": completion,
        },
        "pricing_mode": "per_token",
        "gateway_type": "inference gateway",
        "privacy_class": "standard",
        "access_class": access_class,
        "aliases": [],
    }
    cfg.update(intelligence)
    return cfg


def get_gmicloud_model_configs() -> list[dict[str, Any]]:
    """Return ModelConfig creation dicts for the GMI Cloud catalog."""
    raw_models = _fetch_gmicloud_models()
    using_fallback = not raw_models
    if using_fallback:
        raw_models = _GMICLOUD_FALLBACK

    if using_fallback:
        raw_models = [m for m in raw_models if m.get("id") in _PROMOTIONAL_FREE_IDS]

    by_id: dict[str, dict[str, Any]] = {}
    free_by_id: dict[str, dict[str, Any]] = {}
    for m in raw_models:
        mid = m.get("id")
        if not mid:
            continue
        if m.get("is_free"):
            free_by_id[mid] = m
        else:
            by_id.setdefault(mid, m)

    selected: list[dict[str, Any]] = []
    for mid, m in by_id.items():
        if mid in free_by_id:
            selected.append(free_by_id[mid])
        else:
            selected.append(m)
    for mid, m in free_by_id.items():
        if mid not in by_id:
            selected.append(m)

    if settings.gmicloud_free_only:
        selected = [m for m in selected if m.get("is_free")]

    configs: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for m in selected:
        cfg = _model_config_from_raw(m)
        if cfg is None:
            continue
        slug = cfg["id"]
        if slug in seen:
            seen[slug] += 1
            cfg["id"] = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
        configs.append(cfg)
    return configs


def invalidate_gmicloud_cache() -> None:
    """Clear GMI Cloud discovery cache."""
    _gmicloud_list_cache.clear()
