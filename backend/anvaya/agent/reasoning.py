"""Reasoning summary generator for the live agent loop.

Summaries are concise, user-safe operational statements derived from
execution state. They never expose hidden chain-of-thought, system prompts,
raw model deliberation, or large tool outputs.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from anvaya.agent.schemas import ToolResult
from anvaya.logging import get_logger
from anvaya.models.agent_context import ExecutionContext

logger = get_logger("anvaya.agent.reasoning")


class ReasoningGenerator:
    """Generate user-safe reasoning summaries from the current execution context.

    The default path is fully deterministic and reads actual tool outputs, plan
    state, and observations. If a configured external model is supplied and
    ``stream=True``, it may optionally stream deltas, but the final summary is
    always grounded in execution state and falls back to deterministic output
    when the model is unavailable or returns nothing usable.
    """

    def __init__(
        self,
        model_provider: Any | None = None,
        model_config: Any | None = None,
        stream: bool = False,
    ) -> None:
        self.model_provider = model_provider
        self.model_config = model_config
        self.use_stream = stream
        self._uses_model = False

    @property
    def uses_model(self) -> bool:
        """True if the last generation came from a model stream."""
        return self._uses_model

    def generate(
        self,
        context: ExecutionContext,
        step: dict[str, Any],
        result: ToolResult | None = None,
    ) -> str:
        """Return a concise, user-safe reasoning summary for ``step``.

        ``result`` is the *previous* tool result, used to explain how the
        current step was chosen.
        """
        self._uses_model = False
        if self._should_force_deterministic(step):
            return self._generate_deterministic(context, step, result)
        if self._should_use_model():
            try:
                model_summary = self._generate_from_model(context, step, result)
                if model_summary:
                    self._uses_model = True
                    return model_summary
            except Exception as exc:
                logger.warning("reasoning.model_failed", error=str(exc))
        return self._generate_deterministic(context, step, result)

    def stream(
        self,
        context: ExecutionContext,
        step: dict[str, Any],
        result: ToolResult | None = None,
    ) -> Iterator[str]:
        """Yield reasoning deltas.

        If a configured external model supports streaming, emits model deltas.
        Otherwise yields a single deterministic delta.
        """
        self._uses_model = False
        if self._should_force_deterministic(step):
            yield self._generate_deterministic(context, step, result)
            return
        if self._should_use_model():
            try:
                yield from self._stream_from_model(context, step, result)
                return
            except Exception as exc:
                logger.warning("reasoning.model_stream_failed", error=str(exc))
        yield self._generate_deterministic(context, step, result)

    def _should_force_deterministic(self, step: dict[str, Any]) -> bool:
        """Per-artifact plan steps carry target/route in step metadata.

        Force the deterministic path so the user-safe route is always present
        in the reasoning stream and final summary.
        """
        return (
            step.get("tool") == "manage_artifacts"
            and step.get("target_artifact_type") is not None
        )


    def _generate_deterministic(
        self,
        context: ExecutionContext,
        step: dict[str, Any],
        result: ToolResult | None = None,
    ) -> str:
        tool_name = step.get("tool", "")
        label = step.get("label", tool_name.replace("_", " ").title())
        target = self._target_name(context)

        if tool_name == "manage_artifacts":
            atype = step.get("target_artifact_type")
            if atype and len(context.plan) > 1:
                action = step.get("inputs", {}).get("action", "generate")
                verb = {
                    "generate": "generating",
                    "regenerate": "regenerating",
                    "delete": "deleting",
                }.get(action, f"{action}ing")
                route = step.get("route") or atype
                return f"Next: {verb} {atype.title()} — navigating to /{route}."

        if result is not None:
            previous_label = _tool_label(result.tool_name)
            if result.status == "success":
                previous = _safe_result_summary(result)
                if result.tool_name == "get_telemetry" and result.output:
                    total = result.output.get("total_events")
                    attack = result.output.get("attack_events")
                    if total is not None and attack is not None:
                        previous = f"{total} events ({attack} attack)"
                return (
                    f"The previous step ({previous_label}) returned {previous}. "
                    f"I'll now {label.lower()} to continue."
                )
            return (
                f"The previous step ({previous_label}) did not succeed. "
                f"I'll continue with {label}."
            )

        if tool_name == "get_incident":
            return f"I'll start by loading the incident context for {target}."
        if tool_name == "manage_artifacts":
            action = step.get("inputs", {}).get("action", "generate")
            return f"I found a project, so I'll {action} artifacts from the dataset."
        if tool_name == "confirm_ground_truth":
            return f"The detection missed for {target}, so I'll confirm the ground truth first."
        return f"I'll start by {label.lower()} for {target}."

    def _target_name(self, context: ExecutionContext) -> str:
        if context.incident_id:
            return context.incident_id
        if context.project_id:
            return context.project_id
        objective = context.objective
        if objective:
            return _truncate(objective, 40)
        return "this task"


    def _should_use_model(self) -> bool:
        return bool(
            self.model_provider
            and self.use_stream
            and getattr(self.model_provider, "configured", lambda: False)()
            and getattr(self.model_provider, "supports_capability", lambda c: False)("streaming")
        )

    def _build_model_messages(
        self,
        context: ExecutionContext,
        step: dict[str, Any],
        result: ToolResult | None = None,
    ) -> list[dict[str, str]]:
        target = self._target_name(context)
        tool_name = step.get("tool", "")
        label = step.get("label", tool_name)
        plan_names = [s.get("tool", "") for s in context.plan]

        previous = ""
        if result is not None:
            previous = _safe_result_summary(result)

        system = (
            "You are an operational assistant for a cyber SOC agent. "
            "Produce a single concise, user-safe sentence that explains the next "
            "action the agent will take. Do not include hidden reasoning, "
            "chain-of-thought, system details, or raw tool output. "
            "Use only the facts provided."
        )
        user = (
            f"Objective: {context.objective}\n"
            f"Target: {target}\n"
            f"Plan tools: {', '.join(plan_names)}\n"
            f"Previous step result: {previous}\n"
            f"Next step tool: {tool_name}\n"
            f"Next step label: {label}\n"
            "Explain the next step in one sentence."
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def _generate_from_model(
        self,
        context: ExecutionContext,
        step: dict[str, Any],
        result: ToolResult | None = None,
    ) -> str:
        if not self.model_provider:
            return ""
        messages = self._build_model_messages(context, step, result)
        temperature = getattr(self.model_config, "temperature", 0.2) if self.model_config else 0.2
        response = self.model_provider.chat_completion(
            messages,
            temperature=temperature,
            stream=False,
        )
        if isinstance(response, Iterator):
            return ""
        text = getattr(response, "text", "") or ""
        return _sanitize_model_text(text)

    def _stream_from_model(
        self,
        context: ExecutionContext,
        step: dict[str, Any],
        result: ToolResult | None = None,
    ) -> Iterator[str]:
        if not self.model_provider:
            return
        messages = self._build_model_messages(context, step, result)
        temperature = getattr(self.model_config, "temperature", 0.2) if self.model_config else 0.2
        chunks = self.model_provider.chat_completion(
            messages,
            temperature=temperature,
            stream=True,
        )
        if not isinstance(chunks, Iterator):
            text = getattr(chunks, "text", "") or ""
            if text:
                yield _sanitize_model_text(text)
            return

        full_text = ""
        for chunk in chunks:
            delta = getattr(chunk, "text", "") or ""
            if delta:
                full_text += delta
                yield _sanitize_model_text(delta)
            error = getattr(chunk, "error", "")
            if error:
                break

        final = _sanitize_model_text(full_text)
        if final:
            self._uses_model = True



_LABELS: dict[str, str] = {
    "get_incident": "incident context",
    "get_telemetry": "telemetry inspection",
    "inspect_detection": "detection inspection",
    "confirm_ground_truth": "ground truth confirmation",
    "run_sentinel_trace": "Sentinel backtrack",
    "propose_rule": "rule proposal",
    "validate_rule": "rule validation",
    "run_replay": "attack replay",
    "run_blastscope": "BlastScope analysis",
    "build_or_update_ecosystem": "ecosystem update",
    "run_orbit_analysis": "orbit analysis",
    "run_reachability": "reachability analysis",
    "run_segment_analysis": "segment analysis",
    "run_what_if": "What-If analysis",
    "append_audit_record": "audit record",
    "verify_audit_chain": "audit verification",
    "seal_incident": "incident seal",
    "manage_artifacts": "artifact management",
    "generate_artifacts": "artifact generation",
    "threat_intelligence_lookup": "threat intelligence",
    "trigger_automation": "automation",
    "spawn_subagent": "subagent",
}


def _tool_label(tool_name: str) -> str:
    return _LABELS.get(tool_name, tool_name.replace("_", " ").title())


def _safe_result_summary(result: ToolResult) -> str:
    summary = result.output_summary or result.error_message or "completed"
    return _truncate(summary, 80)


def _truncate(text: str, length: int) -> str:
    text = text.strip()
    if len(text) > length:
        return text[: length - 1].rstrip() + "…"
    return text


def _sanitize_model_text(text: str) -> str:
    """Remove anything that looks like hidden chain-of-thought."""
    text = text.strip()
    markers = ("<think>", "", "[thinking]", "[/thinking]")
    for m in markers:
        text = text.replace(m, "")
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith(("(", "["))]
    text = " ".join(lines).strip()
    return _truncate(text, 160)
