"""Agent planning: deterministic policy or model-driven plan generation.

The model planner asks a configured model provider to produce a tool plan and
falls back to the deterministic policy when the model is unavailable, not
capable, or returns an invalid plan.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from anvaya.agent.profiles import AgentProfile, default_models
from anvaya.agent.registry import ToolRegistry, default_tool_registry
from anvaya.agent.schemas import ModelConfig
from anvaya.llm.providers import (
    LocalProvider,
    ModelProvider,
    get_model_provider_for_config,
    is_model_compatible,
    select_model_provider_for_profile,
)
from anvaya.logging import get_logger

logger = get_logger("anvaya.agent.planner")


class DeterministicPlanner:
    """Returns the existing ANVAYA self-correction plan."""

    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or default_tool_registry()

    def build_plan(
        self,
        session: Any,
        incident_id: str,
        context: dict[str, Any] | None = None,
        profile: AgentProfile | None = None,
    ) -> list[dict[str, Any]]:
        from anvaya.agent.orchestrator import _build_plan

        return _build_plan(session, incident_id, profile)


class ModelPlanner:
    """Ask a model provider to generate a tool plan."""

    def __init__(
        self,
        provider: ModelProvider,
        model_config: ModelConfig,
        profile: AgentProfile,
        registry: ToolRegistry | None = None,
        max_steps: int = 20,
    ):
        self.provider = provider
        self.model_config = model_config
        self.profile = profile
        self.registry = registry or default_tool_registry()
        self.max_steps = max_steps

    def build_plan(
        self,
        session: Any,
        incident_id: str,
        context: dict[str, Any] | None = None,
        profile: AgentProfile | None = None,
    ) -> list[dict[str, Any]] | None:
        """Return a model-generated plan or None to trigger fallback."""
        context = context or {}
        messages = self._build_messages(incident_id, context)

        response = self.provider.chat_completion(
            messages,
            temperature=self.model_config.default_temperature,
            response_format={"type": "json_object"},
        )

        if isinstance(response, Iterator):
            logger.warning(
                "model.streaming_not_supported_in_planner",
                provider=self.provider.name,
            )
            return None

        response_dict = response.to_dict()

        if response_dict.get("error"):
            logger.warning(
                "model.plan_failed",
                provider=self.provider.name,
                error=response_dict["error"],
            )
            return None

        text = response_dict.get("text", "")
        plan = self._parse_plan(text)
        if plan is None:
            logger.warning(
                "model.plan_unparseable",
                provider=self.provider.name,
                text=text[:200],
            )
            return None

        validated = []
        for step in plan:
            tool_name = step.get("tool")
            if not tool_name or not self.registry.get(tool_name):
                logger.warning("model.plan_unknown_tool", tool=tool_name)
                continue
            inputs = step.get("inputs", {})
            tool_def = self.registry.get(tool_name)
            if tool_def:
                for p in tool_def.parameters:
                    if p.name == "incident_id" and p.required and not inputs.get("incident_id"):
                        inputs["incident_id"] = incident_id
            valid, errors = self.registry.validate_inputs(tool_name, inputs)
            if not valid:
                logger.warning(
                    "model.plan_invalid_inputs",
                    tool=tool_name,
                    errors=errors,
                )
                continue
            validated.append(
                {
                    "tool": tool_name,
                    "inputs": inputs,
                    "label": step.get("label") or f"Running {tool_name}",
                    "progress": step.get("progress") or "Processing...",
                    "completed": step.get("completed") or f"{tool_name} completed",
                    "optional": bool(step.get("optional", False)),
                    "stop_on_failure": bool(step.get("stop_on_failure", False)),
                }
            )

        if not validated:
            return None
        return validated[: self.max_steps]

    def _build_messages(self, incident_id: str, context: dict[str, Any]) -> list[dict[str, str]]:
        tool_descriptions = []
        for tool in self.registry.list_tools():
            params = ", ".join(
                f"{p.name} ({p.type}{' required' if p.required else ''})" for p in tool.parameters
            )
            tool_descriptions.append(
                f"- {tool.name}: {tool.description} [{tool.category}] params: {params}"
            )

        available_tools = "\n".join(tool_descriptions)
        preferred = ", ".join(self.profile.preferred_tools)

        system = (
            f"You are the ANVAYA agent profile '{self.profile.display_name}'.\n"
            f"{self.profile.system_instruction}\n"
            "Your job is to select the next tools to run.\n"
            "Respond ONLY with a JSON object containing a top-level 'plan' array.\n"
            "Each plan item must have:\n"
            "  tool: the exact tool name\n"
            "  inputs: an object of input parameters\n"
            "  label: a short label for the UI (max 6 words)\n"
            "  progress: a short running message\n"
            "  completed: a short completion message\n"
            "  optional: boolean (optional)\n"
            "Prefer these tools when relevant: "
            f"{preferred}.\n"
            "Do not include hidden reasoning, explanations, or chain-of-thought."
        )

        user = (
            f"Objective: {context.get('objective', 'Investigate the incident')}\n"
            f"Incident: {incident_id}\n"
            f"Profile: {self.profile.display_name}\n"
            f"Title: {context.get('title', '')}\n"
            f"Severity: {context.get('severity', '')}\n"
            f"Status: {context.get('status', '')}\n"
            f"Self-correction status: {context.get('self_correction_status', '')}\n"
            f"Telemetry events: {context.get('telemetry_count', 0)}\n"
            f"Detection caught: {context.get('detection_caught', False)}\n"
            f"Available tools:\n{available_tools}\n\n"
            "Return the JSON plan."
        )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _parse_plan(self, text: str) -> list[dict[str, Any]] | None:
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None

        if not isinstance(data, dict):
            return None

        plan = data.get("plan")
        if plan is None:
            for v in data.values():
                if isinstance(v, list):
                    plan = v
                    break
        if not isinstance(plan, list):
            return None
        return plan


def resolve_planner(
    profile: AgentProfile,
    model_id: str = "",
) -> tuple[ModelPlanner | DeterministicPlanner, ModelConfig | None]:
    """Pick the right planner for a profile.

    If a capable, configured external model is selected, return a ModelPlanner.
    Otherwise return the deterministic planner.
    """
    models = default_models()

    selected_model: ModelConfig | None = None
    selected_provider: ModelProvider | None = None
    if model_id:
        from anvaya.agent.profiles import get_model

        selected_model = get_model(model_id)
        if selected_model:
            selected_provider = get_model_provider_for_config(selected_model)
            if selected_provider and selected_provider.configured():
                compatible, reason = is_model_compatible(
                    selected_model, _required_capabilities(profile)
                )
                if compatible:
                    return (
                        ModelPlanner(selected_provider, selected_model, profile),
                        selected_model,
                    )

    selected_model, selected_provider, _ = select_model_provider_for_profile(profile.id, models)

    if selected_model and selected_provider and not isinstance(selected_provider, LocalProvider):
        return ModelPlanner(selected_provider, selected_model, profile), selected_model

    return DeterministicPlanner(), selected_model


def _required_capabilities(profile: AgentProfile) -> list[str]:
    required = ["chat", "tools"]
    if profile.id == "sentinel":
        required.extend(["streaming", "structured-outputs"])
    if profile.id in ("pathfinder", "responder"):
        required.append("structured-outputs")
    return required
