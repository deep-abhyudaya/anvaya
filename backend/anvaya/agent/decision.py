"""Adaptive next-action decision for the agent loop.

The decision engine selects the next tool, replan, ask_user, or complete action
based on the current mission, blackboard, world observation, and memory. It is
deterministic by default and can delegate to a model when one is configured.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from anvaya.agent.blackboard import Blackboard, Hypothesis
from anvaya.agent.mission import Mission
from anvaya.agent.recovery import FailureClassifier
from anvaya.agent.world import WorldObserver


class NextDecision(BaseModel):
    """A single decision from the planner."""

    kind: str = "tool"
    tool: str = ""
    inputs: dict[str, Any] = Field(default_factory=dict)
    purpose_summary: str = ""
    expected_result: str = ""
    continue_after_result: bool = True
    confidence: float = 0.0
    expected_information_gain: float = 0.0
    reasoning: str = ""
    recovery_action: str = ""

    plan_update: list[dict[str, Any]] | None = None
    expected_observation: str = ""
    completion_condition: str = ""
    summary: str = ""


def _extract_target_from_objective(objective: str) -> str:
    """Try to find a host, incident, or project identifier in the objective."""
    patterns = [
        r"\b(HOST-[A-Z0-9-]+)\b",
        r"\b(INC-[A-Z0-9-]+)\b",
        r"\b(PRJ-[A-Z0-9-]+)\b",
        r"\b(SERVER-[A-Z0-9-]+)\b",
        r"\b(USER-[A-Z0-9-]+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, objective, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return ""


def _has_action(action: str, actions: list[str]) -> bool:
    """Check whether an exact action key is recorded (possibly with a reason suffix)."""
    return any(a == action or a.startswith(f"{action}:") for a in actions)


def _entity_from_prior_memory(memory: dict[str, Any], objective: str) -> str:
    """Extract a candidate entity from prior completed executions in memory.

    Re-use a prior finding when the current objective explicitly names the same
    entity, or when the objective only names the incident/project (generic
    "investigate incident") and a prior completed execution found a concrete
    entity for that same scope.
    """
    objective_target = _extract_target_from_objective(objective) or ""
    objective_is_generic = (
        not objective_target
        or objective_target.startswith("INC-")
        or objective_target.startswith("PRJ-")
    )
    episodic = memory.get("episodic") if isinstance(memory, dict) else []
    for row in episodic or []:
        if row.get("status") != "completed":
            continue
        result = row.get("result_summary") or ""
        if not result:
            continue
        for pattern in [
            r"\b(SERVER-[A-Z0-9-]+)\b",
            r"\b(HOST-[A-Z0-9-]+)\b",
            r"\b(USER-[A-Z0-9-]+)\b",
        ]:
            match = re.search(pattern, result, re.IGNORECASE)
            if match:
                entity = match.group(1).upper()
                if objective_is_generic or entity == objective_target:
                    return entity
    return ""


class DecisionEngine:
    """Adaptive next-action selector that uses world state, blackboard, and memory."""

    def __init__(self, world: WorldObserver):
        self.world = world

    def _observe(self, incident_id: str, project_id: str) -> dict[str, Any]:
        """Return a fresh world observation for the current scope."""
        return self.world.observe_environment(
            incident_id=incident_id, project_id=project_id, dataset_id=""
        )

    def _top_active_hypothesis(self, blackboard: Blackboard) -> Hypothesis | None:
        """Return the highest-confidence non-rejected hypothesis."""
        return blackboard.top_hypothesis()

    def _focus_hypothesis(self, blackboard: Blackboard) -> Hypothesis | None:
        """Prefer the hypothesis tied to the current candidate, else the top one."""
        if blackboard.current_candidate:
            h = blackboard.get_hypothesis(blackboard.current_candidate)
            if h and h.status not in ("rejected",):
                return h
        return self._top_active_hypothesis(blackboard)

    def _is_tool_done(
        self, tool: str, blackboard: Blackboard, entity: str = ""
    ) -> bool:
        """Check whether a tool is done or failed, optionally for a specific entity."""
        action = f"{tool}:{entity}" if entity else tool
        return _has_action(action, blackboard.completed_actions) or _has_action(
            action, blackboard.failed_actions
        )

    def _inputs_for_entity(
        self, tool: str, incident_id: str, project_id: str, entity: str
    ) -> dict[str, Any]:
        if incident_id:
            return {"incident_id": incident_id, "entity_id": entity}
        if project_id:
            return {"project_id": project_id, "entity_id": entity}
        return {"entity_id": entity}

    def _next_tool_for_candidate(
        self,
        top: Hypothesis,
        blackboard: Blackboard,
        observation: dict[str, Any],
        incident_id: str,
        project_id: str,
    ) -> tuple[str, dict[str, Any], str]:
        """Return (tool, inputs, purpose) for the current leading hypothesis."""
        entity = top.entity_id or blackboard.current_candidate or ""
        next_tool = top.next_test or ""

        if next_tool and self._is_tool_done(next_tool, blackboard, entity):
            chain = [
                "correlate_entities",
                "investigate_entity",
                "trace_attack_path",
                "reconstruct_timeline",
                "verify_conclusion",
            ]
            if next_tool in chain:
                idx = chain.index(next_tool)
                for later in chain[idx + 1 :]:
                    if not self._is_tool_done(later, blackboard, entity):
                        next_tool = later
                        break

        graph = observation.get("graph", {}) if observation else {}
        telemetry = observation.get("telemetry", {}) if observation else {}

        if next_tool == "trace_attack_path" and (
            not graph.get("found") or graph.get("node_count", 0) == 0
        ):
            if not self._is_tool_done("reconstruct_timeline", blackboard, entity):
                next_tool = "reconstruct_timeline"
            elif not self._is_tool_done("get_telemetry", blackboard):
                next_tool = "get_telemetry"

        if next_tool == "reconstruct_timeline" and telemetry.get("total_events", 0) == 0:
            if not self._is_tool_done("get_telemetry", blackboard):
                next_tool = "get_telemetry"

        if next_tool == "correlate_entities" and self._is_tool_done(
            "correlate_entities", blackboard, entity
        ):
            if not self._is_tool_done("investigate_entity", blackboard, entity):
                next_tool = "investigate_entity"

        if next_tool == "investigate_entity" and top.status == "rejected":
            next_tool = ""

        if next_tool and not self._is_tool_done(next_tool, blackboard, entity):
            inputs = self._inputs_for_entity(next_tool, incident_id, project_id, entity)
            purposes = {
                "correlate_entities": f"Correlate evidence for {entity} to test '{top.statement}'.",
                "investigate_entity": f"Deep-dive into {entity} to test the leading hypothesis.",
                "trace_attack_path": f"Trace how {entity} relates to other assets.",
                "reconstruct_timeline": f"Reconstruct the timeline for {entity}.",
                "verify_conclusion": "Verify the current hypothesis before finalizing.",
            }
            return (
                next_tool,
                inputs,
                purposes.get(next_tool, f"Investigate {entity}"),
            )

        if not self._is_tool_done("investigate_entity", blackboard, entity):
            return (
                "investigate_entity",
                self._inputs_for_entity("investigate_entity", incident_id, project_id, entity),
                f"Deep-dive into {entity} to test the leading hypothesis.",
            )

        if not self._is_tool_done("reconstruct_timeline", blackboard, entity):
            return (
                "reconstruct_timeline",
                self._inputs_for_entity("reconstruct_timeline", incident_id, project_id, entity),
                f"Reconstruct the timeline for {entity}.",
            )

        return "", {}, ""

    def _recovery_decision(
        self,
        blackboard: Blackboard,
        last_result: dict[str, Any],
        incident_id: str,
        project_id: str,
    ) -> NextDecision | None:
        """Build a recovery decision for the last failed tool, filtering alternates."""
        tool_name = last_result.get("tool_name", "")
        error_code = last_result.get("error_code", "")
        error_message = last_result.get("error_message", "")
        failed_count = sum(
            1 for a in blackboard.failed_actions if a.split(":")[0].strip() == tool_name
        )
        recovery = FailureClassifier.classify(
            tool_name, error_code, error_message, retry_count=failed_count, max_retries=1
        )

        if recovery.action == "retry":
            return NextDecision(
                kind="tool",
                tool=tool_name,
                inputs=last_result.get("inputs", {}),
                purpose_summary=recovery.reason,
                recovery_action=recovery.action,
                continue_after_result=True,
            )

        if recovery.alternate_tool:
            alternates = recovery.alternate_tool
            if not isinstance(alternates, list):
                alternates = [alternates]

            failed_inputs = last_result.get("inputs", {})
            entity_id = failed_inputs.get("entity_id", blackboard.current_candidate or "")

            for alt in alternates:
                if self._is_tool_done(alt, blackboard, entity_id):
                    continue
                if alt in (
                    "correlate_entities",
                    "investigate_entity",
                    "trace_attack_path",
                    "reconstruct_timeline",
                ):
                    if not entity_id:
                        continue
                    inputs = (
                        {"incident_id": incident_id, "entity_id": entity_id}
                        if incident_id
                        else {"project_id": project_id, "entity_id": entity_id}
                    )
                elif alt == "observe_project":
                    inputs = (
                        {"project_id": project_id} if project_id else {"objective": blackboard.goal}
                    )
                else:
                    inputs = (
                        {"incident_id": incident_id} if incident_id else {"project_id": project_id}
                    )

                return NextDecision(
                    kind="tool",
                    tool=alt,
                    inputs=inputs,
                    purpose_summary=recovery.reason,
                    recovery_action=recovery.action,
                    continue_after_result=True,
                )

            return NextDecision(
                kind="replan",
                tool="",
                inputs={},
                purpose_summary=recovery.reason,
                recovery_action=recovery.action,
                continue_after_result=True,
            )

        return None

    def decide(
        self,
        mission: Mission,
        blackboard: Blackboard,
        observation: dict[str, Any] | None,
        last_result: dict[str, Any] | None,
        memory: dict[str, Any],
    ) -> NextDecision:
        """Return the next decision for the current mission state."""
        objective = mission.objective
        blackboard.current_entity or _extract_target_from_objective(objective)
        incident_id = mission.incident_id or blackboard.current_incident
        project_id = mission.project_id

        if last_result and last_result.get("status") == "failure":
            recovery = self._recovery_decision(blackboard, last_result, incident_id, project_id)
            if recovery:
                return recovery

        if mission.iteration == 0 and not blackboard.completed_actions:
            if project_id and not incident_id:
                return NextDecision(
                    kind="tool",
                    tool="observe_project",
                    inputs={"project_id": project_id},
                    purpose_summary="Understand the project environment before investigating.",
                    expected_result="Project summary, dataset, artifacts, and incidents.",
                    continue_after_result=True,
                )
            if incident_id:
                return NextDecision(
                    kind="tool",
                    tool="observe_environment",
                    inputs={"incident_id": incident_id},
                    purpose_summary="Load incident context and telemetry summary.",
                    expected_result="Incident details, telemetry counts, and graph summary.",
                    continue_after_result=True,
                )
            return NextDecision(
                kind="tool",
                tool="observe_environment",
                inputs={"objective": objective},
                purpose_summary="Scan the available environment to identify candidate targets.",
                expected_result="Overall metrics and unresolved incidents.",
                continue_after_result=True,
            )

        if not blackboard.hypotheses and not blackboard.facts.get("detect_attempted"):
            prior_entity = _entity_from_prior_memory(memory, objective)
            if prior_entity and incident_id:
                h = Hypothesis(
                    id=prior_entity,
                    statement=f"{prior_entity} is involved in suspicious activity",
                    confidence=0.7,
                    evidence_for=["prior_execution"],
                    next_test="investigate_entity",
                    entity_id=prior_entity,
                )
                blackboard.add_hypothesis(h)
                blackboard.current_candidate = prior_entity

        if not blackboard.hypotheses:
            if blackboard.facts.get("detect_attempted"):
                if not self._is_tool_done("get_telemetry", blackboard) and incident_id:
                    return NextDecision(
                        kind="tool",
                        tool="get_telemetry",
                        inputs={"incident_id": incident_id, "limit": 50},
                        purpose_summary="No anomaly candidates; inspect raw telemetry for clues.",
                        expected_result="Recent events for the incident.",
                        continue_after_result=True,
                    )
                return NextDecision(
                    kind="complete",
                    purpose_summary="No anomalies or telemetry evidence found.",
                    expected_result="Mission complete with evidence-insufficient result.",
                    continue_after_result=False,
                )

            if incident_id:
                return NextDecision(
                    kind="tool",
                    tool="detect_anomalies",
                    inputs={"incident_id": incident_id},
                    purpose_summary="Identify anomalous entities and events.",
                    expected_result="A ranked list of suspicious hosts, users, or events.",
                    continue_after_result=True,
                )
            if project_id:
                return NextDecision(
                    kind="tool",
                    tool="detect_anomalies",
                    inputs={"project_id": project_id},
                    purpose_summary="Find the strongest anomalies in the project dataset.",
                    expected_result="A ranked list of suspicious entities.",
                    continue_after_result=True,
                )

        world_state = (
            observation if observation is not None else self._observe(incident_id, project_id)
        )
        top = self._focus_hypothesis(blackboard)

        if top:
            active = [h for h in blackboard.hypotheses if h.status not in ("rejected",)]
            if len(active) >= 2:
                sorted_active = sorted(active, key=lambda h: h.confidence, reverse=True)
                if (
                    len(sorted_active) >= 2
                    and (sorted_active[0].confidence - sorted_active[1].confidence) < 0.15
                    and (
                        not top.next_test
                        or self._is_tool_done(top.next_test, blackboard, top.entity_id)
                    )
                ):
                    if not self._is_tool_done("test_hypothesis", blackboard):
                        return NextDecision(
                            kind="tool",
                            tool="test_hypothesis",
                            inputs={
                                "incident_id": incident_id,
                                "entity_id": top.entity_id,
                                "hypothesis": top.statement,
                            }
                            if incident_id
                            else {
                                "project_id": project_id,
                                "entity_id": top.entity_id,
                                "hypothesis": top.statement,
                            },
                            purpose_summary=f"Compare hypotheses; test '{top.statement}'.",
                            expected_result="Evidence for or against the hypothesis.",
                            continue_after_result=True,
                        )

            tool, inputs, purpose = self._next_tool_for_candidate(
                top, blackboard, world_state, incident_id, project_id
            )
            if tool:
                return NextDecision(
                    kind="tool",
                    tool=tool,
                    inputs=inputs,
                    purpose_summary=purpose,
                    expected_result="Tool result for the selected action.",
                    continue_after_result=True,
                )

            blackboard.current_candidate = ""
            top = self._top_active_hypothesis(blackboard)
            if top:
                blackboard.current_candidate = top.entity_id
                tool, inputs, purpose = self._next_tool_for_candidate(
                    top, blackboard, world_state, incident_id, project_id
                )
                if tool:
                    return NextDecision(
                        kind="tool",
                        tool=tool,
                        inputs=inputs,
                        purpose_summary=purpose,
                        expected_result="Evidence for the next candidate.",
                        continue_after_result=True,
                    )

        top = self._top_active_hypothesis(blackboard)
        if top and top.confidence >= mission.confidence_threshold and len(blackboard.evidence) >= 2:
            return NextDecision(
                kind="tool",
                tool="verify_conclusion",
                inputs={"incident_id": incident_id, "project_id": project_id},
                purpose_summary="Verify the current hypothesis before finalizing.",
                expected_result="Verification pass or fail with missing evidence.",
                continue_after_result=True,
            )

        if incident_id:
            if not self._is_tool_done("get_telemetry", blackboard):
                return NextDecision(
                    kind="tool",
                    tool="get_telemetry",
                    inputs={"incident_id": incident_id, "limit": 50},
                    purpose_summary="Collect more telemetry to find additional evidence.",
                    expected_result="Recent events for the incident.",
                    continue_after_result=True,
                )
            return NextDecision(
                kind="complete",
                purpose_summary="No further actionable steps and no new telemetry to collect.",
                expected_result="Mission complete with evidence-insufficient result.",
                continue_after_result=False,
            )

        if project_id:
            return NextDecision(
                kind="tool",
                tool="observe_project",
                inputs={"project_id": project_id},
                purpose_summary="Refresh the project observation and look for new evidence.",
                expected_result="Updated project, dataset, and artifact summary.",
                continue_after_result=True,
            )

        if top and top.confidence < mission.confidence_threshold:
            return NextDecision(
                kind="complete",
                purpose_summary="Evidence is insufficient for a high-confidence conclusion.",
                expected_result="Mission complete with evidence-insufficient result.",
                continue_after_result=False,
            )

        return NextDecision(
            kind="complete",
            purpose_summary="Investigation complete; no further actionable steps.",
            expected_result="Mission complete.",
            continue_after_result=False,
        )
