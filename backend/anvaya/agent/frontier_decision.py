"""Frontier model-driven next-action decision for the agent loop.

The frontier decision engine calls the configured frontier model at each
iteration to determine the single best next action. It produces a strict
``NextActionContract`` that is validated against the tool registry before
execution.

Falls back to the existing deterministic ``DecisionEngine`` when the model
is unavailable or returns an invalid action.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from pydantic import BaseModel, Field

from anvaya.agent.blackboard import Blackboard
from anvaya.agent.mission import Mission
from anvaya.agent.registry import ToolRegistry, default_tool_registry
from anvaya.agent.schemas import ModelConfig, ToolResult
from anvaya.logging import get_logger
from anvaya.models.agent_context import ExecutionContext

logger = get_logger("anvaya.agent.frontier_decision")




class NextActionContract(BaseModel):
    """Strict structured output contract for the frontier model.

    Every iteration of the frontier loop produces exactly one of these.
    The ``action`` field determines the kind:

    * tool name  — execute that tool with ``inputs``
    * ``finish`` — mark execution complete
    * ``replan`` — update the plan without executing a tool
    * ``verify`` — run verification on the latest result
    * ``ask_user`` — pause and wait for user input
    """

    action: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    plan_update: list[dict[str, Any]] | None = None
    expected_observation: str = ""
    completion_condition: str = ""
    summary: str = ""




def build_model_context(
    *,
    mission: Mission,
    context: ExecutionContext,
    blackboard: Blackboard,
    available_tools: list[dict[str, Any]],
    latest_observation: dict[str, Any] | None = None,
    latest_tool_result: dict[str, Any] | None = None,
    user_updates: list[dict[str, Any]] | None = None,
    artifact_state: dict[str, str] | None = None,
    recent_failures: list[str] | None = None,
) -> str:
    """Build a bounded, data-grounded context string for the frontier model.

    This is NOT a chain-of-thought dump. It is a compact, structured
    representation of the current state that the model uses to decide the
    single best next action.
    """
    parts: list[str] = []

    parts.append(f"MISSION\nObjective: {mission.objective}")
    if mission.constraints:
        parts.append(f"Constraints: {', '.join(mission.constraints)}")
    parts.append(
        f"Budget: iteration {mission.iteration}/{mission.max_iterations}, "
        f"tool_calls {mission.tool_calls}/{mission.max_tool_calls}, "
        f"model_calls {mission.model_calls}/{mission.max_model_calls}"
    )

    plan = context.plan or []
    if plan:
        plan_lines = []
        for i, step in enumerate(plan):
            status = step.get("status", "pending")
            icon = {"completed": "✓", "failed": "✗", "running": "→", "skipped": "⊘"}.get(
                status, "○"
            )
            plan_lines.append(f"  {icon} {step.get('label', step.get('tool', '?'))}")
        parts.append("CURRENT PLAN\n" + "\n".join(plan_lines))

    if blackboard.completed_actions:
        parts.append(
            "COMPLETED ACTIONS\n" + "\n".join(f"  - {a}" for a in blackboard.completed_actions[-10:])
        )

    if latest_observation:
        obs_summary = latest_observation.get("summary", "")
        obs_facts = latest_observation.get("facts", {})
        facts_str = ", ".join(f"{k}={v}" for k, v in obs_facts.items() if v is not None)
        parts.append(f"LATEST OBSERVATION\n  {obs_summary}\n  {facts_str}")

    hypotheses = blackboard.hypotheses[:3]
    if hypotheses:
        hyp_lines = [
            f"  - [{h.status}] {h.statement} (confidence={h.confidence:.2f})" for h in hypotheses
        ]
        parts.append("ACTIVE HYPOTHESES\n" + "\n".join(hyp_lines))

    if artifact_state:
        art_lines = [f"  {k}: {v}" for k, v in artifact_state.items()]
        parts.append("ARTIFACT STATE\n" + "\n".join(art_lines))

    if recent_failures:
        parts.append(
            "RECENT FAILURES\n" + "\n".join(f"  - {f}" for f in recent_failures[-5:])
        )

    if user_updates:
        update_lines = [f"  [{u.get('role', 'user')}] {u.get('content', '')}" for u in user_updates]
        parts.append("USER UPDATES\n" + "\n".join(update_lines[-3:]))

    if available_tools:
        tool_lines = [
            f"  - {t['name']}: {t.get('description', '')[:80]}" for t in available_tools[:25]
        ]
        parts.append("AVAILABLE TOOLS\n" + "\n".join(tool_lines))

    return "\n\n".join(parts)




class FrontierDecisionEngine:
    """Model-driven next-action selector for the frontier agent loop.

    Calls the frontier model with a compact context and expects a
    ``NextActionContract`` in return. Validates the contract against the
    tool registry and falls back to re-prompting (once) on invalid output.
    """

    def __init__(
        self,
        model_provider: Any,
        model_config: ModelConfig,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.provider = model_provider
        self.model_config = model_config
        self.registry = registry or default_tool_registry()
        self._retry_counts: dict[str, int] = {}

    def decide(
        self,
        *,
        mission: Mission,
        context: ExecutionContext,
        blackboard: Blackboard,
        latest_observation: dict[str, Any] | None = None,
        latest_tool_result: dict[str, Any] | None = None,
        user_updates: list[dict[str, Any]] | None = None,
        artifact_state: dict[str, str] | None = None,
        recent_failures: list[str] | None = None,
    ) -> NextActionContract:
        """Call the frontier model to determine the next action.

        Returns a validated ``NextActionContract``. Falls back to a
        conservative ``finish`` action if the model fails.
        """
        available_tools = self._tool_summaries()
        model_context = build_model_context(
            mission=mission,
            context=context,
            blackboard=blackboard,
            available_tools=available_tools,
            latest_observation=latest_observation,
            latest_tool_result=latest_tool_result,
            user_updates=user_updates,
            artifact_state=artifact_state,
            recent_failures=recent_failures,
        )

        messages = self._build_messages(model_context)

        try:
            contract = self._call_model(messages)
        except Exception as exc:
            logger.error("frontier.decision_failed", error=str(exc))
            return NextActionContract(
                action="finish",
                reason=f"Model decision failed: {exc}",
                summary="Execution stopped due to model error.",
            )

        if contract.action not in ("finish", "replan", "verify", "ask_user"):
            validated = self._validate_tool_action(contract, messages)
            if validated is not None:
                return validated

        return contract

    def track_retry(self, action: str, inputs_key: str) -> int:
        """Track and return the retry count for an action+input combination."""
        key = f"{action}:{inputs_key}"
        self._retry_counts[key] = self._retry_counts.get(key, 0) + 1
        return self._retry_counts[key]

    def get_retry_count(self, action: str, inputs_key: str) -> int:
        """Return the current retry count without incrementing."""
        key = f"{action}:{inputs_key}"
        return self._retry_counts.get(key, 0)


    def _build_messages(self, model_context: str) -> list[dict[str, str]]:
        system = (
            "You are ANVAYA, an autonomous cybersecurity SOC agent. "
            "You decide the SINGLE best next action at each step of an investigation or task.\n\n"
            "Respond ONLY with a JSON object matching this schema:\n"
            "{\n"
            '  "action": "<tool_name | finish | replan | verify | ask_user>",\n'
            '  "inputs": {},\n'
            '  "reason": "Short user-safe explanation (1-2 sentences)",\n'
            '  "plan_update": null,\n'
            '  "expected_observation": "What this action should establish",\n'
            '  "completion_condition": "What must be true before considering this step complete",\n'
            '  "summary": "Only for finish actions"\n'
            "}\n\n"
            "Rules:\n"
            "- Choose exactly ONE action per call.\n"
            "- The reason must be concise and user-safe. Never expose chain-of-thought.\n"
            "- Only use tools from the AVAILABLE TOOLS list.\n"
            "- Respect the CONSTRAINTS and BUDGET.\n"
            "- If the objective is complete and verified, use 'finish'.\n"
            "- If previous actions failed and you need a different approach, use 'replan'.\n"
            "- Do not invent data. Base decisions on LATEST OBSERVATION and ARTIFACT STATE.\n"
            "- Do not expand scope beyond what CONSTRAINTS allow.\n"
            "- Do not generate more than 2 sentences of reasoning."
        )

        user = (
            "Current execution state:\n\n"
            f"{model_context}\n\n"
            "What is the single best next action right now? "
            "Respond with the JSON contract only."
        )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _call_model(self, messages: list[dict[str, str]]) -> NextActionContract:
        """Call the model and parse the response into a NextActionContract."""
        response = self.provider.chat_completion(
            messages,
            temperature=self.model_config.default_temperature,
            response_format={"type": "json_object"},
        )

        if isinstance(response, Iterator):
            text_parts: list[str] = []
            for chunk in response:
                chunk_dict = chunk.to_dict() if hasattr(chunk, "to_dict") else chunk
                text_parts.append(chunk_dict.get("text", ""))
            text = "".join(text_parts)
        else:
            response_dict = response.to_dict()
            if response_dict.get("error"):
                raise RuntimeError(f"Model error: {response_dict['error']}")
            text = response_dict.get("text", "")

        return self._parse_contract(text)

    def _parse_contract(self, text: str) -> NextActionContract:
        """Parse model output text into a NextActionContract."""
        if not text:
            raise ValueError("Empty model response")

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError(f"Could not parse JSON from model response: {text[:200]}")
            data = json.loads(text[start : end + 1])

        if not isinstance(data, dict):
            raise ValueError(f"Expected dict, got {type(data).__name__}")

        return NextActionContract(**data)

    def _validate_tool_action(
        self,
        contract: NextActionContract,
        original_messages: list[dict[str, str]],
    ) -> NextActionContract | None:
        """Validate a tool action against the registry.

        Returns the original contract if valid, a re-prompted contract
        if the first attempt was invalid, or None if validation passes.
        """
        tool_name = contract.action
        tool = self.registry.get(tool_name)

        if not tool:
            logger.warning("frontier.unknown_tool", tool=tool_name)
            return self._reprompt_for_invalid_tool(
                original_messages, tool_name, "not found in registry"
            )

        valid, errors = self.registry.validate_inputs(tool_name, contract.inputs)
        if not valid:
            logger.warning(
                "frontier.invalid_inputs",
                tool=tool_name,
                errors=errors,
            )
            return self._reprompt_for_invalid_tool(
                original_messages, tool_name, f"invalid inputs: {'; '.join(errors)}"
            )

        return None

    def _reprompt_for_invalid_tool(
        self,
        original_messages: list[dict[str, str]],
        tool_name: str,
        reason: str,
    ) -> NextActionContract:
        """Re-prompt the model once after an invalid tool selection."""
        correction_messages = list(original_messages)
        correction_messages.append(
            {
                "role": "assistant",
                "content": json.dumps({"action": tool_name, "reason": "..."}),
            }
        )
        correction_messages.append(
            {
                "role": "user",
                "content": (
                    f"The action '{tool_name}' is invalid: {reason}. "
                    "Choose a different valid tool from the AVAILABLE TOOLS list, "
                    "or use 'finish' / 'replan'. Respond with the corrected JSON contract."
                ),
            }
        )

        try:
            return self._call_model(correction_messages)
        except Exception as exc:
            logger.error("frontier.reprompt_failed", error=str(exc))
            return NextActionContract(
                action="replan",
                reason=f"Could not select a valid tool after correction: {exc}",
            )


    def _tool_summaries(self) -> list[dict[str, Any]]:
        """Build compact tool descriptions for the model context."""
        summaries: list[dict[str, Any]] = []
        for tool in self.registry.list_tools():
            params = [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                }
                for p in tool.parameters
            ]
            summaries.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "category": tool.category,
                    "params": params,
                }
            )
        return summaries




def stream_frontier_reasoning(
    provider: Any,
    model_config: ModelConfig,
    context_str: str,
) -> Iterator[str]:
    """Stream safe reasoning deltas from the frontier model.

    Used by the frontier loop to emit ``agent.reasoning_delta`` events.
    The model is asked to produce a short operational status, not chain-of-thought.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You are ANVAYA. Produce a brief (1-2 sentence) operational status "
                "explaining what you are about to do and why, based on the current state. "
                "Do NOT expose internal reasoning, deliberation, or chain-of-thought. "
                "Do NOT use more than 2 sentences."
            ),
        },
        {
            "role": "user",
            "content": f"Current state:\n{context_str}\n\nBrief operational status:",
        },
    ]

    try:
        response = provider.chat_completion(
            messages,
            temperature=model_config.default_temperature,
            stream=True,
        )
        if isinstance(response, Iterator):
            for chunk in response:
                chunk_dict = chunk.to_dict() if hasattr(chunk, "to_dict") else chunk
                delta = chunk_dict.get("text", "")
                if delta:
                    yield delta
        else:
            resp_dict = response.to_dict()
            text = resp_dict.get("text", "")
            if text:
                yield text
    except Exception as exc:
        logger.warning("frontier.reasoning_stream_failed", error=str(exc))
        yield "Analyzing current state..."
