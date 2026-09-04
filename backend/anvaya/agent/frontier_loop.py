"""Frontier model-driven agent execution loop.

This is the core iterative agent engine where the frontier model participates
at every iteration, deciding the single best next action based on accumulated
observations, blackboard state, and mission constraints.

The loop follows an 8-phase cycle:
    A. Observe — collect current state
    B. Reason — call model, stream safe reasoning
    C. Decide — validate selected action
    D. Execute — run exactly one tool
    E. Observe result — create observation from result
    F. Update state — update blackboard, mission, plan
    G. Verify — check completion condition
    H. Re-enter model — repeat from A
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from sqlmodel import Session, select

from anvaya.agent.blackboard import Blackboard
from anvaya.agent.frontier_decision import (
    FrontierDecisionEngine,
    NextActionContract,
    build_model_context,
    stream_frontier_reasoning,
)
from anvaya.agent.memory import MemoryStore
from anvaya.agent.messaging import MessageGenerator
from anvaya.agent.mission import Mission
from anvaya.agent.profiles import AgentProfile
from anvaya.agent.registry import ToolRegistry
from anvaya.agent.schemas import ModelConfig, ToolResult
from anvaya.agent.scope import ScopeConstraints, enforce_scope, parse_scope
from anvaya.agent.verification import VerificationResult, verify_action_completion
from anvaya.agent.world import WorldObserver
from anvaya.logging import get_logger
from anvaya.models.agent_context import ExecutionContext
from anvaya.models.execution import Execution, ExecutionEvent
from anvaya.models.project import ARTIFACT_TYPES

logger = get_logger("anvaya.agent.frontier_loop")




def _next_sequence(session: Session, execution_id: str) -> int:
    last = session.exec(
        select(ExecutionEvent)
        .where(ExecutionEvent.execution_id == execution_id)
        .order_by(ExecutionEvent.sequence.desc())
    ).first()
    return (last.sequence + 1) if last else 1


def _safe_payload(inputs: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for k, v in inputs.items():
        if isinstance(v, (str, int, float, bool)):
            safe[k] = v
        elif isinstance(v, dict):
            safe[k] = {sk: sv for sk, sv in v.items() if isinstance(sv, (str, int, float, bool))}
        elif isinstance(v, list):
            safe[k] = v[:10]
        else:
            safe[k] = str(v)[:120]
    return safe


def _build_observation(tool_name: str, result: ToolResult, step_index: int) -> dict[str, Any]:
    """Build a user-safe observation from a tool result."""
    facts: dict[str, Any] = {"status": result.status}
    output = result.output or {}

    if result.status == "success":
        for key, value in output.items():
            if key in facts:
                continue
            if isinstance(value, (int, float, bool, str)):
                facts[key] = value
            elif isinstance(value, list):
                facts[f"{key}_count"] = len(value)
            elif isinstance(value, dict):
                facts[f"{key}_keys"] = list(value.keys())[:5]

        facts["artifact_count"] = len(result.artifact_refs)
        facts["fallback_used"] = result.fallback_used
    else:
        facts["error_code"] = result.error_code
        facts["error_message"] = result.error_message

    facts = {k: v for k, v in facts.items() if v is not None}

    return {
        "summary": result.output_summary or result.error_message or f"{tool_name} finished",
        "facts": facts,
        "source": tool_name,
        "step_index": step_index,
    }


def _inputs_key(inputs: dict[str, Any]) -> str:
    """Create a hashable key from tool inputs for retry tracking."""
    try:
        return json.dumps(inputs, sort_keys=True, default=str)[:200]
    except Exception:
        return str(inputs)[:200]




def run_frontier(
    *,
    loop: Any,
    execution: Execution,
    incident_id: str,
    profile: AgentProfile,
    active_model: ModelConfig,
    model_provider: Any,
    messenger: MessageGenerator,
    objective: str,
    project_id: str,
    world: WorldObserver,
    memory_store: MemoryStore,
    initial_plan: list[dict[str, Any]],
    scope: ScopeConstraints | None = None,
) -> Execution:
    """Run the frontier model-driven iterative agent loop.

    This is the heart of the upgrade: the model participates at every
    iteration, deciding the single best next action based on accumulated
    observations.
    """
    started = perf_counter()
    execution_id = execution.execution_id
    session: Session = loop.session
    store = loop.store
    executor = loop.executor
    registry: ToolRegistry = loop.registry

    if scope is None:
        scope = parse_scope(objective)

    frontier = FrontierDecisionEngine(model_provider, active_model, registry)

    initial_plan_normalized = [
        {
            "tool": s.get("tool", ""),
            "inputs": s.get("inputs", {}),
            "label": s.get("label", s.get("tool", "")),
            "status": "pending",
            "optional": s.get("optional", False),
            "stop_on_failure": s.get("stop_on_failure", False),
        }
        for s in (initial_plan or [])
    ]
    context = loop._get_or_create_context(
        execution_id=execution_id,
        objective=objective,
        incident_id=incident_id,
        project_id=project_id,
        plan=initial_plan_normalized,
        observations=[],
        messages=[],
        reasoning_summary="",
        current_action={},
        model=active_model.id if active_model else profile.model_name,
        provider=active_model.provider if active_model else "anvaya",
        status="running",
    )

    if context.status == "cancelled":
        loop._emit_execution_interrupted(execution_id, "cancelled")
        store.complete_execution(
            session,
            execution_id,
            "cancelled",
            result_summary="Execution cancelled before it started",
            error_code="cancelled",
            error_message="Execution cancelled before it started",
        )
        return execution

    mission = Mission(
        objective=objective,
        project_id=project_id,
        dataset_id=project_id,
        incident_id=incident_id,
        max_iterations=20,
        max_tool_calls=50,
        max_model_calls=25,
        confidence_threshold=0.75,
        constraints=scope.to_constraint_strings(),
        allowed_artifacts=scope.allowed_artifacts,
    )
    context.set_mission(mission.model_dump())

    blackboard = Blackboard(
        goal=objective,
        scope_constraints=scope.to_constraint_strings(),
    )
    context.set_blackboard(blackboard.model_dump())
    context.set_hypotheses([])
    context.set_findings([])
    context.set_verification({})

    sequence = _next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        sequence,
        "agent.message",
        label="Mission started",
        payload={
            "message": messenger.start(objective, incident_id or project_id),
            "profile": profile.id,
            "profile_display_name": profile.display_name,
            "incident_id": incident_id,
            "project_id": project_id,
        },
    )

    sequence = _next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        sequence,
        "agent.plan_created",
        label="Plan created",
        payload={
            "objective": objective,
            "steps": [s["tool"] for s in initial_plan_normalized],
            "plan": initial_plan_normalized,
            "can_update": True,
            "provider": context.provider or "anvaya",
            "profile": profile.id,
            "model": context.model or profile.model_name,
            "scope": scope.model_dump(),
        },
    )

    observation = world.observe_environment(
        project_id=project_id, incident_id=incident_id, dataset_id=""
    )
    blackboard.add_fact("environment_observed", f"project={project_id}, incident={incident_id}")
    context.set_blackboard(blackboard.model_dump())

    sequence = _next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        sequence,
        "agent.observation",
        label="Environment observed",
        payload={"summary": _summarize_observation(observation), "observation": observation},
    )

    memory = memory_store.recall(execution_id, project_id=project_id, incident_id=incident_id)
    context.set_memory(memory)

    results: list[ToolResult] = []
    fallback_used = False
    fallback_reason = ""
    latest_observation: dict[str, Any] | None = None
    reasoning_counter = 0

    try:
        while mission.should_continue():
            session.refresh(context)
            if context.status == "cancelled":
                break

            stop, _ = loop._check_messages(execution, context)
            if stop:
                break

            user_updates = [
                m for m in (context.messages or []) if not m.get("processed")
            ]

            recent_failures = list(blackboard.failed_actions[-5:])

            model_context_str = build_model_context(
                mission=mission,
                context=context,
                blackboard=blackboard,
                available_tools=frontier._tool_summaries(),
                latest_observation=latest_observation,
                latest_tool_result=_result_to_dict(results[-1]) if results else None,
                user_updates=user_updates if user_updates else None,
                artifact_state=blackboard.artifact_state or None,
                recent_failures=recent_failures if recent_failures else None,
            )

            reasoning_counter += 1
            reasoning_id = f"reason-{execution_id}-{reasoning_counter}"

            sequence = _next_sequence(session, execution_id)
            store.emit(
                session,
                execution_id,
                sequence,
                "agent.reasoning_started",
                label="Reasoning started",
                payload={"reasoning_id": reasoning_id},
            )

            full_reasoning = ""
            try:
                for delta in stream_frontier_reasoning(
                    model_provider, active_model, model_context_str
                ):
                    full_reasoning += delta
                    sequence = _next_sequence(session, execution_id)
                    store.emit(
                        session,
                        execution_id,
                        sequence,
                        "agent.reasoning_delta",
                        label="Reasoning delta",
                        payload={"reasoning_id": reasoning_id, "delta": delta},
                    )
            except Exception as exc:
                logger.warning("frontier.reasoning_stream_error", error=str(exc))
                full_reasoning = "Analyzing current state..."
                sequence = _next_sequence(session, execution_id)
                store.emit(
                    session,
                    execution_id,
                    sequence,
                    "agent.reasoning_delta",
                    label="Reasoning delta",
                    payload={"reasoning_id": reasoning_id, "delta": full_reasoning},
                )

            sequence = _next_sequence(session, execution_id)
            store.emit(
                session,
                execution_id,
                sequence,
                "agent.reasoning_completed",
                label="Reasoning completed",
                payload={
                    "reasoning_id": reasoning_id,
                    "summary": full_reasoning[:500],
                    "source": "frontier_model",
                },
            )
            context.reasoning_summary = full_reasoning[:500]

            mission.model_step()

            contract = frontier.decide(
                mission=mission,
                context=context,
                blackboard=blackboard,
                latest_observation=latest_observation,
                latest_tool_result=_result_to_dict(results[-1]) if results else None,
                user_updates=user_updates if user_updates else None,
                artifact_state=blackboard.artifact_state or None,
                recent_failures=recent_failures if recent_failures else None,
            )

            sequence = _next_sequence(session, execution_id)
            store.emit(
                session,
                execution_id,
                sequence,
                "agent.decision_started",
                label=f"Deciding {contract.action}",
                payload={
                    "step_index": mission.iteration,
                    "action": contract.action,
                    "reason": contract.reason,
                    "inputs_safe": _safe_payload(contract.inputs),
                },
            )

            if contract.action == "finish":
                _emit_completion(
                    session=session,
                    store=store,
                    execution_id=execution_id,
                    contract=contract,
                    results=results,
                    fallback_used=fallback_used,
                    fallback_reason=fallback_reason,
                    started=started,
                    context=context,
                    mission=mission,
                    messenger=messenger,
                    profile=profile,
                )
                return store.get_execution(session, execution_id) or execution

            if contract.action == "replan":
                if contract.plan_update:
                    context.plan = contract.plan_update
                    loop._save_context(context)
                    sequence = _next_sequence(session, execution_id)
                    store.emit(
                        session,
                        execution_id,
                        sequence,
                        "agent.plan_updated",
                        label="Plan updated",
                        payload={
                            "plan": contract.plan_update,
                            "reason": contract.reason,
                        },
                    )
                mission.step()
                context.set_mission(mission.model_dump())
                continue

            if contract.action == "ask_user":
                mission.status = "paused"
                context.set_mission(mission.model_dump())
                sequence = _next_sequence(session, execution_id)
                store.emit(
                    session,
                    execution_id,
                    sequence,
                    "agent.awaiting_input",
                    label="Awaiting user input",
                    payload={"reason": contract.reason},
                )
                break

            if contract.action == "verify":
                if results:
                    vr = verify_action_completion(
                        results[-1].tool_name,
                        results[-1],
                        contract.completion_condition,
                        session=session,
                        project_id=project_id,
                    )
                    _emit_verification(session, store, execution_id, vr)
                    if vr.passed:
                        blackboard.add_completed_action(f"verify:{results[-1].tool_name}")
                mission.step()
                context.set_mission(mission.model_dump())
                continue

            tool_name = contract.action
            inputs = dict(contract.inputs)

            inputs = enforce_scope(tool_name, inputs, scope)

            if "requested_artifacts" in inputs:
                requested = inputs["requested_artifacts"]
                if isinstance(requested, list) and "all" in requested:
                    inputs["requested_artifacts"] = list(ARTIFACT_TYPES)

            ik = _inputs_key(inputs)
            retry_count = frontier.get_retry_count(tool_name, ik)
            if retry_count >= 2:
                logger.warning(
                    "frontier.max_retries_exceeded",
                    tool=tool_name,
                    retries=retry_count,
                )
                blackboard.add_failed_action(
                    tool_name, f"max retries ({retry_count}) exceeded"
                )
                mission.step()
                context.set_blackboard(blackboard.model_dump())
                context.set_mission(mission.model_dump())
                continue

            context.current_action = {
                "tool_name": tool_name,
                "label": contract.reason[:80] or f"Running {tool_name}",
                "status": "running",
                "target": incident_id or project_id,
                "step_index": mission.iteration,
            }
            context.set_blackboard(blackboard.model_dump())
            loop._save_context(context)

            sequence = _next_sequence(session, execution_id)
            store.emit(
                session,
                execution_id,
                sequence,
                "agent.tool_requested",
                label=f"Requesting {tool_name}",
                payload={
                    "tool_name": tool_name,
                    "label": contract.reason[:80],
                    "purpose": contract.reason,
                },
            )

            sequence = _next_sequence(session, execution_id)
            tool_call_id = f"{execution_id}-{tool_name}-{sequence}"
            store.emit(
                session,
                execution_id,
                sequence,
                "tool.started",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                provider=profile.model_provider,
                status="running",
                label=f"Running {tool_name}",
                payload={"inputs": _safe_payload(inputs)},
            )

            result = executor.execute(
                tool_name, inputs, tool_call_id=tool_call_id, execution_id=execution_id
            )
            results.append(result)

            if result.fallback_used:
                fallback_used = True
                if not fallback_reason:
                    fallback_reason = f"{tool_name}: {result.fallback_reason}"

            if result.status == "success":
                sequence = _next_sequence(session, execution_id)
                store.emit(
                    session,
                    execution_id,
                    sequence,
                    "tool.completed",
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    provider=profile.model_provider or "anvaya",
                    status="completed",
                    label=f"{tool_name} completed",
                    payload={
                        "duration_ms": result.duration_ms,
                        "output_summary": result.output_summary,
                        "artifact_count": len(result.artifact_refs),
                    },
                )
            else:
                sequence = _next_sequence(session, execution_id)
                store.emit(
                    session,
                    execution_id,
                    sequence,
                    "tool.failed",
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    status="failed",
                    label=f"{tool_name} failed",
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
                frontier.track_retry(tool_name, ik)

            for artifact in result.artifact_refs:
                sequence = _next_sequence(session, execution_id)
                store.emit(
                    session,
                    execution_id,
                    sequence,
                    "artifact.saved",
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    provider=result.provider,
                    status="success",
                    label=artifact.label,
                    artifact_ref=artifact.ref_id,
                    artifact_type=artifact.ref_type,
                    payload={"link": artifact.link, "label": artifact.label},
                )

            latest_observation = _build_observation(tool_name, result, mission.iteration)
            context.observations = list(context.observations) + [latest_observation]

            sequence = _next_sequence(session, execution_id)
            store.emit(
                session,
                execution_id,
                sequence,
                "agent.observation_created",
                label=f"Observation from {tool_name}",
                payload=latest_observation,
            )

            if result.status == "success":
                blackboard.add_completed_action(tool_name)
                blackboard.add_evidence(
                    ref=tool_call_id,
                    summary=result.output_summary or "",
                    tool=tool_name,
                )
                if tool_name in ("manage_artifacts", "generate_artifacts"):
                    for aref in result.artifact_refs:
                        blackboard.update_artifact_state(aref.ref_type, "saved")
            else:
                blackboard.add_failed_action(tool_name, result.error_message or result.error_code)

            updated_plan = list(context.plan or [])
            for step in updated_plan:
                if step.get("tool") == tool_name and step.get("status") == "pending":
                    step["status"] = "completed" if result.status == "success" else "failed"
                    step["result_summary"] = result.output_summary or result.error_message or ""
                    break
            context.plan = updated_plan

            mission.step()
            context.set_mission(mission.model_dump())
            context.set_blackboard(blackboard.model_dump())
            loop._save_context(context)

            if contract.completion_condition and result.status == "success":
                vr = verify_action_completion(
                    tool_name,
                    result,
                    contract.completion_condition,
                    session=session,
                    project_id=project_id,
                )
                _emit_verification(session, store, execution_id, vr)

                if not vr.passed:
                    blackboard.add_fact(
                        f"verification_failed:{tool_name}",
                        vr.reason,
                    )
                    context.set_blackboard(blackboard.model_dump())
                    loop._save_context(context)


    except Exception as exc:
        logger.error("frontier.loop_error", execution_id=execution_id, error=str(exc))
        _fail_execution(
            session=session,
            store=store,
            execution_id=execution_id,
            context=context,
            error_code="frontier_loop_error",
            error_message=str(exc),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
        return store.get_execution(session, execution_id) or execution

    if mission.status == "paused":
        return store.get_execution(session, execution_id) or execution

    if context.status == "cancelled":
        loop._emit_execution_interrupted(execution_id, "User cancelled execution")
        store.complete_execution(
            session,
            execution_id,
            "cancelled",
            result_summary="Execution cancelled by user",
            error_code="cancelled",
            error_message="Execution cancelled by user",
        )
        return store.get_execution(session, execution_id) or execution

    budget_reason = _budget_exhaustion_reason(mission)
    _emit_completion(
        session=session,
        store=store,
        execution_id=execution_id,
        contract=NextActionContract(
            action="finish",
            reason=budget_reason,
            summary=f"Completed after {mission.iteration} iterations. {budget_reason}",
        ),
        results=results,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        started=started,
        context=context,
        mission=mission,
        messenger=messenger,
        profile=profile,
    )
    return store.get_execution(session, execution_id) or execution




def _emit_completion(
    *,
    session: Session,
    store: Any,
    execution_id: str,
    contract: NextActionContract,
    results: list[ToolResult],
    fallback_used: bool,
    fallback_reason: str,
    started: float,
    context: ExecutionContext,
    mission: Mission,
    messenger: MessageGenerator,
    profile: AgentProfile,
) -> None:
    """Emit completion events and finalize execution."""
    duration_ms = round((perf_counter() - started) * 1000, 2)
    successful = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status != "success")
    artifacts = sum(len(r.artifact_refs) for r in results)

    result_summary = contract.summary or contract.reason or (
        f"Ran {len(results)} tools: {successful} succeeded, {failed} failed, "
        f"{artifacts} artifacts."
    )

    sequence = _next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        sequence,
        "agent.message",
        label="Execution complete",
        payload={
            "message": result_summary,
            "profile": profile.id,
        },
    )

    sequence = _next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        sequence,
        "agent.completed",
        label="Execution complete",
        payload={
            "duration_ms": duration_ms,
            "tools_run": len(results),
            "successful": successful,
            "failed": failed,
            "fallback_used": fallback_used,
            "result_summary": result_summary,
            "iterations": mission.iteration,
            "model_calls": mission.model_calls,
        },
    )

    context.status = "completed"
    context.reasoning_summary = result_summary
    context.current_action = {}
    context.completed_at = datetime.now(timezone.utc)
    mission.complete(result_summary)
    context.set_mission(mission.model_dump())
    session.add(context)
    session.commit()

    store.complete_execution(
        session,
        execution_id,
        "completed",
        result_summary=result_summary,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )


def _emit_verification(
    session: Session,
    store: Any,
    execution_id: str,
    vr: VerificationResult,
) -> None:
    """Emit verification started/completed events."""
    sequence = _next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        sequence,
        "agent.verification_started",
        label="Verification started",
        payload={},
    )

    sequence = _next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        sequence,
        "agent.verification_completed",
        label="Verification " + ("passed" if vr.passed else "failed"),
        payload={
            "passed": vr.passed,
            "reason": vr.reason,
            "missing": vr.missing,
            "contradictions": vr.contradictions,
            "confidence": vr.confidence,
            "evidence_count": vr.evidence_count,
        },
    )


def _fail_execution(
    *,
    session: Session,
    store: Any,
    execution_id: str,
    context: ExecutionContext,
    error_code: str,
    error_message: str,
    fallback_used: bool,
    fallback_reason: str,
) -> None:
    """Emit failure events and finalize execution."""
    sequence = _next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        sequence,
        "agent.failed",
        label="Execution failed",
        error_code=error_code,
        error_message=error_message,
        payload={"fallback_used": fallback_used, "fallback_reason": fallback_reason},
    )

    context.status = "failed"
    context.reasoning_summary = f"Execution failed: {error_message}"
    context.current_action = {}
    context.completed_at = datetime.now(timezone.utc)
    session.add(context)
    session.commit()

    store.complete_execution(
        session,
        execution_id,
        "failed",
        result_summary=f"Execution failed: {error_message}",
        error_code=error_code,
        error_message=error_message,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )




def _result_to_dict(result: ToolResult) -> dict[str, Any]:
    """Convert a ToolResult to a compact dict for model context."""
    return {
        "tool_name": result.tool_name,
        "status": result.status,
        "output_summary": result.output_summary,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "artifact_count": len(result.artifact_refs),
        "duration_ms": result.duration_ms,
    }


def _summarize_observation(observation: dict[str, Any]) -> str:
    """Create a compact summary from a world observation."""
    parts: list[str] = []
    if observation.get("telemetry", {}).get("total_events"):
        parts.append(f"telemetry: {observation['telemetry']['total_events']} events")
    if observation.get("graph", {}).get("node_count"):
        parts.append(f"graph: {observation['graph']['node_count']} nodes")
    if observation.get("incident", {}).get("found"):
        parts.append(f"incident: {observation['incident'].get('severity', 'unknown')}")
    if observation.get("project", {}).get("found"):
        parts.append(f"project: {observation['project'].get('name', 'unknown')}")
    return "; ".join(parts) if parts else "Environment observed."


def _budget_exhaustion_reason(mission: Mission) -> str:
    """Return the reason the mission budget was exhausted."""
    if mission.iteration >= mission.max_iterations:
        return f"Reached max iterations ({mission.max_iterations})."
    if mission.tool_calls >= mission.max_tool_calls:
        return f"Reached max tool calls ({mission.max_tool_calls})."
    if mission.model_calls >= mission.max_model_calls:
        return f"Reached max model calls ({mission.max_model_calls})."
    return "Budget exhausted."
