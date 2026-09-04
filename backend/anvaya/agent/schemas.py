"""Typed schemas for the agentic tool system."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """A single tool input parameter."""

    name: str
    description: str = ""
    type: str = "string"
    required: bool = True
    default: Any = None
    enum: Optional[list[Any]] = None


class ToolDefinition(BaseModel):
    """Provider-neutral tool definition."""

    name: str
    description: str
    category: str = "investigation"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    parameters: list[ToolParameter] = Field(default_factory=list)
    risk_level: str = "low"
    requires_confirmation: bool = False
    provider: str = "anvaya"
    fallback_provider: str = "anvaya"
    timeout_ms: int = 30000
    idempotent: bool = False
    supports_streaming: bool = False


class ArtifactRef(BaseModel):
    """Reference to a user-visible artifact."""

    ref_type: str
    ref_id: str
    label: str = ""
    link: str = ""


class ToolResult(BaseModel):
    """Result of a tool execution."""

    tool_call_id: str = Field(default_factory=lambda: f"call_{uuid4().hex[:8]}")
    tool_name: str
    status: str = "success"
    provider: str = "anvaya"
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""
    duration_ms: float = 0.0
    input_summary: str = ""
    output_summary: str = ""
    output: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: list[ArtifactRef] = Field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    fallback_used: bool = False
    fallback_reason: str = ""


class ExecutionEventPayload(BaseModel):
    """Safe payload for an execution event."""

    id: int = 0
    execution_id: str
    sequence: int
    type: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tool_call_id: str = ""
    tool_name: str = ""
    provider: str = ""
    status: str = ""
    label: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    artifact_ref: str = ""
    artifact_type: str = ""
    error_code: str = ""
    error_message: str = ""
    fallback_reason: str = ""


class ExecutionSummary(BaseModel):
    """Summary of an agent execution."""

    execution_id: str
    objective: str
    incident_id: str = ""
    status: str
    provider: str
    fallback_used: bool
    started_at: str
    completed_at: Optional[str]
    duration_ms: float
    result_summary: str
    error_message: str


class AgentProfile(BaseModel):
    """Agent personality/profile configuration."""

    id: str
    name: str
    display_name: str
    purpose: str
    description: str
    system_instruction: str
    model_provider: str
    model_name: str
    temperature: float = 0.2
    verbosity: str = "concise"
    personality: str = "analytical"
    expertise: list[str]
    autonomy_level: str = "high"
    preferred_tools: list[str]
    fallback_tools: list[str]
    confirmation_policy: str = "read-only"
    response_style: str = "operational"
    icon: str = "bot"
    accent: str = "cyan"
    status: str = "active"


class ModelPricing(BaseModel):
    """Per-token pricing metadata (per million tokens where known)."""

    input_per_million: float | None = None
    cached_input_per_million: float | None = None
    output_per_million: float | None = None


class ModelBenchmarkEvidence(BaseModel):
    """A single public benchmark or technical-report evidence point.

    ``source`` is the evidence tier/label required by the catalog policy:
    Independent, Provider-reported, Harness-specific, ANVAYA measured, or
    Insufficient evidence.
    """

    name: str
    value: str
    source: str
    url: str | None = None


class ModelUsage(BaseModel):
    """Live usage signal from a provider (usage_rank, usage_tokens, trend)."""

    usage_rank: int | None = None
    usage_tokens: int | None = None
    trend: str = ""


class ModelAnvayaData(BaseModel):
    """Measured ANVAYA performance, if any."""

    mission_success: float | None = None
    tool_success: float | None = None
    verification: float | None = None
    ttft_ms: float | None = None
    tokens_per_sec: float | None = None
    cost_per_mission: float | None = None
    recovery: float | None = None
    false_positive_rate: float | None = None
    usage: ModelUsage | None = None


class ModelConfig(BaseModel):
    """Model metadata for the agent."""

    id: str
    provider: str
    provider_model_id: str = ""
    model: str
    maker: str = ""
    family: str = ""
    display_name: str
    description: str
    purpose: str
    capabilities: list[str]
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    supports_reasoning: bool
    supports_multimodal: bool = False
    latency_class: str = "unknown"
    cost_class: str = "standard"
    availability: str = "unknown"
    configured: bool = False
    default_temperature: float = 0.2
    recommended_for: list[str]
    recommended_profiles: list[str] = []
    logo_domain: str = ""
    protocol: str = ""
    base_url: str = ""
    pricing: ModelPricing | None = None
    pricing_mode: str = "per_token"
    cost_per_request: float | None = None
    access_class: str = "standard"
    privacy_class: str = "standard"
    gateway_type: str = ""
    aliases: list[str] = Field(default_factory=list)
    max_tokens: int | None = None
    profile_fit: dict[str, float | None] = Field(
        default_factory=dict,
        description="Per-profile ANVAYA role-fit score (0.0-1.0) or None for N/A",
    )
    evidence_confidence: str = "Unknown"
    anvaya_measured: bool = False
    recommendation_confidence: str = "Low"
    benchmark_evidence: list[ModelBenchmarkEvidence] = Field(default_factory=list)
    anvaya_data: ModelAnvayaData | None = None
    best_for: list[str] = Field(default_factory=list)
    quality_class: str | None = None
    evidence_level: str = "Provisional"
    fit_reason: str = ""
    limitations: str = ""
    provisional: bool = False
    experimental: bool = False

    def model_post_init(self, __context: Any) -> None:
        if not self.recommended_profiles and self.recommended_for:
            self.recommended_profiles = self.recommended_for
        self.configured = self.availability in ("available", "configured")
