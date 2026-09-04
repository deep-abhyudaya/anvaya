"""Adaptive observe-decide-act loop for ANVAYA agent execution."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from sqlmodel import Session, select

from anvaya.agent.blackboard import Blackboard, Hypothesis
from anvaya.agent.decision import DecisionEngine
from anvaya.agent.memory import MemoryStore
from anvaya.agent.messaging import MessageGenerator
from anvaya.agent.mission import Mission
from anvaya.agent.profiles import AgentProfile
from anvaya.agent.schemas import ToolResult
from anvaya.agent.verification import verify_conclusion
from anvaya.agent.world import WorldObserver
from anvaya.logging import get_logger
from anvaya.models.execution import Execution, ExecutionEvent
from anvaya.models.project import ARTIFACT_TYPES
from anvaya.agent.frontier_loop import run_frontier
from anvaya.agent.scope import parse_scope

logger = get_logger("anvaya.agent.adaptive_loop")


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
        else:
            safe[k] = str(v)[:120]
    return safe


def _extract_target_from_result(result: ToolResult) -> str:
    output = result.output or {}
    for key in ("entity_id", "host", "user", "incident_id", "candidate"):
        if output.get(key):
            return str(output[key])
    summary = result.output_summary or ""
    import re

    patterns = [
        r"\b(HOST-[A-Z0-9-]+)\b",
        r"\b(INC-[A-Z0-9-]+)\b",
        r"\b(SERVER-[A-Z0-9-]+)\b",
        r"\b(USER-[A-Z0-9-]+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, summary, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return ""


def run_adaptive(
    loop: Any,
    execution: Execution,
    incident_id: str,
    profile: AgentProfile,
    active_model: Any,
    messenger: MessageGenerator,
    objective: str,
    project_id: str,
    world: WorldObserver,
    decision_engine: DecisionEngine,
    memory_store: MemoryStore,
    initial_plan: list[dict[str, Any]],
) -> Execution:
    """Run the adaptive observe-decide-act loop for an execution."""
    if active_model and getattr(active_model, 'quality_class', None) == 'frontier':
        from anvaya.llm.providers import get_model_provider_for_config
        _provider = get_model_provider_for_config(active_model)
        if _provider and _provider.configured():
            return run_frontier(
                loop=loop,
                execution=execution,
                incident_id=incident_id,
                profile=profile,
                active_model=active_model,
                model_provider=_provider,
                messenger=messenger,
                objective=objective,
                project_id=project_id,
                world=world,
                memory_store=memory_store,
                initial_plan=initial_plan,
            )

    started = perf_counter()
    execution_id = execution.execution_id
    objective = objective or execution.objective
    session = loop.session
    store = loop.store
    executor = loop.executor

    loop._init_reasoning(active_model)
    reasoning_generator = loop.reasoning_generator
    reasoning_counter = 0

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
        max_iterations=12,
        max_tool_calls=30,
        confidence_threshold=0.75,
    )
    context.set_mission(mission.model_dump())

    blackboard = Blackboard(goal=objective)
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
            "steps": [s["tool"] for s in initial_plan],
            "plan": initial_plan,
            "can_update": True,
            "provider": context.provider or "anvaya",
            "profile": profile.id,
            "model": context.model or profile.model_name,
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
    last_result: dict[str, Any] | None = None

    try:
        while mission.should_continue():
            session.refresh(context)
            if context.status == "cancelled":
                break

            stop, _ = loop._check_messages(execution, context)
            if stop:
                break

            decision = decision_engine.decide(
                mission=mission,
                blackboard=blackboard,
                observation=None,
                last_result=last_result,
                memory=memory,
            )

            sequence = _next_sequence(session, execution_id)
            store.emit(
                session,
                execution_id,
                sequence,
                "agent.decision_started",
                label=f"Deciding {decision.tool or decision.kind}",
                payload={
                    "step_index": mission.iteration,
                    "tool_name": decision.tool,
                    "kind": decision.kind,
                    "inputs_safe": _safe_payload(decision.inputs),
                },
            )

            sequence = _next_sequence(session, execution_id)
            store.emit(
                session,
                execution_id,
                sequence,
                "agent.decision",
                label=f"Next action: {decision.kind}",
                payload={
                    "kind": decision.kind,
                    "tool": decision.tool,
                    "purpose_summary": decision.purpose_summary,
                    "expected_result": decision.expected_result,
                    "confidence": decision.confidence,
                    "expected_information_gain": decision.expected_information_gain,
                },
            )

            if decision.kind == "complete":
                break

            if decision.kind == "ask_user":
                mission.status = "paused"
                context.set_mission(mission.model_dump())
                sequence = _next_sequence(session, execution_id)
                store.emit(
                    session,
                    execution_id,
                    sequence,
                    "agent.awaiting_input",
                    label="Awaiting user input",
                    payload={"reason": decision.purpose_summary},
                )
                break

            if decision.kind == "replan":
                observation = world.observe_environment(
                    project_id=project_id, incident_id=incident_id, dataset_id=""
                )
                last_result = None
                mission.step()
                context.set_mission(mission.model_dump())
                continue

            tool_name = decision.tool
            inputs = dict(decision.inputs)

            if tool_name == "verify_conclusion":
                inputs["execution_id"] = execution_id

            if "requested_artifacts" in inputs:
                requested = inputs["requested_artifacts"]
                if isinstance(requested, list) and "all" in requested:
                    inputs = {**inputs, "requested_artifacts": list(ARTIFACT_TYPES)}

            step: dict[str, Any] = {
                "tool": tool_name,
                "inputs": inputs,
                "label": decision.purpose_summary or f"Running {tool_name}",
                "status": "running",
                "optional": False,
                "stop_on_failure": False,
                "progress": decision.purpose_summary or "Processing...",
                "completed": f"{tool_name} completed",
            }

            context.current_action = {
                "tool_name": tool_name,
                "label": step["label"],
                "status": "running",
                "target": incident_id or project_id,
                "step_index": mission.iteration,
            }
            context.set_blackboard(blackboard.model_dump())
            loop._save_context(context)

            reasoning_counter += 1
            reasoning_id = f"reason-{execution_id}-{reasoning_counter}"
            sequence = _next_sequence(session, execution_id)
            store.emit(
                session,
                execution_id,
                sequence,
                "agent.reasoning_started",
                label="Reasoning started",
                payload={"reasoning_id": reasoning_id, "summary": decision.purpose_summary},
            )

            previous = results[-1] if results else None
            full_text = ""
            for delta in reasoning_generator.stream(context, step, previous):
                full_text += delta
                sequence = _next_sequence(session, execution_id)
                store.emit(
                    session,
                    execution_id,
                    sequence,
                    "agent.reasoning_delta",
                    label="Reasoning delta",
                    payload={"reasoning_id": reasoning_id, "delta": delta},
                )

            summary = reasoning_generator.generate(context, step, previous)
            if not full_text:
                sequence = _next_sequence(session, execution_id)
                store.emit(
                    session,
                    execution_id,
                    sequence,
                    "agent.reasoning_delta",
                    label="Reasoning delta",
                    payload={"reasoning_id": reasoning_id, "delta": summary},
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
                    "summary": summary,
                    "source": "execution_summary",
                },
            )
            context.reasoning_summary = summary

            sequence = _next_sequence(session, execution_id)
            store.emit(
                session,
                execution_id,
                sequence,
                "agent.tool_requested",
                label=f"Requesting {tool_name}",
                payload={
                    "tool_name": tool_name,
                    "label": step["label"],
                    "purpose": decision.purpose_summary,
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
                label=step["label"],
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
                    payload={"output_summary": result.output_summary},
                )

            observation = _build_observation_from_result(tool_name, result)
            sequence = _next_sequence(session, execution_id)
            store.emit(
                session,
                execution_id,
                sequence,
                "agent.observation_created",
                label=f"Observation from {tool_name}",
                payload={
                    "tool": tool_name,
                    "summary": result.output_summary or result.error_message,
                    "status": result.status,
                    "observation": observation,
                },
            )

            context.observations = list(context.observations) + [observation]

            _update_blackboard_from_result(
                blackboard, tool_name, inputs, result, mission, observation, tool_call_id
            )

            _update_hypotheses(blackboard, tool_name, result, mission)

            if tool_name == "verify_conclusion":
                verification = verify_conclusion(blackboard, mission)
                context.set_verification(verification.model_dump())
                sequence = _next_sequence(session, execution_id)
                if verification.passed:
                    store.emit(
                        session,
                        execution_id,
                        sequence,
                        "agent.verification_passed",
                        label="Verification passed",
                        payload=verification.model_dump(),
                    )
                    top = blackboard.top_hypothesis()
                    finding = {
                        "statement": top.statement if top else objective,
                        "confidence": top.confidence if top else 0.0,
                        "evidence": blackboard.evidence,
                        "entity": blackboard.current_candidate,
                        "incident_id": incident_id,
                    }
                    context.set_findings(context.get_findings() + [finding])
                    blackboard.summary = (
                        f"Finding: {finding['statement']} (confidence {finding['confidence']:.2f})"
                    )
                    mission.complete("High-confidence conclusion verified and persisted.")
                else:
                    store.emit(
                        session,
                        execution_id,
                        sequence,
                        "agent.verification_failed",
                        label="Verification failed",
                        payload=verification.model_dump(),
                    )
                    mission.complete(
                        f"Evidence insufficient: {verification.reason}", status="completed"
                    )

            memory = memory_store.recall(
                execution_id, project_id=project_id, incident_id=incident_id
            )
            context.set_memory(memory)

            step["status"] = "completed" if result.status == "success" else "failed"
            step["result_summary"] = result.output_summary or result.error_message or ""
            step["artifact_count"] = len(result.artifact_refs)
            executed_plan = list(context.plan)
            executed_plan.append(step)
            context.plan = executed_plan

            context.set_mission(mission.model_dump())
            context.set_blackboard(blackboard.model_dump())
            context.set_hypotheses([h.model_dump() for h in blackboard.hypotheses])
            context.reasoning_summary = summary
            context.current_action = {
                "tool_name": tool_name,
                "label": step["label"],
                "status": "completed" if result.status == "success" else "failed",
                "target": incident_id or project_id,
                "step_index": mission.iteration,
            }
            loop._save_context(context)

            last_result = {
                "tool_name": tool_name,
                "status": result.status,
                "error_code": result.error_code,
                "error_message": result.error_message,
                "inputs": inputs,
            }

            mission.step()

            stop, _ = loop._check_messages(execution, context)
            if stop:
                break

        if mission.status == "running":
            top = blackboard.top_hypothesis()
            if top and top.confidence >= mission.confidence_threshold:
                verification = verify_conclusion(blackboard, mission)
                context.set_verification(verification.model_dump())
                if verification.passed:
                    finding = {
                        "statement": top.statement,
                        "confidence": top.confidence,
                        "evidence": blackboard.evidence,
                        "entity": blackboard.current_candidate,
                        "incident_id": incident_id,
                    }
                    context.set_findings(context.get_findings() + [finding])
                    blackboard.summary = (
                        f"Finding: {finding['statement']} (confidence {finding['confidence']:.2f})"
                    )
                    mission.complete("Investigation complete with verified finding.")
                else:
                    mission.complete(
                        f"Evidence insufficient: {verification.reason}", status="completed"
                    )
            else:
                mission.complete(
                    "Evidence exhausted without a high-confidence conclusion.", status="completed"
                )

        duration_ms = round((perf_counter() - started) * 1000, 2)
        successful = sum(1 for r in results if r.status == "success")
        failed = len(results) - successful

        if mission.status == "completed":
            final_type = "agent.completed"
            final_label = "Mission complete"
            final_status = "completed"
        else:
            final_type = "agent.failed"
            final_label = "Mission failed"
            final_status = "failed"

        result_summary = blackboard.summary or mission.stop_reason or f"Mission {mission.status}"

        sequence = _next_sequence(session, execution_id)
        store.emit(
            session,
            execution_id,
            sequence,
            final_type,
            label=final_label,
            payload={
                "duration_ms": duration_ms,
                "tools_run": len(results),
                "successful": successful,
                "failed": failed,
                "fallback_used": fallback_used,
                "result_summary": result_summary,
                "findings": context.get_findings(),
                "stop_reason": mission.stop_reason,
                "iterations": mission.iteration,
            },
        )

        context.status = final_status
        context.reasoning_summary = result_summary
        context.current_action = {}
        context.completed_at = datetime.now(timezone.utc)
        context.set_mission(mission.model_dump())
        context.set_blackboard(blackboard.model_dump())
        context.set_hypotheses([h.model_dump() for h in blackboard.hypotheses])
        loop._save_context(context)

        store.complete_execution(
            session,
            execution_id,
            final_status,
            result_summary=result_summary,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )

    except Exception as exc:
        logger.error("agent.adaptive_loop_error", execution_id=execution_id, error=str(exc))
        mission.complete(f"Orchestration error: {exc}", status="failed")
        context.status = "failed"
        context.reasoning_summary = f"Investigation failed: {exc}"
        context.current_action = {}
        context.completed_at = datetime.now(timezone.utc)
        context.set_mission(mission.model_dump())
        loop._save_context(context)
        store.complete_execution(
            session,
            execution_id,
            "failed",
            result_summary=f"Investigation failed: {exc}",
            error_code="orchestration_error",
            error_message=str(exc),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )

    return store.get_execution(session, execution_id) or execution


def _summarize_observation(observation: dict[str, Any]) -> str:
    parts = []
    if observation.get("project", {}).get("found"):
        parts.append(f"project {observation['project']['project_id']}")
    if observation.get("incident", {}).get("found"):
        inc = observation["incident"]
        title = inc.get("title", "")
        severity = inc.get("severity", "")
        parts.append(f"incident {inc['incident_id']} ({title}), severity {severity}")
    if observation.get("telemetry", {}).get("found"):
        tel = observation["telemetry"]
        parts.append(f"{tel['total_events']} telemetry events, {tel['attack_events']} attack")
    return "Observed: " + ", ".join(parts) if parts else "No prior environment state."


def _json_safe(value: Any) -> Any:
    from enum import Enum

    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _build_observation_from_result(tool_name: str, result: ToolResult) -> dict[str, Any]:
    return _json_safe(
        {
            "tool": tool_name,
            "status": result.status,
            "summary": result.output_summary or result.error_message,
            "output": result.output,
            "artifact_refs": [a.model_dump() for a in result.artifact_refs],
            "error_code": result.error_code,
        }
    )


def _update_blackboard_from_result(
    blackboard: Blackboard,
    tool_name: str,
    inputs: dict[str, Any],
    result: ToolResult,
    mission: Mission,
    observation: dict[str, Any],
    tool_call_id: str,
) -> None:
    entity_id = inputs.get("entity_id") or inputs.get("target_entity") or ""
    action_key = f"{tool_name}:{entity_id}" if entity_id else tool_name

    if result.status != "success":
        blackboard.add_failed_action(action_key, result.error_message)
        return

    blackboard.add_completed_action(action_key)

    for ref in result.artifact_refs:
        blackboard.add_evidence(ref.ref_id, ref.label, tool_name)

    summary = result.output_summary or ""
    if summary:
        evidence_ref = f"{tool_name}:{tool_call_id}"
        blackboard.add_evidence(evidence_ref, summary, tool_name)

    output = result.output or {}
    if tool_name == "observe_environment" or tool_name == "observe_project":
        if output.get("incident"):
            blackboard.current_incident = output["incident"].get("incident_id", "")
        if output.get("telemetry"):
            blackboard.add_fact("total_events", str(output["telemetry"].get("total_events", 0)))
            blackboard.add_fact("attack_events", str(output["telemetry"].get("attack_events", 0)))
            if output["telemetry"].get("sources"):
                blackboard.add_fact("top_source", str(output["telemetry"]["sources"][0]))
    elif tool_name == "detect_anomalies":
        blackboard.add_fact("detect_attempted", "true")
        candidates = output.get("candidates", [])
        if candidates:
            top = candidates[0]
            entity = top.get("entity_id") or top.get("host") or top.get("user")
            blackboard.current_candidate = entity or ""
            blackboard.next_best_action = "correlate"
            for c in candidates[:3]:
                entity_id = c.get("entity_id") or c.get("host") or c.get("user")
                if not entity_id:
                    continue
                h = blackboard.get_hypothesis(entity_id)
                if h is None:
                    h = Hypothesis(
                        id=entity_id,
                        statement=f"{entity_id} is involved in suspicious activity",
                        confidence=c.get("score", 0.5),
                        evidence_for=[tool_name],
                        next_test="correlate_entities",
                        entity_id=entity_id,
                    )
                    blackboard.add_hypothesis(h)
                else:
                    h.assess(c.get("score", 0.5), "testing")
                    h.add_evidence_for(tool_name)
    elif tool_name == "correlate_entities":
        entity = output.get("entity_id", "")
        related = output.get("related_entities", [])
        if related:
            h = blackboard.get_hypothesis(entity)
            if h:
                h.add_evidence_for(tool_name)
                h.assess(min(1.0, h.confidence + 0.1), "testing")
                h.next_test = "investigate_entity"
            blackboard.current_candidate = entity
            blackboard.next_best_action = "investigate"
    elif tool_name == "investigate_entity":
        entity = output.get("entity_id", "")
        risk = output.get("risk_score", 0.0)
        h = blackboard.get_hypothesis(entity)
        if h:
            h.assess(max(h.confidence, risk), "testing")
            h.add_evidence_for(tool_name)
            h.next_test = "trace_attack_path"
        blackboard.current_candidate = entity
    elif tool_name == "trace_attack_path":
        entity = output.get("entity_id", "")
        path = output.get("path", [])
        if path:
            h = blackboard.get_hypothesis(entity)
            if h:
                h.assess(min(1.0, h.confidence + 0.1), "testing")
                h.add_evidence_for(tool_name)
                h.next_test = "reconstruct_timeline"
    elif tool_name == "reconstruct_timeline":
        entity = output.get("entity_id", "")
        events = output.get("events", [])
        if events:
            h = blackboard.get_hypothesis(entity)
            if h:
                new_confidence = min(1.0, h.confidence + 0.05)
                h.assess(new_confidence, "supported")
                h.add_evidence_for(tool_name)
                h.next_test = (
                    "verify_conclusion" if new_confidence >= 0.75 else "get_telemetry"
                )
    elif tool_name == "test_hypothesis":
        entity = output.get("entity_id", "")
        confidence = output.get("confidence", 0.5)
        assessment = output.get("assessment", "weak")
        h = blackboard.get_hypothesis(entity)
        if h:
            h.assess(
                max(h.confidence, confidence), "testing" if assessment == "weak" else "supported"
            )
            h.add_evidence_for(tool_name)
            h.next_test = (
                "investigate_entity"
                if assessment == "weak" and confidence < 0.7
                else "verify_conclusion"
            )

    blackboard.add_fact("last_tool", tool_name)


def _update_hypotheses(
    blackboard: Blackboard, tool_name: str, result: ToolResult, mission: Mission
) -> None:
    if result.status != "success":
        return
    output = result.output or {}
    if output.get("assessment") == "benign" or output.get("benign"):
        entity = output.get("entity_id") or _extract_target_from_result(result)
        if entity:
            h = blackboard.get_hypothesis(entity)
            if h:
                h.assess(0.15, "rejected")
                h.add_evidence_against(tool_name)
                blackboard.add_fact(f"{entity}_assessment", "benign scanner or authorized activity")
