"""Infer model maker, family, and related identity metadata from provider IDs.

This is the backend normalization layer for model catalog UX.  All family/maker
inference lives here so the frontend can consume authoritative catalog fields
instead of reverse-engineering model names.
"""

from __future__ import annotations

from anvaya.llm.logo_domains import logo_domain_for_model

_MAKER_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("claude", "fable"), "Anthropic"),
    (("qwen3.8", "qwen-3.8"), "Alibaba"),
    (("dall-e",), "OpenAI"),
    (("gpt",), "OpenAI"),
    (("o1", "o3"), "OpenAI"),
    (("gemini",), "Google"),
    (("grok",), "xAI"),
    (("deepseek",), "DeepSeek"),
    (("glm",), "Z AI"),
    (("minimax",), "MiniMax"),
    (("kimi",), "Moonshot AI"),
    (("qwen",), "Alibaba"),
    (("muse", "llama"), "Meta"),
    (("nemotron",), "NVIDIA"),
    (("laguna",), "Poolside"),
    (("ox",), "Unknown / undisclosed"),
    (("inkling",), "Thinking Machines"),
    (("liquid", "lfm"), "LiquidAI"),
    (("ling",), "01.AI"),
    (("ring",), "Reka"),
    (("mimo",), "Mistral AI"),
    (("north",), "Cohere"),
    (("hy3", "hunyuan"), "Tencent"),
    (("big-pickle",), "Big Pickle"),
    (("x-preview",), "OpenCode"),
    (("yi",), "01.AI"),
    (("mistral",), "Mistral AI"),
    (("mixtral",), "Mistral AI"),
    (("phi",), "Microsoft"),
    (("command",), "Cohere"),
    (("aurora",), "Mistral AI"),
]


def _normalize_key(text: str) -> str:
    return text.lower().replace("_", "-").replace("/", "-")


def infer_maker(model_id: str, family: str = "") -> str:
    """Return the likely model maker for a model id or family string."""
    joined = _normalize_key(f"{model_id} {family}")
    for patterns, maker in _MAKER_PATTERNS:
        for pattern in patterns:
            if pattern in joined:
                return maker
    if "/" in model_id:
        vendor = model_id.split("/")[0]
        return _MAKER_BY_VENDOR.get(vendor, vendor.replace("-", " ").title())
    return ""


def infer_family(model_id: str, family_hint: str = "") -> str:
    """Return a clean, displayable family name from a model id or metadata."""
    if family_hint:
        return family_hint.replace("-", " ").title()
    name = model_id.split("/")[-1] if "/" in model_id else model_id
    name = name.lower().replace("_", "-")
    drop = (
        "free",
        "mini",
        "nano",
        "xs",
        "small",
        "medium",
        "large",
        "super",
        "ultra",
        "flash",
        "pro",
        "max",
        "instruct",
        "vision",
        "vlm",
    )
    parts = [p for p in name.split("-") if p and p not in drop]
    if not parts:
        return name.replace("-", " ").title()
    return " ".join(parts[:2]).title()


def logo_domain_for_maker(maker: str) -> str:
    """Return a real company domain for a model maker name."""
    key = maker.lower().replace(" ", "-").replace(".", "-")
    return logo_domain_for_model(f"{key}/model")


_MAKER_BY_VENDOR: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "meta": "Meta",
    "meta-llama": "Meta",
    "mistralai": "Mistral AI",
    "moonshotai": "Moonshot AI",
    "minimaxai": "MiniMax",
    "minimax": "MiniMax",
    "deepseek": "DeepSeek",
    "deepseek-ai": "DeepSeek",
    "nvidia": "NVIDIA",
    "qwen": "Alibaba",
    "x-ai": "xAI",
    "grok": "xAI",
    "poolside": "Poolside",
    "stepfun-ai": "StepFun",
    "stepfun": "StepFun",
    "thinkingmachines": "Thinking Machines",
    "z-ai": "Z AI",
    "zai-org": "Z AI",
    "bytedance": "ByteDance",
    "kimi": "Moonshot AI",
    "glm": "Z AI",
    "ling": "01.AI",
    "ring": "Reka",
    "mimo": "Mistral AI",
    "north": "Cohere",
    "hy3": "Tencent",
    "tencent": "Tencent",
    "big-pickle": "Big Pickle",
    "stealth": "OpenCode",
    "ox": "Unknown / undisclosed",
    "liquid": "LiquidAI",
    "xiaomimimo": "Xiaomi",
}
