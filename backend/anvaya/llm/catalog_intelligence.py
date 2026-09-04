"""Benchmark-grounded model catalog intelligence for ANVAYA.

This module is the single source of truth for ANVAYA role-fit scores,
public benchmark evidence, and recommendation confidence.  It does not
hardcode arbitrary bars; values are derived from the model intelligence
card that ships with the repository and must be updated as new public
or ANVAYA measurements arrive.
"""

from __future__ import annotations

import re
from typing import Any


def _norm(text: str) -> str:
    """Normalize a string for matching."""
    return text.lower().replace(" ", "-").replace(".", "-").replace("_", "-")


def _role_fit(scores: dict[str, int | None] | None) -> dict[str, float | None]:
    """Convert integer 0-100 scores to 0.0-1.0 floats, keeping None for N/A."""
    if not scores:
        return {}
    return {
        k: (v / 100.0 if v is not None and isinstance(v, (int, float)) else None)
        for k, v in scores.items()
    }


_ACRONYMS = {
    "glm": "GLM",
    "gpt": "GPT",
    "oss": "OSS",
    "llama": "Llama",
    "claude": "Claude",
    "kimi": "Kimi",
    "deepseek": "DeepSeek",
    "nemotron": "Nemotron",
    "muse": "Muse",
    "spark": "Spark",
    "laguna": "Laguna",
    "gemma": "Gemma",
    "grok": "Grok",
    "qwen": "Qwen",
    "lfm": "LFM",
    "ox": "Ox",
    "poolside": "Poolside",
    "z": "Z",
    "z.ai": "Z.ai",
    "minimax": "MiniMax",
    "mimo": "MiMo",
    "qwen3.8": "Qwen 3.8",
    "fp8": "FP8",
    "a4b": "A4B",
}


def _clean_raw_name(raw_name: str) -> str:
    """Strip maker prefix and free-tier suffix from a provider-supplied name."""
    name = (raw_name or "").strip()
    if ":" in name:
        name = name.split(":", 1)[1].strip()
    name = re.sub(r"\s*\(free\)\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+free\s*$", "", name, flags=re.IGNORECASE)
    return name.strip()


def _format_token(token: str) -> str:
    """Format a single token with known acronym and size capitalization."""
    token = token.strip()
    if not token:
        return ""
    lower = token.lower()
    if lower in _ACRONYMS:
        return _ACRONYMS[lower]
    for short, canonical in sorted(_ACRONYMS.items(), key=lambda x: -len(x[0])):
        if lower.startswith(short) and len(lower) > len(short):
            rest = token[len(short):]
            return canonical + _format_token(rest)
    if re.fullmatch(r"[\d.]+[a-z]", token):
        return token[:-1] + token[-1].upper()
    if re.fullmatch(r"[\d.]+[a-z]\d*", token, re.IGNORECASE):
        m = re.fullmatch(r"([\d.]+)([a-z])(\d*)", token, re.IGNORECASE)
        if m:
            return m.group(1) + m.group(2).upper() + m.group(3)
    return token.capitalize()


def _pattern_display_name(pattern: str) -> str:
    """Turn a catalog pattern into a human display name."""
    pattern = pattern.replace("_", "-")
    tokens = pattern.split("-")
    tokens = [_format_token(t) for t in tokens if t]
    return " ".join(tokens)


def _display_name_from_model_id(model_id: str) -> str:
    """Best-effort display name from a raw model id when no catalog matches."""
    tail = model_id.split("/")[-1]
    tail = re.sub(r"[-_]free$", "", tail, flags=re.IGNORECASE)
    tail = re.sub(r"[-_]", " ", tail)
    tail = re.sub(r"\s+", " ", tail).strip()
    tokens = tail.split()
    tokens = [_format_token(t) for t in tokens if t]
    return " ".join(tokens)


def display_name_for_model(
    model_id: str,
    raw_name: str | None = None,
    catalog_entry: _CatalogEntry | None = None,
) -> str:
    """Return a clean, maker-free display name for a model.

    - Prefer the provider's own human name, stripped of maker and "(free)".
    - Next, use the catalog entry's explicit or pattern-derived display name.
    - Finally, derive from the model id.
    """
    if raw_name:
        cleaned = _clean_raw_name(raw_name)
        if cleaned:
            return cleaned
    if catalog_entry:
        if catalog_entry.display_name:
            return catalog_entry.display_name
        if catalog_entry.patterns:
            return _pattern_display_name(catalog_entry.patterns[0])
    return _display_name_from_model_id(model_id)


def _evidence_confidence(label: str) -> str:
    """Normalize evidence-confidence labels to the UI vocabulary."""
    mapping = {
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "unknown": "Provisional",
        "medium-high": "Medium-High",
        "medium-low": "Low-Medium",
        "low-medium": "Low-Medium",
    }
    return mapping.get(label.lower(), label.capitalize())


def _evidence_level(label: str | None) -> str:
    """Collapse any evidence label to High / Medium / Provisional."""
    if not label:
        return "Provisional"
    mapping = {
        "high": "High",
        "medium-high": "Medium",
        "medium": "Medium",
        "medium-low": "Provisional",
        "low-medium": "Provisional",
        "low": "Provisional",
        "provisional": "Provisional",
        "unknown": "Provisional",
    }
    return mapping.get(label.lower(), "Provisional")


class _CatalogEntry:
    """A single benchmark-grounded catalog entry."""

    def __init__(
        self,
        makers: list[str],
        patterns: list[str],
        profile_fit: dict[str, int | None],
        evidence_confidence: str,
        recommendation_confidence: str,
        best_for: list[str],
        benchmark_evidence: list[dict[str, str]],
        quality_class: str,
        display_name: str | None = None,
        evidence_level: str | None = None,
        fit_reason: str | None = None,
        limitations: str | None = None,
        provisional: bool | None = None,
        experimental: bool | None = None,
        gateway_type: str = "",
    ):
        self.makers = [_norm(m) for m in makers]
        self.patterns = patterns
        self.profile_fit = _role_fit(profile_fit)
        self.evidence_confidence = _evidence_confidence(evidence_confidence)
        self.evidence_level = _evidence_level(evidence_level or evidence_confidence)
        self.recommendation_confidence = _evidence_confidence(recommendation_confidence)
        self.best_for = best_for
        self.benchmark_evidence = benchmark_evidence
        self.quality_class = quality_class
        self.display_name = display_name
        self.provisional = provisional if provisional is not None else True
        self.experimental = (
            experimental if experimental is not None else quality_class == "experimental"
        )
        self.gateway_type = gateway_type
        self.fit_reason = fit_reason or self._derive_fit_reason()
        self.limitations = limitations or self._derive_limitations()

    def _derive_fit_reason(self) -> str:
        if self.quality_class == "orchestrator":
            return (
                "ANVAYA's deterministic local orchestrator provides uniform high fit "
                "across Sentinel, Pathfinder, Responder, and Auditor control flows."
            )
        if self.quality_class == "router":
            return (
                "This is a model router, not a foundation model; the Responder score "
                "reflects fast, low-cost routing and tool-execution potential."
            )
        if not self.profile_fit or all(v is None for v in self.profile_fit.values()):
            return (
                "No matching public evidence; ANVAYA fit is a provisional estimate "
                "based on model scale and provider metadata."
            )
        sorted_roles = sorted(
            ((k, v) for k, v in self.profile_fit.items() if v is not None),
            key=lambda x: x[1],
            reverse=True,
        )
        top_role, top_score = sorted_roles[0]
        second_role, second_score = sorted_roles[1] if len(sorted_roles) > 1 else (None, 0.0)
        primary = self.best_for[0] if self.best_for else "general tasks"
        if self.evidence_level == "High":
            return (
                f"Strong public benchmark evidence supports a {top_role.title()} fit of "
                f"{top_score:.0%} and a {second_role.title()} fit of {second_score:.0%}; "
                f"recommended for {primary}."
            )
        if self.evidence_level == "Medium":
            return (
                f"Good public/provider evidence supports a {top_role.title()} fit of "
                f"{top_score:.0%}; useful for {primary}."
            )
        return (
            f"Limited public evidence; ANVAYA fit is a provisional estimate led by "
            f"{top_role.title()} ({top_score:.0%}). Treat as experimental for {primary}."
        )

    def _derive_limitations(self) -> str:
        if self.quality_class == "orchestrator":
            return (
                "Not a generative foundation model; cannot perform open-ended reasoning "
                "or creative synthesis outside ANVAYA policy."
            )
        if self.quality_class == "router":
            return (
                "This is a model router, not a foundation model. The ANVAYA fit reflects "
                "routing quality; actual capability depends on the selected backend."
            )
        if self.quality_class == "experimental":
            return (
                "Experimental or limited-coverage model; verify tool-use, long-context "
                "behaviour, and reasoning before production deployment."
            )
        if self.evidence_level == "Provisional":
            return (
                "Public benchmark coverage is limited; ANVAYA fit scores are provisional "
                "estimates and should be validated on real security workloads."
            )
        return (
            "ANVAYA fit is a role-specific estimate, not a universal benchmark score. "
            "Provider-reported results may not reflect ANVAYA security workloads."
        )

    def matches(self, maker: str, family: str, model_id: str) -> bool:
        """Check whether a model matches this entry."""
        return self.match_score(maker, family, model_id) > 0

    def match_score(self, maker: str, family: str, model_id: str) -> int:
        """Return the length of the longest matching pattern, or 0 if none."""
        maker_norm = _norm(maker)
        if maker_norm not in self.makers:
            return 0
        model_norm = _norm(model_id)
        family_norm = _norm(family)
        best = 0
        for pattern in self.patterns:
            pat = _norm(pattern)
            if pat in model_norm or pat in family_norm:
                best = max(best, len(pat))
        return best


_CATALOG_DATA: list[dict[str, Any]] = [   {   'makers': ['ANVAYA'],
        'patterns': ['local-policy', 'local-orchestrator', 'orchestrator'],
        'profile_fit': {'sentinel': 95, 'pathfinder': 95, 'responder': 95, 'auditor': 95},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['orchestration', 'policy fallback', 'deterministic control'],
        'benchmark_evidence': [],
        'quality_class': 'orchestrator',
        'display_name': 'Local Orchestrator',
        'fit_reason': 'ANVAYA local orchestrator provides deterministic policy, tool selection, '
                      'and fallback with uniform high orchestrator fit across all four roles.',
        'limitations': 'Not a generative foundation model; cannot perform open-ended reasoning or '
                       'creative synthesis outside ANVAYA policy.',
        'gateway_type': 'orchestrator',
        'provisional': False,
        'experimental': False},
    {   'makers': ['anthropic'],
        'patterns': ['claude-opus-5'],
        'profile_fit': {'sentinel': 98, 'pathfinder': 99, 'responder': 97, 'auditor': 99},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['complex autonomous investigations', 'root-cause analysis', 'final synthesis'],
        'benchmark_evidence': [   {   'name': 'AA-Briefcase',
                                      'value': '1714',
                                      'source': 'Independent'},
                                  {'name': 'Vellum HLE', 'value': '64.7%', 'source': 'Independent'},
                                  {   'name': 'Arena',
                                      'value': 'frontier tier',
                                      'source': 'Independent'}],
        'quality_class': 'frontier'},
    {   'makers': ['anthropic'],
        'patterns': ['claude-opus-4.8', 'claude-opus-4-8'],
        'profile_fit': {'sentinel': 95, 'pathfinder': 97, 'responder': 94, 'auditor': 96},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['deep investigation', 'coding/tool tasks', 'verification'],
        'benchmark_evidence': [   {   'name': 'AA-Briefcase',
                                      'value': '1340',
                                      'source': 'Independent'},
                                  {'name': 'Vellum HLE', 'value': '57.9%', 'source': 'Independent'},
                                  {   'name': 'Arena coding',
                                      'value': 'leading agentic coding',
                                      'source': 'Independent'}],
        'quality_class': 'frontier'},
    {   'makers': ['anthropic'],
        'patterns': ['claude-sonnet-5'],
        'profile_fit': {'sentinel': 91, 'pathfinder': 94, 'responder': 93, 'auditor': 90},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'High',
        'best_for': ['coding', 'analysis', 'cost-efficient agent work'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'limited frontier evidence',
                                      'source': 'Provider-reported'}],
        'quality_class': 'frontier'},
    {   'makers': ['anthropic'],
        'patterns': ['claude-fable-5'],
        'profile_fit': {'sentinel': 99, 'pathfinder': 99, 'responder': 99, 'auditor': 99},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['creative synthesis', 'controlled agent workflows', 'analysis'],
        'benchmark_evidence': [   {   'name': 'SeekAI description',
                                      'value': 'creative writing and analysis',
                                      'source': 'Provider-reported'}],
        'quality_class': 'frontier',
        'provisional': True,
        'display_name': 'Claude Fable 5'},
    {   'makers': ['openai'],
        'patterns': ['gpt-5.6-sol', 'gpt-5-6-sol'],
        'profile_fit': {'sentinel': 94, 'pathfinder': 95, 'responder': 94, 'auditor': 92},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['general agent work', 'coding/tool use', 'interactive execution'],
        'benchmark_evidence': [   {   'name': 'AA-Briefcase',
                                      'value': '1503',
                                      'source': 'Independent'},
                                  {'name': 'Vellum HLE', 'value': '47.2%', 'source': 'Independent'},
                                  {   'name': 'Arena coding/agent',
                                      'value': 'high tier',
                                      'source': 'Independent'}],
        'quality_class': 'frontier'},
    {   'makers': ['openai'],
        'patterns': ['gpt-5.6', 'gpt-5-6'],
        'profile_fit': {'sentinel': 94, 'pathfinder': 96, 'responder': 94, 'auditor': 93},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['general agent work', 'coding/tool use', 'investigation planning'],
        'benchmark_evidence': [   {   'name': 'AA-Briefcase',
                                      'value': '1503',
                                      'source': 'Independent'},
                                  {'name': 'Vellum HLE', 'value': '47.2%', 'source': 'Independent'},
                                  {   'name': 'Arena coding/agent',
                                      'value': 'high tier',
                                      'source': 'Independent'}],
        'quality_class': 'frontier'},
    {   'makers': ['openai'],
        'patterns': ['gpt-5-6-terra', 'gpt-5.6-terra'],
        'profile_fit': {'sentinel': 93, 'pathfinder': 94, 'responder': 92, 'auditor': 91},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['frontier work', 'coding', 'research'],
        'benchmark_evidence': [   {   'name': 'OpenAI tiering',
                                      'value': 'frontier',
                                      'source': 'Provider-reported'}],
        'quality_class': 'frontier'},
    {   'makers': ['openai'],
        'patterns': ['gpt-5-6-luna', 'gpt-5.6-luna'],
        'profile_fit': {'sentinel': 91, 'pathfinder': 92, 'responder': 95, 'auditor': 89},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['fast high-volume workloads', 'responder tasks', 'coding'],
        'benchmark_evidence': [   {   'name': 'OpenAI tiering',
                                      'value': 'frontier-fast',
                                      'source': 'Provider-reported'}],
        'quality_class': 'frontier'},
    {   'makers': ['openai'],
        'patterns': ['gpt-5-5', 'gpt-5.5'],
        'profile_fit': {'sentinel': 93, 'pathfinder': 95, 'responder': 94, 'auditor': 92},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['general agent work', 'coding', 'computer use'],
        'benchmark_evidence': [   {   'name': 'SWE-Bench Pro',
                                      'value': '58.6%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'Terminal-Bench 2.0',
                                      'value': '82.7%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'ARC-AGI-2',
                                      'value': '85.0%',
                                      'source': 'Provider-reported'}],
        'quality_class': 'frontier'},
    {   'makers': ['openai'],
        'patterns': ['gpt-5-4', 'gpt-5.4'],
        'profile_fit': {'sentinel': 92, 'pathfinder': 93, 'responder': 93, 'auditor': 91},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['agent work', 'computer use', 'coding'],
        'benchmark_evidence': [   {   'name': 'SWE-Bench Pro',
                                      'value': '57.7%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'Terminal-Bench 2.0',
                                      'value': '75.1%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'OSWorld-Verified',
                                      'value': '75.0%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'BrowseComp',
                                      'value': '82.7%',
                                      'source': 'Provider-reported'}],
        'quality_class': 'frontier'},
    {   'makers': ['google'],
        'patterns': ['gemini-3.1-pro'],
        'profile_fit': {'sentinel': 91, 'pathfinder': 93, 'responder': 92, 'auditor': 91},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['multimodal reasoning', 'complex coding', 'long-context analysis'],
        'benchmark_evidence': [   {   'name': 'SWE-Bench Verified',
                                      'value': '80.6%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'SWE-Bench Pro',
                                      'value': '54.2%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'Terminal-Bench 2.0',
                                      'value': '68.5%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'BrowseComp',
                                      'value': '85.9%',
                                      'source': 'Provider-reported'}],
        'quality_class': 'frontier'},
    {   'makers': ['google'],
        'patterns': ['gemini-3-pro'],
        'profile_fit': {'sentinel': 88, 'pathfinder': 90, 'responder': 89, 'auditor': 88},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['multimodal reasoning', 'long-context analysis'],
        'benchmark_evidence': [   {   'name': 'Gemini family',
                                      'value': 'frontier multimodal',
                                      'source': 'Provider-reported'}],
        'quality_class': 'frontier'},
    {   'makers': ['google'],
        'patterns': ['gemini-3-flash'],
        'profile_fit': {'sentinel': 82, 'pathfinder': 84, 'responder': 91, 'auditor': 80},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['fast multimodal reasoning', 'responder tasks', 'long context'],
        'benchmark_evidence': [   {   'name': 'Gemini family',
                                      'value': 'frontier flash',
                                      'source': 'Provider-reported'}],
        'quality_class': 'frontier'},
    {   'makers': ['moonshot ai', 'moonshot'],
        'patterns': ['kimi-k3'],
        'profile_fit': {'sentinel': 94, 'pathfinder': 96, 'responder': 93, 'auditor': 92},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['coding', 'long investigations', 'alternate provider path'],
        'benchmark_evidence': [   {   'name': 'AA-Briefcase',
                                      'value': '1542',
                                      'source': 'Independent'},
                                  {'name': 'Vellum HLE', 'value': '56.0%', 'source': 'Independent'},
                                  {   'name': 'Arena coding/agent',
                                      'value': 'leading',
                                      'source': 'Independent'}],
        'quality_class': 'strong'},
    {   'makers': ['deepseek'],
        'patterns': ['deepseek-v4-pro'],
        'profile_fit': {'sentinel': 90, 'pathfinder': 94, 'responder': 89, 'auditor': 88},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['coding', 'long agent runs', 'agentic investigation'],
        'benchmark_evidence': [   {   'name': 'OpenCode usage',
                                      'value': 'leading',
                                      'source': 'OpenCode usage'},
                                  {   'name': 'OpenRouter usage',
                                      'value': 'low-cost agentic coding',
                                      'source': 'OpenRouter usage'}],
        'quality_class': 'strong'},
    {   'makers': ['deepseek'],
        'patterns': ['deepseek-v4-pro-0813'],
        'profile_fit': {'sentinel': 88, 'pathfinder': 93, 'responder': 87, 'auditor': 86},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'High',
        'best_for': ['coding', 'long agent runs', 'snapshot variant'],
        'benchmark_evidence': [   {   'name': 'Base model evidence',
                                      'value': 'inherited from DeepSeek V4 Pro',
                                      'source': 'Provider-reported'}],
        'quality_class': 'strong'},
    {   'makers': ['deepseek'],
        'patterns': ['deepseek-v4-flash'],
        'profile_fit': {'sentinel': 86, 'pathfinder': 91, 'responder': 88, 'auditor': 84},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['coding', 'agentic investigation', 'cost-efficient serious workloads'],
        'benchmark_evidence': [   {   'name': 'AA-Briefcase',
                                      'value': '1285',
                                      'source': 'Independent'},
                                  {'name': 'Vellum HLE', 'value': '51.6%', 'source': 'Independent'},
                                  {   'name': 'SWE-Bench Verified',
                                      'value': '72.4%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'LiveCodeBench v6',
                                      'value': '90.9%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'RULER (1M)',
                                      'value': '57.0%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'OpenCode usage',
                                      'value': 'leading',
                                      'source': 'OpenCode usage'}],
        'quality_class': 'strong'},
    {   'makers': ['deepseek'],
        'patterns': ['deepseek-v4-flash-0731'],
        'profile_fit': {'sentinel': 84, 'pathfinder': 89, 'responder': 86, 'auditor': 82},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'High',
        'best_for': ['coding', 'agentic investigation', 'snapshot variant'],
        'benchmark_evidence': [   {   'name': 'Base model evidence',
                                      'value': 'inherited from DeepSeek V4 Flash',
                                      'source': 'Provider-reported'}],
        'quality_class': 'strong'},
    {   'makers': ['z ai', 'z'],
        'patterns': ['glm-5.2', 'glm-5-2'],
        'profile_fit': {'sentinel': 87, 'pathfinder': 91, 'responder': 88, 'auditor': 86},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'High',
        'best_for': ['lower-cost reasoning', 'coding/analysis', 'fallback'],
        'benchmark_evidence': [   {'name': 'Vellum HLE', 'value': '54.7%', 'source': 'Independent'},
                                  {   'name': 'AA-Briefcase',
                                      'value': '1252',
                                      'source': 'Independent'},
                                  {   'name': 'OpenRouter usage',
                                      'value': 'AA Index 51',
                                      'source': 'OpenRouter usage'}],
        'quality_class': 'strong'},
    {   'makers': ['z ai', 'z'],
        'patterns': ['glm-5.3-flash', 'glm-5-3-flash'],
        'profile_fit': {'sentinel': 87, 'pathfinder': 92, 'responder': 88, 'auditor': 85},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'High',
        'best_for': ['fast multimodal reasoning', 'long context', 'fallback'],
        'benchmark_evidence': [   {   'name': 'OpenCode usage',
                                      'value': 'leading',
                                      'source': 'OpenCode usage'}],
        'quality_class': 'strong'},
    {   'makers': ['minimax'],
        'patterns': ['minimax-m3', 'm3'],
        'profile_fit': {'sentinel': 90, 'pathfinder': 93, 'responder': 91, 'auditor': 87},
        'evidence_confidence': 'High',
        'evidence_level': 'High',
        'recommendation_confidence': 'High',
        'best_for': ['exploratory reasoning', 'coding', 'alternate routing'],
        'benchmark_evidence': [   {   'name': 'SWE-Bench Pro',
                                      'value': '59.0',
                                      'source': 'Provider-reported'},
                                  {   'name': 'Terminal-Bench 2.1',
                                      'value': '66.0',
                                      'source': 'Provider-reported'},
                                  {   'name': 'BrowseComp',
                                      'value': '83.52',
                                      'source': 'Provider-reported'},
                                  {   'name': 'MCP Atlas',
                                      'value': '74.2',
                                      'source': 'Provider-reported'},
                                  {   'name': 'OpenRouter usage',
                                      'value': 'AA Index 44',
                                      'source': 'OpenRouter usage'},
                                  {   'name': 'OpenCode usage',
                                      'value': 'leading',
                                      'source': 'OpenCode usage'}],
        'quality_class': 'strong'},
    {   'makers': ['minimax'],
        'patterns': ['minimax-m2.7', 'minimax-m2-7', 'm2.7'],
        'profile_fit': {'sentinel': 87, 'pathfinder': 91, 'responder': 89, 'auditor': 85},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['exploratory reasoning', 'alternate routing'],
        'benchmark_evidence': [   {   'name': 'SWE-Pro',
                                      'value': '56.22%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'VIBE-Pro',
                                      'value': '55.6%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'Terminal Bench 2',
                                      'value': '57.0%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'OpenHands SWE-bench',
                                      'value': '75.6',
                                      'source': 'Harness-specific'},
                                  {   'name': 'OpenCode usage',
                                      'value': 'leading',
                                      'source': 'OpenCode usage'}],
        'quality_class': 'strong'},
    {   'makers': ['nvidia'],
        'patterns': ['nemotron-3-ultra'],
        'profile_fit': {'sentinel': 90, 'pathfinder': 91, 'responder': 90, 'auditor': 91},
        'evidence_confidence': 'Medium-High',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'High',
        'best_for': [   'huge security-evidence contexts',
                        'long-context reasoning',
                        'tool-heavy workflows'],
        'benchmark_evidence': [   {   'name': 'SWE-Bench Verified',
                                      'value': '71.9%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'Terminal-Bench 2.1',
                                      'value': '56.4%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'LiveCodeBench v6',
                                      'value': '89.0%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'RULER (1M)',
                                      'value': '94.7%',
                                      'source': 'Provider-reported'},
                                  {'name': 'GPQA', 'value': '87.0%', 'source': 'Provider-reported'},
                                  {   'name': 'OpenRouter usage',
                                      'value': 'AA Index 48',
                                      'source': 'OpenRouter usage'},
                                  {   'name': 'OpenCode usage',
                                      'value': 'leading',
                                      'source': 'OpenCode usage'}],
        'quality_class': 'strong'},
    {   'makers': ['nvidia'],
        'patterns': ['nemotron-3-super'],
        'profile_fit': {'sentinel': 86, 'pathfinder': 88, 'responder': 87, 'auditor': 88},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'High',
        'best_for': ['long-context reasoning', 'general analysis', 'NVIDIA-native deployment'],
        'benchmark_evidence': [   {   'name': 'OpenHands SWE-bench',
                                      'value': '60.47%',
                                      'source': 'Harness-specific'},
                                  {   'name': 'OpenCode SWE-bench',
                                      'value': '59.20%',
                                      'source': 'Harness-specific'}],
        'quality_class': 'strong'},
    {   'makers': ['nvidia'],
        'patterns': ['nemotron-3.5-lightning'],
        'profile_fit': {'sentinel': 74, 'pathfinder': 78, 'responder': 83, 'auditor': 71},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['classification', 'routing', 'lightweight agent steps', 'fast summaries'],
        'benchmark_evidence': [   {   'name': 'SWE-bench Verified',
                                      'value': '51.56',
                                      'source': 'Provider-reported'},
                                  {   'name': 'Terminal-Bench 2.1',
                                      'value': '24.58',
                                      'source': 'Provider-reported'},
                                  {'name': 'GPQA', 'value': '76.89', 'source': 'Provider-reported'},
                                  {   'name': 'PinchBench',
                                      'value': '85.37',
                                      'source': 'Provider-reported'},
                                  {   'name': 'BrowseComp',
                                      'value': '36.97',
                                      'source': 'Provider-reported'},
                                  {   'name': 'OpenCode usage',
                                      'value': 'leading',
                                      'source': 'OpenCode usage'}],
        'quality_class': 'strong'},
    {   'makers': ['meta'],
        'patterns': ['muse-spark-1.2', 'muse-spark'],
        'profile_fit': {'sentinel': 86, 'pathfinder': 92, 'responder': 87, 'auditor': 85},
        'evidence_confidence': 'Medium-High',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'High',
        'best_for': ['coding agents', 'repository work', 'long-context/tool-heavy workloads'],
        'benchmark_evidence': [   {   'name': 'Terminal-Bench 2.1',
                                      'value': '82.9%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'DeepSWE 1.1',
                                      'value': '59.3%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'Meta internal coding',
                                      'value': '70.6%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'Artificial Analysis Intelligence Index',
                                      'value': '54',
                                      'source': 'Independent'},
                                  {   'name': 'OpenCode usage',
                                      'value': 'leading',
                                      'source': 'OpenCode usage'}],
        'quality_class': 'strong'},
    {   'makers': ['mistral ai', 'mistral'],
        'patterns': ['mimo-v2.5', 'mimo'],
        'profile_fit': {'sentinel': 80, 'pathfinder': 87, 'responder': 84, 'auditor': 78},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['coding', 'agentic tool use', 'inexpensive experimentation'],
        'benchmark_evidence': [   {   'name': 'OpenCode usage',
                                      'value': 'leading',
                                      'source': 'OpenCode usage'}],
        'quality_class': 'strong'},
    {   'makers': ['stepfun'],
        'patterns': ['step-3.7-flash', 'step-3-7-flash'],
        'profile_fit': {'sentinel': 78, 'pathfinder': 84, 'responder': 82, 'auditor': 75},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['fast general analysis', 'classification', 'lightweight coding'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'limited provider evidence',
                                      'source': 'Provider-reported'}],
        'quality_class': 'strong'},
    {   'makers': ['alibaba'],
        'patterns': ['qwen3.8-27b-fp8', 'qwen-3.8-27b-fp8', 'qwen3.8'],
        'profile_fit': {'sentinel': 78, 'pathfinder': 84, 'responder': 81, 'auditor': 76},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['open-weight reasoning', 'coding', 'experimentation'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'limited provider evidence',
                                      'source': 'Provider-reported'}],
        'quality_class': 'specialist'},
    {   'makers': ['google'],
        'patterns': ['gemma-4-31b'],
        'profile_fit': {'sentinel': 80, 'pathfinder': 84, 'responder': 82, 'auditor': 79},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['general analysis', 'lightweight coding', 'edge deployment'],
        'benchmark_evidence': [   {   'name': 'MMLU Pro',
                                      'value': '85.2%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'LiveCodeBench v6',
                                      'value': '80.0%',
                                      'source': 'Provider-reported'},
                                  {'name': 'GPQA', 'value': '84.3%', 'source': 'Provider-reported'},
                                  {   'name': 'Tau2',
                                      'value': '76.9%',
                                      'source': 'Provider-reported'}],
        'quality_class': 'specialist'},
    {   'makers': ['google'],
        'patterns': ['gemma-4-26b', 'gemma-4-26b-a4b'],
        'profile_fit': {'sentinel': 77, 'pathfinder': 81, 'responder': 80, 'auditor': 76},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['general analysis', 'lightweight coding', 'edge deployment'],
        'benchmark_evidence': [   {   'name': 'MMLU Pro',
                                      'value': '82.6%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'LiveCodeBench v6',
                                      'value': '77.1%',
                                      'source': 'Provider-reported'},
                                  {'name': 'GPQA', 'value': '82.3%', 'source': 'Provider-reported'},
                                  {   'name': 'Tau2',
                                      'value': '68.2%',
                                      'source': 'Provider-reported'}],
        'quality_class': 'specialist'},
    {   'makers': ['meta'],
        'patterns': ['llama-3.2-90b-vision-instruct', 'llama-3-2-90b-vision'],
        'profile_fit': {'sentinel': 74, 'pathfinder': 78, 'responder': 77, 'auditor': 79},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['visual security evidence', 'diagrams', 'multimodal analysis'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'vision/multimodal',
                                      'source': 'Provider-reported'}],
        'quality_class': 'specialist'},
    {   'makers': ['meta'],
        'patterns': ['llama-3.2-11b-vision-instruct', 'llama-3-2-11b-vision'],
        'profile_fit': {'sentinel': 54, 'pathfinder': 58, 'responder': 61, 'auditor': 53},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Low',
        'best_for': ['visual security evidence', 'screenshots', 'multimodal analysis'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'vision/multimodal',
                                      'source': 'Provider-reported'}],
        'quality_class': 'utility'},
    {   'makers': ['openai'],
        'patterns': ['gpt-oss-20b', 'gpt-oss-20b-instruct'],
        'profile_fit': {'sentinel': 62, 'pathfinder': 67, 'responder': 69, 'auditor': 61},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['cheap general analysis', 'classification', 'fallback'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'limited OpenAI guidance',
                                      'source': 'Provider-reported'}],
        'quality_class': 'specialist'},
    {   'makers': ['cohere', 'north'],
        'patterns': ['north-mini-code'],
        'profile_fit': {'sentinel': 61, 'pathfinder': 72, 'responder': 67, 'auditor': 58},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['classification', 'lightweight coding'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'specialist'},
    {   'makers': ['nvidia'],
        'patterns': ['nemotron-3-nano-omni', 'nemotron-3-nano'],
        'profile_fit': {'sentinel': 56, 'pathfinder': 62, 'responder': 72, 'auditor': 54},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['classification', 'routing', 'lightweight agent steps'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'limited NVIDIA evidence',
                                      'source': 'Provider-reported'}],
        'quality_class': 'specialist'},
    {   'makers': ['nvidia'],
        'patterns': ['nemotron-3.5-content-safety'],
        'profile_fit': {'sentinel': 89, 'pathfinder': 42, 'responder': 51, 'auditor': 94},
        'evidence_confidence': 'Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['content moderation', 'safety audit'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'content-safety specialist',
                                      'source': 'Provider-reported'}],
        'quality_class': 'specialist',
        'fit_reason': 'Specialised content-safety model with very strong Sentinel and Auditor '
                      'scores; the Responder and Pathfinder scores are intentionally lower.',
        'limitations': 'Not designed for open-ended agentic work. Strong at safety classification '
                       'and audit but weak at coding and long-horizon investigation.'},
    {   'makers': ['big pickle'],
        'patterns': ['big-pickle'],
        'profile_fit': {'sentinel': 70, 'pathfinder': 77, 'responder': 72, 'auditor': 66},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['experimentation'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['tencent'],
        'patterns': ['hy3'],
        'profile_fit': {'sentinel': 73, 'pathfinder': 79, 'responder': 76, 'auditor': 69},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['experimentation'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['poolside'],
        'patterns': ['laguna-xs-2.1', 'laguna-xs-2-1'],
        'profile_fit': {'sentinel': 67, 'pathfinder': 74, 'responder': 72, 'auditor': 65},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['experimentation'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['poolside'],
        'patterns': ['laguna-s-2.1', 'laguna-s-2-1'],
        'profile_fit': {'sentinel': 70, 'pathfinder': 78, 'responder': 74, 'auditor': 68},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['experimentation'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['poolside'],
        'patterns': ['laguna'],
        'profile_fit': {'sentinel': 67, 'pathfinder': 74, 'responder': 72, 'auditor': 65},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['experimentation'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['mistral ai', 'mistral', 'nvidia', 'mistralai'],
        'patterns': ['mistral-nemotron'],
        'profile_fit': {'sentinel': 70, 'pathfinder': 76, 'responder': 75, 'auditor': 68},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['general analysis', 'NVIDIA-native deployment'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['thinking machines'],
        'patterns': ['inkling-small'],
        'profile_fit': {'sentinel': 64, 'pathfinder': 71, 'responder': 70, 'auditor': 62},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['exploratory reasoning', 'alternate routing'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['thinking machines'],
        'patterns': ['inkling'],
        'profile_fit': {'sentinel': 70, 'pathfinder': 78, 'responder': 73, 'auditor': 67},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['exploratory reasoning', 'alternate routing'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['01.ai', 'ling'],
        'patterns': ['ling-3.0-flash-fin', 'ling-3-0-flash-fin'],
        'profile_fit': {'sentinel': 67, 'pathfinder': 73, 'responder': 76, 'auditor': 65},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['fast general analysis', 'alternate routing'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['', 'dots3', 'dots studio', 'dots-studio'],
        'patterns': ['dots3-note-preview', 'dots3-note', 'dots-3-note-preview', 'dots-3-note'],
        'profile_fit': {'sentinel': 54, 'pathfinder': 64, 'responder': 61, 'auditor': 52},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['experimentation'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['', 'lyria', 'google'],
        'patterns': ['lyria-3-pro-preview', 'lyria-3-pro'],
        'profile_fit': {'sentinel': 45, 'pathfinder': 50, 'responder': 65, 'auditor': 43},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['experimentation'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['', 'lyria', 'google'],
        'patterns': ['lyria-3-clip-preview', 'lyria-3-clip'],
        'profile_fit': {'sentinel': 42, 'pathfinder': 46, 'responder': 63, 'auditor': 40},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['experimentation'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'experimental'},
    {   'makers': ['openrouter'],
        'patterns': [
            'free-models-router',
            'free_models_router',
            'openrouter/free',
            'openrouter/openrouter/free',
        ],
        'profile_fit': {'sentinel': 78, 'pathfinder': 82, 'responder': 90, 'auditor': 74},
        'evidence_confidence': 'Provisional',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['budget routing', 'experimentation'],
        'benchmark_evidence': [   {   'name': 'Type',
                                      'value': 'Router',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'router',
        'fit_reason': 'OpenRouter free-model router; the Responder score reflects fast, low-cost '
                      'routing and tool-execution potential, not a foundation-model score.',
        'limitations': 'This is a model router, not a foundation model. ANVAYA fit reflects '
                       'routing quality; actual capability depends on the selected backend.',
        'gateway_type': 'router'},
    {   'makers': ['unknown / undisclosed', 'ox'],
        'patterns': ['ox-alpha'],
        'profile_fit': {'sentinel': 70, 'pathfinder': 78, 'responder': 68, 'auditor': 64},
        'evidence_confidence': 'Low-Medium',
        'evidence_level': 'Medium',
        'recommendation_confidence': 'Medium',
        'best_for': ['specific coding/agent tasks', 'alternate routing'],
        'benchmark_evidence': [   {   'name': 'LiveCodeBench pass@1',
                                      'value': '28.0%',
                                      'source': 'Independent'},
                                  {   'name': 'DeepSWE-style',
                                      'value': '58.4%',
                                      'source': 'Independent'},
                                  {   'name': 'Publisher 10-task benchmark',
                                      'value': '80%',
                                      'source': 'Provider-reported'},
                                  {   'name': 'OpenCode usage',
                                      'value': 'leading',
                                      'source': 'OpenCode usage'}],
        'quality_class': 'specialist'},
    {   'makers': ['liquidai', 'liquid'],
        'patterns': ['lfm2.5-2.6b', 'lfm-2.5-2.6b'],
        'profile_fit': {'sentinel': 38, 'pathfinder': 43, 'responder': 58, 'auditor': 36},
        'evidence_confidence': 'Low',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['extraction', 'routing', 'tiny classification'],
        'benchmark_evidence': [   {   'name': 'Public coverage',
                                      'value': 'insufficient',
                                      'source': 'Insufficient evidence'}],
        'quality_class': 'utility'},
    {   'makers': ['meta'],
        'patterns': ['llama-3.1-70b-instruct', 'llama-3-1-70b'],
        'profile_fit': {'sentinel': 68, 'pathfinder': 72, 'responder': 75, 'auditor': 66},
        'evidence_confidence': 'Low',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['cheap general analysis', 'classification', 'fallback'],
        'benchmark_evidence': [],
        'quality_class': 'utility'},
    {   'makers': ['meta'],
        'patterns': ['llama-3.1-8b-instruct', 'llama-3-1-8b'],
        'profile_fit': {'sentinel': 42, 'pathfinder': 48, 'responder': 55, 'auditor': 40},
        'evidence_confidence': 'Low',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['routing', 'extraction', 'very cheap first passes'],
        'benchmark_evidence': [],
        'quality_class': 'utility'},
    {   'makers': ['meta'],
        'patterns': ['llama-3.2-1b-instruct', 'llama-3-2-1b'],
        'profile_fit': {'sentinel': 35, 'pathfinder': 40, 'responder': 45, 'auditor': 34},
        'evidence_confidence': 'Low',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['routing', 'extraction', 'tiny classification'],
        'benchmark_evidence': [],
        'quality_class': 'utility'},
    {   'makers': ['nvidia'],
        'patterns': ['llama-3.3-nemotron-super', 'llama-3-3-nemotron-super'],
        'profile_fit': {'sentinel': 82, 'pathfinder': 80, 'responder': 81, 'auditor': 80},
        'evidence_confidence': 'Low-Medium',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Medium',
        'best_for': ['long-context reasoning', 'general analysis', 'NVIDIA-native deployment'],
        'benchmark_evidence': [],
        'quality_class': 'strong'},
    {   'makers': ['nvidia'],
        'patterns': ['llama-3.1-nemotron-nano-vl', 'llama-3-1-nemotron-nano-vl'],
        'profile_fit': {'sentinel': 55, 'pathfinder': 58, 'responder': 62, 'auditor': 54},
        'evidence_confidence': 'Low',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['visual security evidence', 'screenshots', 'multimodal analysis'],
        'benchmark_evidence': [],
        'quality_class': 'utility'},
    {   'makers': ['nvidia'],
        'patterns': ['nemotron-nano-12b-v2-vl'],
        'profile_fit': {'sentinel': 60, 'pathfinder': 62, 'responder': 65, 'auditor': 58},
        'evidence_confidence': 'Low',
        'evidence_level': 'Provisional',
        'recommendation_confidence': 'Low',
        'best_for': ['visual security evidence', 'screenshots', 'multimodal analysis'],
        'benchmark_evidence': [],
        'quality_class': 'utility'}]

_CATALOG: list[_CatalogEntry] = [_CatalogEntry(**d) for d in _CATALOG_DATA]



def _make_default(raw_name: str | None = None, model_id: str = "") -> dict[str, Any]:
    """Return a fully populated, provisional intelligence dict for unknown models."""
    return {
        "profile_fit": {
            "sentinel": 0.50,
            "pathfinder": 0.55,
            "responder": 0.50,
            "auditor": 0.45,
        },
        "evidence_confidence": "Provisional",
        "evidence_level": "Provisional",
        "recommendation_confidence": "Low",
        "anvaya_measured": False,
        "best_for": ["exploration", "fallback"],
        "benchmark_evidence": [
            {"name": "Public coverage", "value": "insufficient", "source": "Insufficient evidence"}
        ],
        "quality_class": "unknown",
        "display_name": display_name_for_model(model_id, raw_name=raw_name),
        "fit_reason": (
            "No matching catalog entry; ANVAYA fit is a provisional estimate based on "
            "model scale and provider metadata."
        ),
        "limitations": (
            "Public benchmark coverage is insufficient. ANVAYA fit scores are not validated "
            "for this model and should be treated as experimental."
        ),
        "provisional": True,
        "experimental": False,
        "gateway_type": "",
    }


def get_model_intelligence(
    maker: str,
    family: str,
    model_id: str,
    provider: str = "",
    raw_name: str | None = None,
) -> dict[str, Any]:
    """Return benchmark-grounded intelligence for a model config.

    The returned dict can be spread into a ModelConfig creation dict.  It
    includes profile_fit (0.0-1.0), evidence_confidence, evidence_level,
    recommendation_confidence, benchmark_evidence, best_for, quality_class,
    fit_reason, limitations, provisional, experimental, gateway_type and
    display_name.
    """
    best_entry: _CatalogEntry | None = None
    best_score = 0
    for entry in _CATALOG:
        score = entry.match_score(maker, family, model_id)
        if score > best_score:
            best_score = score
            best_entry = entry
    if best_entry:
        return {
            "profile_fit": best_entry.profile_fit,
            "evidence_confidence": best_entry.evidence_confidence,
            "evidence_level": best_entry.evidence_level,
            "recommendation_confidence": best_entry.recommendation_confidence,
            "anvaya_measured": False,
            "best_for": best_entry.best_for,
            "benchmark_evidence": best_entry.benchmark_evidence,
            "quality_class": best_entry.quality_class,
            "fit_reason": best_entry.fit_reason,
            "limitations": best_entry.limitations,
            "provisional": best_entry.provisional,
            "experimental": best_entry.experimental,
            "gateway_type": best_entry.gateway_type,
            "display_name": display_name_for_model(
                model_id, raw_name=raw_name, catalog_entry=best_entry
            ),
        }

    return _make_default(raw_name=raw_name, model_id=model_id)


def has_role_fit(intelligence: dict[str, Any]) -> bool:
    """Return True if the intelligence has any numeric role-fit scores."""
    profile_fit = intelligence.get("profile_fit") or {}
    return any(v is not None for v in profile_fit.values())
