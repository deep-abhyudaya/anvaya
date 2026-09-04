"""Recovery planning for failed or unavailable tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecoveryDecision(BaseModel):
    """What to do after a tool failure."""

    action: str = "replan"
    retry: bool = False
    alternate_tool: list[str] = Field(default_factory=list)
    reason: str = ""
    continue_after: bool = True


class FailureClassifier:
    """Classify a tool failure and choose a recovery strategy."""

    RETRYABLE_CODES = {
        "timeout",
        "connection_error",
        "provider_unavailable",
        "rate_limited",
    }

    ALTERNATE_TOOL_MAP: dict[str, list[str]] = {
        "trace_attack_path": ["reconstruct_timeline", "correlate_entities", "get_telemetry"],
        "reconstruct_timeline": ["get_telemetry", "correlate_entities", "investigate_entity"],
        "correlate_entities": ["investigate_entity", "get_telemetry"],
        "investigate_entity": ["compare_baseline", "test_hypothesis"],
        "run_blastscope": ["run_reachability", "get_telemetry"],
        "run_reachability": ["get_telemetry", "trace_attack_path"],
        "run_sentinel_trace": ["get_telemetry", "inspect_detection"],
        "propose_rule": ["get_telemetry", "run_sentinel_trace"],
        "validate_rule": ["run_replay", "get_telemetry"],
        "generate_artifacts": ["observe_project"],
        "observe_project": ["get_metrics"],
    }

    @classmethod
    def classify(
        cls,
        tool_name: str,
        error_code: str,
        error_message: str,
        retry_count: int = 0,
        max_retries: int = 1,
    ) -> RecoveryDecision:
        """Return a recovery decision for a tool failure."""
        decision = RecoveryDecision(reason=f"{tool_name} failed: {error_message}")

        if error_code in ("tool_not_found", "validation_error", "not_found"):
            decision.action = "replan"
            decision.continue_after = True
            return decision

        if error_code in cls.RETRYABLE_CODES and retry_count < max_retries:
            decision.action = "retry"
            decision.retry = True
            decision.reason = (
                f"{tool_name} failed transiently; retrying ({retry_count + 1}/{max_retries + 1})."
            )
            return decision

        alternates = cls.ALTERNATE_TOOL_MAP.get(tool_name, [])
        if alternates:
            decision.action = "alternate"
            decision.alternate_tool = list(alternates)
            decision.reason = f"{tool_name} failed; switching to one of {', '.join(alternates)}."
            return decision

        decision.action = "replan"
        decision.reason = f"{tool_name} failed with no direct fallback; replanning."
        return decision
