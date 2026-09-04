"""SeekAI model catalog.

SeekAI exposes an OpenAI-compatible gateway at ``https://seekai.cc/v1``.
The catalog is built from:

1. The user-supplied SeekAI model catalog (authoritative for model IDs,
   pricing, and capabilities).
2. A live ``GET /v1/models`` call when ``SEEKAI_API_KEY`` is configured.

Models that appear in the live discovery are marked ``available``; models from
the user catalog that are not currently returned by the discovery endpoint are
kept as ``configured`` so they remain selectable and attemptable.
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

logger = get_logger("anvaya.llm.seekai_catalog")

_SEEKAI_BASE_URL = "https://seekai.cc/v1"

_LIST_TTL_SECONDS = 120

_SEEKAI_CAPABILITIES = ["chat", "tools", "streaming", "reasoning"]

_SEEKAI_MODELS: list[dict[str, Any]] = [
    {
        "provider_model_id": "claude-fable-5",
        "display_name": "Claude Fable 5",
        "family": "Claude Fable",
        "maker": "Anthropic",
        "description": (
            "Claude model for creative writing, analysis, "
            "and controlled agent workflows."
        ),
        "context_window": 1_000_000,
        "input_price": 3.0,
        "output_price": 18.5,
        "cached_price": 0.3,
        "pricing_mode": "per_token",
        "cost_class": "premium",
    },
    {
        "provider_model_id": "claude-opus-4-8",
        "display_name": "Claude Opus 4.8",
        "family": "Claude Opus",
        "maker": "Anthropic",
        "description": (
            "Top Claude Opus tier for the hardest reasoning, "
            "coding, and long-horizon agents."
        ),
        "context_window": 1_000_000,
        "input_price": 0.425,
        "output_price": 2.125,
        "cached_price": 0.0425,
        "pricing_mode": "per_token",
        "cost_class": "standard",
    },
    {
        "provider_model_id": "claude-opus-5",
        "display_name": "Claude Opus 5",
        "family": "Claude Opus",
        "maker": "Anthropic",
        "description": (
            "Flagship Claude model for deep reasoning, "
            "coding, and long-horizon agents."
        ),
        "context_window": 1_000_000,
        "input_price": 5.0,
        "output_price": 25.0,
        "cached_price": 0.5,
        "pricing_mode": "per_token",
        "cost_class": "premium",
    },
    {
        "provider_model_id": "claude-sonnet-5",
        "display_name": "Claude Sonnet 5",
        "family": "Claude Sonnet",
        "maker": "Anthropic",
        "description": (
            "Balanced Claude model for coding, analysis, "
            "agent workflows, and cost control."
        ),
        "context_window": 1_000_000,
        "input_price": 1.44,
        "output_price": 7.2,
        "cached_price": 0.144,
        "pricing_mode": "per_token",
        "cost_class": "high",
    },
    {
        "provider_model_id": "deepseek-v4-flash",
        "display_name": "DeepSeek V4 Flash",
        "family": "DeepSeek V4",
        "maker": "DeepSeek",
        "description": (
            "Fast DeepSeek V4 lane for economical reasoning, "
            "coding, and long-context work."
        ),
        "context_window": 1_000_000,
        "input_price": 0.0625,
        "output_price": 0.125,
        "cached_price": 0.001316,
        "pricing_mode": "per_token",
        "cost_class": "low",
    },
    {
        "provider_model_id": "deepseek-v4-flash-0731",
        "display_name": "DeepSeek V4 Flash 0731",
        "family": "DeepSeek V4",
        "maker": "DeepSeek",
        "description": "OpenAI-compatible route.",
        "context_window": 1_000_000,
        "input_price": None,
        "output_price": None,
        "cached_price": None,
        "pricing_mode": "per_request",
        "cost_per_request": 0.10,
        "cost_class": "low",
        "aliases": ["DeepSeek-V4-Flash-0731"],
    },
    {
        "provider_model_id": "DeepSeek-V4-Flash-0731",
        "display_name": "DeepSeek V4 Flash 0731",
        "family": "DeepSeek V4",
        "maker": "DeepSeek",
        "description": "OpenAI-compatible route.",
        "context_window": 1_000_000,
        "input_price": None,
        "output_price": None,
        "cached_price": None,
        "pricing_mode": "per_request",
        "cost_per_request": 0.10,
        "cost_class": "low",
        "aliases": ["deepseek-v4-flash-0731"],
    },
    {
        "provider_model_id": "deepseek-v4-pro",
        "display_name": "DeepSeek V4 Pro",
        "family": "DeepSeek V4",
        "maker": "DeepSeek",
        "description": (
            "Open MoE flagship with million-token context "
            "for coding and long agent runs."
        ),
        "context_window": 1_000_000,
        "input_price": 0.348,
        "output_price": 0.696,
        "cached_price": 0.000812,
        "pricing_mode": "per_token",
        "cost_class": "low",
    },
    {
        "provider_model_id": "deepseek-v4-pro-0813",
        "display_name": "DeepSeek V4 Pro 0813",
        "family": "DeepSeek V4",
        "maker": "DeepSeek",
        "description": "No description available",
        "context_window": 1_000_000,
        "input_price": None,
        "output_price": None,
        "cached_price": None,
        "pricing_mode": "per_request",
        "cost_per_request": 0.10,
        "cost_class": "low",
    },
    {
        "provider_model_id": "gemini-3-1-pro",
        "display_name": "Gemini 3.1 Pro",
        "family": "Gemini 3",
        "maker": "Google",
        "description": (
            "Advanced Gemini model for complex reasoning, "
            "coding, and multimodal analysis."
        ),
        "context_window": 1_000_000,
        "input_price": 2.0,
        "output_price": 12.0,
        "cached_price": 0.2,
        "pricing_mode": "per_token",
        "cost_class": "high",
    },
    {
        "provider_model_id": "gemini-3-flash",
        "display_name": "Gemini 3 Flash",
        "family": "Gemini 3",
        "maker": "Google",
        "description": (
            "New Gemini flash lane bringing frontier-style "
            "multimodal reasoning to cheaper runs."
        ),
        "context_window": 1_000_000,
        "input_price": 0.5,
        "output_price": 3.0,
        "cached_price": 0.05,
        "pricing_mode": "per_token",
        "cost_class": "low",
    },
    {
        "provider_model_id": "gemini-3-6-flash",
        "display_name": "Gemini 3.6 Flash",
        "family": "Gemini 3.6",
        "maker": "Google",
        "description": (
            "Fast Gemini 3.6 model for economical reasoning, "
            "coding, and long-context work."
        ),
        "context_window": 1_000_000,
        "input_price": 0.25,
        "output_price": 1.0,
        "cached_price": 0.025,
        "pricing_mode": "per_token",
        "cost_class": "low",
    },
    {
        "provider_model_id": "gemini-3-pro",
        "display_name": "Gemini 3 Pro",
        "family": "Gemini 3",
        "maker": "Google",
        "description": (
            "Legacy model retained for compatibility "
            "with older integrations."
        ),
        "context_window": 1_000_000,
        "input_price": 2.0,
        "output_price": 12.0,
        "cached_price": 0.2,
        "pricing_mode": "per_token",
        "cost_class": "high",
    },
    {
        "provider_model_id": "glm-5-2",
        "display_name": "GLM 5.2",
        "family": "GLM 5",
        "maker": "Z AI",
        "description": (
            "Open flagship GLM for long-horizon coding "
            "agents and million-token context work."
        ),
        "context_window": 1_000_000,
        "input_price": 1.4,
        "output_price": 4.4,
        "cached_price": 1.4,
        "pricing_mode": "per_token",
        "cost_class": "high",
    },
    {
        "provider_model_id": "gpt-5-4",
        "display_name": "GPT 5.4",
        "family": "GPT 5",
        "maker": "OpenAI",
        "description": (
            "Agent-ready GPT for coding and computer-use "
            "workflows at a lower cost."
        ),
        "context_window": 1_000_000,
        "input_price": 2.5,
        "output_price": 20.0,
        "cached_price": 0.25,
        "pricing_mode": "per_token",
        "cost_class": "premium",
    },
    {
        "provider_model_id": "gpt-5-5",
        "display_name": "GPT 5.5",
        "family": "GPT 5",
        "maker": "OpenAI",
        "description": (
            "Default frontier GPT for coding, computer use, "
            "research, and knowledge work."
        ),
        "context_window": 1_000_000,
        "input_price": 2.5,
        "output_price": 20.0,
        "cached_price": 0.25,
        "pricing_mode": "per_token",
        "cost_class": "premium",
    },
    {
        "provider_model_id": "gpt-5-6-luna",
        "display_name": "GPT 5.6 Luna",
        "family": "GPT 5.6",
        "maker": "OpenAI",
        "description": (
            "Cost-efficient GPT-5.6 model for fast, "
            "high-volume workloads."
        ),
        "context_window": 1_000_000,
        "input_price": 1.0,
        "output_price": 8.0,
        "cached_price": 0.1,
        "pricing_mode": "per_token",
        "cost_class": "low",
    },
    {
        "provider_model_id": "gpt-5-6-terra",
        "display_name": "GPT 5.6 Terra",
        "family": "GPT 5.6",
        "maker": "OpenAI",
        "description": (
            "Balanced GPT-5.6 model for capable, "
            "cost-efficient everyday work."
        ),
        "context_window": 1_000_000,
        "input_price": 2.5,
        "output_price": 20.0,
        "cached_price": 0.25,
        "pricing_mode": "per_token",
        "cost_class": "premium",
    },
    {
        "provider_model_id": "gpt-5.6",
        "display_name": "GPT 5.6",
        "family": "GPT 5.6",
        "maker": "OpenAI",
        "description": (
            "Frontier GPT-5.6 model for complex professional "
            "work, coding, and agentic workflows."
        ),
        "context_window": 1_000_000,
        "input_price": 1.5,
        "output_price": 12.0,
        "cached_price": 0.15,
        "pricing_mode": "per_token",
        "cost_class": "high",
    },
    {
        "provider_model_id": "gpt-5.6-luna",
        "display_name": "GPT 5.6 Luna",
        "family": "GPT 5.6",
        "maker": "OpenAI",
        "description": "No description available",
        "context_window": 1_000_000,
        "input_price": None,
        "output_price": None,
        "cached_price": None,
        "pricing_mode": "per_request",
        "cost_per_request": 0.10,
        "cost_class": "low",
        "aliases": ["gpt-5-6-luna"],
    },
    {
        "provider_model_id": "gpt-5.6-sol",
        "display_name": "GPT 5.6 Sol",
        "family": "GPT 5.6",
        "maker": "OpenAI",
        "description": (
            "Frontier GPT-5.6 model for complex professional "
            "work, coding, and agentic workflows."
        ),
        "context_window": 1_000_000,
        "input_price": 1.5,
        "output_price": 12.0,
        "cached_price": 0.15,
        "pricing_mode": "per_token",
        "cost_class": "high",
    },
]


class _TTLCache:
    """Simple TTL cache for SeekAI discovery."""

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


_seekai_list_cache = _TTLCache(_LIST_TTL_SECONDS)


def _seekai_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }


def _fetch_seekai_model_ids() -> list[str]:
    """Return the live SeekAI model list, or an empty list if unavailable."""
    cached = _seekai_list_cache.get()
    if cached is not None:
        return cached

    api_key = settings.seekai_api_key
    if not api_key:
        _seekai_list_cache.set([])
        return []

    base_url = (settings.seekai_base_url or _SEEKAI_BASE_URL).rstrip("/")
    url = f"{base_url}/models"
    try:
        response = httpx.get(
            url,
            headers=_seekai_headers(api_key),
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        model_ids = [m["id"] for m in data.get("data", []) if m.get("id")]
        logger.info("seekai.list_fetched", count=len(model_ids))
        _seekai_list_cache.set(model_ids)
        return model_ids
    except Exception as exc:
        logger.warning("seekai.list_fetch_failed", error=str(exc))
        _seekai_list_cache.set([])
        return []


def _model_config_from_entry(entry: dict[str, Any], available_ids: set[str]) -> dict[str, Any]:
    """Build a ModelConfig creation dict from a user-supplied catalog entry."""
    model_id = entry["provider_model_id"]
    family = entry.get("family") or infer_family(model_id)
    maker = entry.get("maker") or infer_maker(model_id, family)
    display_name = entry.get("display_name") or display_name_for_model(model_id)
    logo_domain = logo_domain_for_maker(maker)
    context = int(entry.get("context_window", 1_000_000))

    pricing = entry.get("pricing_mode", "per_token")
    pricing_block: dict[str, float | None] = {
        "input_per_million": entry.get("input_price"),
        "cached_input_per_million": entry.get("cached_price"),
        "output_per_million": entry.get("output_price"),
    }

    intelligence = get_model_intelligence(
        maker,
        family,
        model_id,
        provider="seekai",
        raw_name=display_name,
    )
    intelligence.pop("display_name", None)

    if model_id in available_ids or any(a in available_ids for a in entry.get("aliases", [])):
        availability = "available"
    elif settings.seekai_api_key:
        availability = "configured"
    else:
        availability = "unavailable"

    if context >= 1_000_000:
        context = 1_000_000

    cfg: dict[str, Any] = {
        "id": f"seekai/{model_id}",
        "provider": "seekai",
        "provider_model_id": model_id,
        "model": model_id,
        "maker": maker,
        "family": family,
        "display_name": display_name,
        "description": entry.get("description", ""),
        "purpose": f"{display_name} via SeekAI OpenAI-compatible gateway.",
        "capabilities": _SEEKAI_CAPABILITIES,
        "context_window": context,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_reasoning": True,
        "supports_multimodal": False,
        "latency_class": "fast",
        "cost_class": entry.get("cost_class", "standard"),
        "availability": availability,
        "default_temperature": 0.2,
        "recommended_for": ["sentinel"],
        "logo_domain": logo_domain,
        "protocol": "openai-compatible",
        "base_url": settings.seekai_base_url or _SEEKAI_BASE_URL,
        "pricing": pricing_block,
        "pricing_mode": pricing,
        "cost_per_request": entry.get("cost_per_request"),
        "gateway_type": "aggregator",
        "privacy_class": "standard",
        "access_class": "standard",
        "aliases": entry.get("aliases", []),
    }
    cfg.update(intelligence)
    return cfg


def get_seekai_model_configs() -> list[dict[str, Any]]:
    """Return ModelConfig creation dicts for the SeekAI catalog.

    The live /v1/models list is the source of truth. Static entries are only
    used to enrich display metadata for IDs the live endpoint confirms are
    reachable.  When the live list cannot be fetched (no key or network issue)
    we fall back to the static catalog with truthful availability.
    """
    available_ids = set(_fetch_seekai_model_ids())
    seen: dict[str, int] = {}
    configs: list[dict[str, Any]] = []

    if not available_ids:
        for entry in _SEEKAI_MODELS:
            cfg = _model_config_from_entry(entry, available_ids)
            slug = cfg["id"]
            if slug in seen:
                seen[slug] += 1
                cfg["id"] = f"{slug}-{seen[slug]}"
            else:
                seen[slug] = 0
            configs.append(cfg)
        return configs

    static_by_id: dict[str, dict[str, Any]] = {}
    for entry in _SEEKAI_MODELS:
        static_by_id[entry["provider_model_id"]] = entry
        for alias in entry.get("aliases", []):
            static_by_id.setdefault(alias, entry)

    for live_id in sorted(available_ids):
        entry = static_by_id.get(live_id)
        if entry:
            if entry["provider_model_id"] != live_id:
                entry = dict(entry)
                entry["provider_model_id"] = live_id
                entry["aliases"] = [
                    a for a in entry.get("aliases", []) if a != live_id
                ]
        else:
            entry = {
                "provider_model_id": live_id,
                "context_window": 1_000_000,
                "cost_class": "standard",
            }

        cfg = _model_config_from_entry(entry, available_ids)
        slug = cfg["id"]
        if slug in seen:
            seen[slug] += 1
            cfg["id"] = f"{slug}-{seen[slug]}"
        else:
            seen[slug] = 0
        configs.append(cfg)

    return configs


def invalidate_seekai_cache() -> None:
    """Clear SeekAI discovery cache."""
    _seekai_list_cache.clear()
