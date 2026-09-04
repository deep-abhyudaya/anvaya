"""OpenRouter model catalog.

Queries https://openrouter.ai/api/v1/models and exposes free or all chat models.
Results are cached for one minute to avoid hitting the public endpoint on every
request.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Any

import httpx

from anvaya.config import settings
from anvaya.llm.catalog_intelligence import get_model_intelligence
from anvaya.llm.logo_domains import logo_domain_for_model
from anvaya.llm.model_identity import infer_family, infer_maker
from anvaya.logging import get_logger

logger = get_logger("anvaya.llm.openrouter_catalog")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
CACHE_TTL_SECONDS = 60

_STATIC_OPENROUTER_MODELS: list[dict[str, Any]] = [
    {
        "id": "openai/gpt-4o-mini",
        "name": "OpenAI: GPT-4o mini",
        "context_length": 128000,
        "description": "Small, fast multimodal model from OpenAI.",
        "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
        "architecture": {"modality": "text+image->text", "input_modalities": ["text", "image"]},
    },
    {
        "id": "openai/gpt-4o",
        "name": "OpenAI: GPT-4o",
        "context_length": 128000,
        "description": "Flagship multimodal model from OpenAI.",
        "pricing": {"prompt": "0.0000025", "completion": "0.00001"},
        "architecture": {"modality": "text+image->text", "input_modalities": ["text", "image"]},
    },
    {
        "id": "anthropic/claude-3.5-sonnet",
        "name": "Anthropic: Claude 3.5 Sonnet",
        "context_length": 200000,
        "description": "Strong general-purpose model from Anthropic.",
        "pricing": {"prompt": "0.000003", "completion": "0.000015"},
        "architecture": {"modality": "text+image->text", "input_modalities": ["text", "image"]},
    },
    {
        "id": "anthropic/claude-3-opus",
        "name": "Anthropic: Claude 3 Opus",
        "context_length": 200000,
        "description": "Most capable model from Anthropic.",
        "pricing": {"prompt": "0.000015", "completion": "0.000075"},
        "architecture": {"modality": "text+image->text", "input_modalities": ["text", "image"]},
    },
    {
        "id": "meta-llama/llama-3.1-8b-instruct",
        "name": "Meta: Llama 3.1 8B Instruct",
        "context_length": 131072,
        "description": "Compact open-weight instruction model from Meta.",
        "pricing": {"prompt": "0.00000005", "completion": "0.00000008"},
        "architecture": {"modality": "text->text", "input_modalities": ["text"]},
    },
    {
        "id": "mistralai/mistral-nemo",
        "name": "Mistral: Mistral Nemo",
        "context_length": 131000,
        "description": "Multilingual open model from Mistral AI.",
        "pricing": {"prompt": "0.00000013", "completion": "0.00000013"},
        "architecture": {"modality": "text->text", "input_modalities": ["text"]},
    },
    {
        "id": "deepseek/deepseek-chat",
        "name": "DeepSeek: DeepSeek V3",
        "context_length": 64000,
        "description": "General-purpose chat model from DeepSeek.",
        "pricing": {"prompt": "0.00000014", "completion": "0.00000028"},
        "architecture": {"modality": "text->text", "input_modalities": ["text"]},
    },
    {
        "id": "google/gemini-2.0-flash-exp:free",
        "name": "Google: Gemini 2.0 Flash (free)",
        "context_length": 1048576,
        "description": "Fast multimodal model from Google (free variant).",
        "pricing": {"prompt": "0", "completion": "0"},
        "architecture": {"modality": "text+image->text", "input_modalities": ["text", "image"]},
    },
    {
        "id": "qwen/qwen-2.5-72b-instruct",
        "name": "Qwen: Qwen2.5 72B Instruct",
        "context_length": 131072,
        "description": "Large open-weight instruction model from Alibaba Qwen.",
        "pricing": {"prompt": "0.00000023", "completion": "0.00000046"},
        "architecture": {"modality": "text->text", "input_modalities": ["text"]},
    },
    {
        "id": "x-ai/grok-2",
        "name": "xAI: Grok 2",
        "context_length": 131072,
        "description": "Reasoning model from xAI.",
        "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        "architecture": {"modality": "text->text", "input_modalities": ["text"]},
    },
]


def _is_free(pricing: dict[str, Any] | None) -> bool:
    """A model is free when both prompt and completion price are 0.0."""
    if not pricing:
        return False
    try:
        prompt = float(pricing.get("prompt", -1))
        completion = float(pricing.get("completion", -1))
        return prompt == 0.0 and completion == 0.0
    except (ValueError, TypeError):
        return False


def _cost_class(pricing: dict[str, Any] | None) -> str:
    """Map prompt+completion price per token to a cost bucket."""
    if not pricing:
        return "standard"
    try:
        total = float(pricing.get("prompt", 0)) + float(pricing.get("completion", 0))
    except (ValueError, TypeError):
        return "standard"
    if total == 0.0:
        return "free"
    per_million = total * 1_000_000
    if per_million < 1.0:
        return "low"
    if per_million < 10.0:
        return "standard"
    if per_million < 50.0:
        return "high"
    return "premium"


def _is_multimodal(architecture: dict[str, Any] | None) -> bool:
    if not architecture:
        return False
    inputs = architecture.get("input_modalities") or []
    return "image" in inputs


def _model_config_from_raw(model: dict[str, Any]) -> dict[str, Any]:
    """Return a dict that can be merged into ModelConfig creation."""
    model_id = model.get("id", "")
    name = model.get("name") or model_id
    architecture = model.get("architecture") or {}
    family = infer_family(model_id)
    maker = infer_maker(model_id, family)
    mid = model_id.lower()
    if mid.endswith("free-models-router") or mid.endswith("free_models_router"):
        maker = "OpenRouter"
        family = "Free Models Router"
    raw_name = model.get("name") or ""
    intelligence = get_model_intelligence(
        maker, family, model_id, provider="openrouter", raw_name=raw_name
    )
    pricing = model.get("pricing") or {}
    cfg = {
        "id": f"openrouter/{model_id}",
        "provider": "openrouter",
        "provider_model_id": model_id,
        "model": model_id,
        "maker": maker,
        "family": family,
        "display_name": name,
        "description": (model.get("description", "") or "")[:200],
        "purpose": "Chat, tool use, and reasoning through OpenRouter.",
        "capabilities": ["chat", "tools", "streaming", "structured-outputs"],
        "context_window": model.get("context_length", 128000),
        "supports_tools": True,
        "supports_streaming": True,
        "supports_reasoning": False,
        "supports_multimodal": _is_multimodal(architecture),
        "latency_class": "fast",
        "cost_class": _cost_class(pricing),
        "default_temperature": 0.2,
        "recommended_for": ["sentinel"],
        "logo_domain": logo_domain_for_model(model_id),
        "protocol": "openai-compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "pricing": {
            "input_per_million": float(pricing["prompt"]) if "prompt" in pricing else None,
            "cached_input_per_million": None,
            "output_per_million": float(pricing["completion"]) if "completion" in pricing else None,
        },
    }
    cfg.update(intelligence)
    return cfg


@lru_cache(maxsize=1)
def _cached_free_models(timestamp_bucket: int) -> list[dict[str, Any]]:
    """Fetch free OpenRouter models, bucketed by minute to avoid stale cache."""
    def _free_configs(src: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: dict[str, int] = {}
        configs: list[dict[str, Any]] = []
        for m in src:
            if not _is_free(m.get("pricing")):
                continue
            cfg = _model_config_from_raw(m)
            slug = cfg["id"]
            if slug in seen:
                seen[slug] += 1
                cfg["id"] = f"{slug}-{seen[slug]}"
            else:
                seen[slug] = 0
            configs.append(cfg)
        return configs

    try:
        return _free_configs(_fetch_raw_models())
    except Exception as exc:
        logger.warning("openrouter.free_catalog_failed", error=str(exc))
        return _free_configs(list(_STATIC_OPENROUTER_MODELS))


def _fetch_raw_models() -> list[dict[str, Any]]:
    """Call the OpenRouter /models endpoint and return raw model payloads."""
    api_key = settings.openrouter_api_key
    headers = {"HTTP-Referer": "http://localhost", "X-Title": "ANVAYA"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    response = httpx.get(
        f"{OPENROUTER_BASE_URL}/models",
        headers=headers,
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json().get("data", [])


def get_free_openrouter_models() -> list[dict[str, Any]]:
    """Return ModelConfig dicts for the current free OpenRouter models."""
    bucket = int(time.time() // CACHE_TTL_SECONDS)
    return _cached_free_models(bucket)
