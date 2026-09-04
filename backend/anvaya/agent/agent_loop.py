"""Live, reasoning-aware agent execution loop."""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from sqlmodel import Session, select

from anvaya.agent.adaptive_loop import run_adaptive
from anvaya.agent.artifact_utils import infer_artifact_action, infer_artifact_types
from anvaya.agent.decision import DecisionEngine
from anvaya.agent.executor import LocalToolExecutor
from anvaya.agent.memory import MemoryStore
from anvaya.agent.messaging import MessageGenerator
from anvaya.agent.profiles import AgentProfile
from anvaya.agent.reasoning import ReasoningGenerator
from anvaya.agent.registry import ToolRegistry
from anvaya.agent.schemas import ToolResult
from anvaya.agent.world import WorldObserver
from anvaya.logging import get_logger
from anvaya.models.agent_context import ExecutionContext
from anvaya.models.execution import Execution, ExecutionEvent
from anvaya.models.incident import Incident
from anvaya.models.project import ARTIFACT_TYPES
from anvaya.routes import route_for_artifact_type

logger = get_logger("anvaya.agent.agent_loop")


def _build_artifact_steps(
    action: str, requested: list[str], project_id: str
) -> list[dict[str, Any]]:
    """Build one plan step per requested artifact type."""
    requested_types = (
        list(ARTIFACT_TYPES)
        if isinstance(requested, list) and "all" in requested
        else requested
    )

    plan: list[dict[str, Any]] = []
    for atype in requested_types:
        atype_label = _artifact_label(action, atype)
        step: dict[str, Any] = {
            "tool": "manage_artifacts",
            "inputs": {
                "project_id": project_id,
                "dataset_id": "",
                "action": action,
                "requested_artifacts": [atype],
            },
            "label": atype_label,
            "progress": f"{atype_label}...",
            "completed": f"{atype_label} completed",
            "optional": False,
            "stop_on_failure": True,
        }
        if len(requested_types) > 1:
            step["target_artifact_type"] = atype
            step["route"] = route_for_artifact_type(atype) or atype
        plan.append(step)
    return plan




class AgentLoop:
    """Run an execution plan while emitting reasoning and observation events.

    ``AgentLoop`` is the heart of the live agent: it maintains an
    ``ExecutionContext`` (plan, observations, messages, current action) and
    emits the new ``agent.reasoning_*``, ``agent.decision_started``,
    ``agent.tool_requested``, and ``agent.observation_created`` events while
    preserving the existing tool/artifact/agent message stream.
    """

    def __init__(self, orchestrator: Any) -> None:
        self.orchestrator = orchestrator
        self.session: Session = orchestrator.session
        self.store = orchestrator.store
        self.registry: ToolRegistry = orchestrator.registry
        self.executor: LocalToolExecutor = orchestrator.executor
        self.reasoning_generator = ReasoningGenerator()
        self._reasoning_counter = 0


    def run_investigation(
        self,
        execution: Execution,
        incident_id: str,
        plan: list[dict[str, Any]],
        profile: AgentProfile,
        active_model: Any,
        messenger: MessageGenerator,
        objective: str = "",
        project_id: str = "",
    ) -> Execution:
        """Run the full investigation plan for an incident."""
        started = perf_counter()
        execution_id = execution.execution_id
        objective = objective or execution.objective

        self._init_reasoning(active_model)

        context = self._get_or_create_context(
            execution_id=execution_id,
            objective=objective,
            incident_id=incident_id,
            project_id=project_id,
            plan=self._normalize_plan(plan),
            model=active_model.display_name if active_model else profile.model_name,
            provider=active_model.provider if active_model else "anvaya",
            status="running",
        )

        if context.status == "cancelled":
            self._emit_execution_interrupted(execution_id, "cancelled")
            context.current_action = {}
            context.completed_at = datetime.now(timezone.utc)
            self._save_context(context)
            self.store.complete_execution(
                self.session,
                execution_id,
                "cancelled",
                result_summary="Execution cancelled before it started",
                error_code="cancelled",
                error_message="Execution cancelled before it started",
            )
            return execution

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.message",
            label="Investigation started",
            payload={
                "message": messenger.start(objective or execution.objective, incident_id),
                "profile": profile.id,
                "profile_display_name": profile.display_name,
                "incident_id": incident_id,
            },
        )

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.plan_created",
            label="Plan created",
            payload=self._plan_payload(context, profile=profile),
        )

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.message",
            label="Plan summary",
            payload={
                "message": messenger.plan_created([s["tool"] for s in context.plan]),
                "profile": profile.id,
            },
        )

        results: list[ToolResult] = []
        fallback_used = False
        fallback_reason = ""

        try:
            step_index = 0
            while step_index < len(context.plan):
                self.session.refresh(context)

                if context.status == "cancelled":
                    return execution

                stop, _ = self._check_messages(execution, context)
                if stop:
                    return execution

                if step_index >= len(context.plan):
                    break
                step = context.plan[step_index]

                if step.get("status") == "skipped":
                    context.current_action = {
                        "tool_name": step["tool"],
                        "label": step.get("label", step["tool"]),
                        "status": "skipped",
                        "target": step.get("target_artifact_type", incident_id),
                        "step_index": step_index,
                    }
                    self._save_context(context)
                    step_index += 1
                    continue

                step["status"] = "running"
                step["step_index"] = step_index
                context.current_action = {
                    "tool_name": step["tool"],
                    "label": step.get("label", step["tool"]),
                    "status": "running",
                    "target": step.get("target_artifact_type", incident_id),
                    "step_index": step_index,
                }
                context.plan = list(context.plan)
                self._save_context(context)

                previous_result = results[-1] if results else None

                self._emit_reasoning(context, step, previous_result, execution_id)

                self._emit_decision_started(execution_id, step, step_index)
                self._emit_tool_requested(execution_id, step, step_index)

                result = self._execute_tool_step(
                    execution_id, step, step_index, profile, messenger
                )
                results.append(result)

                if result.fallback_used:
                    fallback_used = True
                    if not fallback_reason:
                        fallback_reason = f"{step['tool']}: {result.fallback_reason}"

                observation = _build_observation(step["tool"], result, step_index)
                context.observations = list(context.observations) + [observation]

                observation_sequence = self._next_sequence(execution_id)
                self.store.emit(
                    self.session,
                    execution_id,
                    observation_sequence,
                    "agent.observation_created",
                    label=f"Observation from {step['tool']}",
                    payload=observation,
                )

                step["status"] = "completed" if result.status == "success" else "failed"
                step["result_summary"] = result.output_summary or result.error_message or ""
                step["artifact_count"] = len(result.artifact_refs)
                context.reasoning_summary = self.reasoning_generator.generate(
                    context, step, result
                )
                context.plan = list(context.plan)
                self._save_context(context)

                stop, _ = self._check_messages(execution, context)
                if stop:
                    return execution

                if result.status != "success" and not step.get("optional"):
                    if step.get("stop_on_failure", False):
                        self._fail_execution(
                            execution,
                            context,
                            result.error_code or "step_failed",
                            result.error_message or f"{step['tool']} failed",
                            fallback_used,
                            fallback_reason,
                        )
                        return execution

                step_index += 1

            incident_row = self.session.exec(
                select(Incident).where(Incident.incident_id == incident_id)
            ).first()
            if incident_row:
                sequence = self._next_sequence(execution_id)
                self.store.emit(
                    self.session,
                    execution_id,
                    sequence,
                    "incident.updated",
                    label="Incident updated",
                    payload={
                        "incident_id": incident_id,
                        "status": incident_row.status.value,
                        "self_correction_status": incident_row.self_correction_status.value,
                    },
                )

            result_summary = _result_summary(results)
            duration_ms = round((perf_counter() - started) * 1000, 2)
            successful = sum(1 for r in results if r.status == "success")
            failed = sum(1 for r in results if r.status == "failure")

            sequence = self._next_sequence(execution_id)
            self.store.emit(
                self.session,
                execution_id,
                sequence,
                "agent.message",
                label="Investigation complete",
                payload={
                    "message": messenger.complete(successful, failed),
                    "profile": profile.id,
                    "summary_items": _summary_items(results),
                },
            )

            sequence = self._next_sequence(execution_id)
            self.store.emit(
                self.session,
                execution_id,
                sequence,
                "agent.completed",
                label="Investigation complete",
                payload={
                    "duration_ms": duration_ms,
                    "tools_run": len(results),
                    "successful": successful,
                    "failed": failed,
                    "fallback_used": fallback_used,
                    "result_summary": result_summary,
                },
            )

            context.status = "completed"
            context.reasoning_summary = result_summary
            context.current_action = {}
            context.completed_at = datetime.now(timezone.utc)
            self._save_context(context)

            self.store.complete_execution(
                self.session,
                execution_id,
                "completed",
                result_summary=result_summary,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
            )

        except Exception as exc:
            logger.error("agent.loop_error", execution_id=execution_id, error=str(exc))
            self._fail_execution(
                execution,
                context,
                "orchestration_error",
                str(exc),
                fallback_used,
                fallback_reason,
            )

        return execution

    def run_adaptive(
        self,
        execution: Execution,
        incident_id: str,
        profile: AgentProfile,
        active_model: Any,
        messenger: MessageGenerator,
        objective: str,
        project_id: str,
        world: WorldObserver,
        decision: DecisionEngine,
        memory: MemoryStore,
        initial_plan: list[dict[str, Any]],
    ) -> Execution:
        """Run the adaptive observe-decide-act loop for an execution."""
        return run_adaptive(
            loop=self,
            execution=execution,
            incident_id=incident_id,
            profile=profile,
            active_model=active_model,
            messenger=messenger,
            objective=objective,
            project_id=project_id,
            world=world,
            decision_engine=decision,
            memory_store=memory,
            initial_plan=initial_plan,
        )

    def run_project_plan(
        self,
        execution: Execution,
        project_id: str,
        objective: str,
        profile: AgentProfile | None,
        action: str,
        requested: list[str],
        active_model: Any | None = None,
    ) -> Execution:
        """Run a project-scoped artifact plan."""
        started = perf_counter()
        execution_id = execution.execution_id
        objective = objective or execution.objective
        profile = profile or AgentProfile(
            id="default",
            name="Agent",
            display_name="Agent",
            purpose="",
            description="",
            system_instruction="",
            model_provider="anvaya",
            model_name="anvaya-local",
            expertise=[],
            preferred_tools=[],
            fallback_tools=[],
        )
        messenger = MessageGenerator(profile)

        final_label = (
            "Artifacts deleted"
            if action == "delete"
            else ("Artifacts regenerated" if action == "regenerate" else "Artifacts generated")
        )

        plan = _build_artifact_steps(action, requested, project_id)

        self._init_reasoning(active_model)

        context = self._get_or_create_context(
            execution_id=execution_id,
            objective=objective,
            project_id=project_id,
            plan=self._normalize_plan(plan),
            model=active_model.display_name if active_model else profile.model_name,
            provider=(
                active_model.provider
                if active_model
                else (profile.model_provider or "anvaya")
            ),
            status="running",
        )

        if context.status == "cancelled":
            self._emit_execution_interrupted(execution_id, "cancelled")
            self.store.complete_execution(
                self.session,
                execution_id,
                "cancelled",
                result_summary="Execution cancelled before it started",
                error_code="cancelled",
                error_message="Execution cancelled before it started",
            )
            return execution

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.message",
            label="Project plan started",
            payload={
                "message": f"Generating artifacts for project {project_id} from dataset.",
                "project_id": project_id,
                "objective": objective,
            },
        )

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.plan_created",
            label="Plan created",
            payload=self._plan_payload(
                context,
                profile=profile,
                project_id=project_id,
                action=action,
                requested_artifacts=requested,
            ),
        )

        results: list[ToolResult] = []
        fallback_used = False
        fallback_reason = ""

        try:
            step_index = 0
            while step_index < len(context.plan):
                self.session.refresh(context)

                if context.status == "cancelled":
                    self._emit_execution_interrupted(execution_id, "cancelled")
                    self.store.complete_execution(
                        self.session,
                        execution_id,
                        "cancelled",
                        result_summary="Execution cancelled",
                        error_code="cancelled",
                        error_message="Execution cancelled",
                    )
                    context.current_action = {}
                    context.completed_at = datetime.now(timezone.utc)
                    self._save_context(context)
                    return execution

                if step_index >= len(context.plan):
                    break
                step = context.plan[step_index]

                if step.get("status") == "skipped":
                    context.current_action = {
                        "tool_name": step["tool"],
                        "label": step.get("label", step["tool"]),
                        "status": "skipped",
                        "target": step.get("target_artifact_type", project_id),
                        "step_index": step_index,
                    }
                    self._save_context(context)
                    step_index += 1
                    continue

                step["status"] = "running"
                step["step_index"] = step_index
                context.current_action = {
                    "tool_name": step["tool"],
                    "label": step.get("label", step["tool"]),
                    "status": "running",
                    "target": step.get("target_artifact_type", project_id),
                    "step_index": step_index,
                }
                context.plan = list(context.plan)
                self._save_context(context)

                previous_result = results[-1] if results else None

                self._emit_reasoning(context, step, previous_result, execution_id)
                self._emit_decision_started(execution_id, step, step_index)
                self._emit_tool_requested(execution_id, step, step_index)

                result = self._execute_tool_step(
                    execution_id, step, step_index, profile, messenger
                )
                results.append(result)

                if result.fallback_used:
                    fallback_used = True
                    if not fallback_reason:
                        fallback_reason = f"{step['tool']}: {result.fallback_reason}"

                observation = _build_observation(step["tool"], result, step_index)
                context.observations = list(context.observations) + [observation]

                observation_sequence = self._next_sequence(execution_id)
                self.store.emit(
                    self.session,
                    execution_id,
                    observation_sequence,
                    "agent.observation_created",
                    label=f"Observation from {step['tool']}",
                    payload=observation,
                )

                step["status"] = "completed" if result.status == "success" else "failed"
                step["result_summary"] = result.output_summary or result.error_message or ""
                step["artifact_count"] = len(result.artifact_refs)
                context.reasoning_summary = self.reasoning_generator.generate(context, step, result)
                context.plan = list(context.plan)
                context.current_action = {
                    "tool_name": step["tool"],
                    "label": step.get("label", step["tool"]),
                    "status": step["status"],
                    "target": step.get("target_artifact_type", project_id),
                    "step_index": step_index,
                }
                self._save_context(context)

                if result.status != "success" and not step.get("optional"):
                    if step.get("stop_on_failure", True):
                        break

                step_index += 1

            duration_ms = round((perf_counter() - started) * 1000, 2)
            failed_result = next((r for r in results if r.status == "failure"), None)

            if failed_result:
                status = "failed"
                final_type = "agent.failed"
                error_code = failed_result.error_code or ""
                error_message = failed_result.error_message or "Artifact management failed"
                result_summary = error_message
                final_label = "Project artifact generation failed"
            else:
                status = "completed"
                final_type = "agent.completed"
                error_code = ""
                error_message = ""
                result_summary = _build_project_result_summary(action, results)

            sequence = self._next_sequence(execution_id)
            self.store.emit(
                self.session,
                execution_id,
                sequence,
                "agent.message",
                label=final_label,
                payload={
                    "message": result_summary,
                    "project_id": project_id,
                },
            )

            self.store.complete_execution(
                self.session,
                execution_id,
                status,
                result_summary=result_summary,
                error_code=error_code,
                error_message=error_message,
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
            )

            sequence = self._next_sequence(execution_id)
            self.store.emit(
                self.session,
                execution_id,
                sequence,
                final_type,
                label=final_label,
                payload={
                    "status": status,
                    "error_message": error_message,
                    "duration_ms": duration_ms,
                },
            )

            context.status = status
            context.current_action = {}
            context.completed_at = datetime.now(timezone.utc)
            self._save_context(context)

        except Exception as exc:
            logger.error("agent.loop_error", execution_id=execution_id, error=str(exc))
            self._fail_execution(
                execution,
                context,
                "orchestration_error",
                str(exc),
                fallback_used,
                fallback_reason,
                label="Project artifact generation failed",
            )

        execution = self.store.get_execution(self.session, execution_id)
        return execution  # type: ignore[return-value]


    def _get_or_create_context(self, **fields: Any) -> ExecutionContext:
        execution_id = fields["execution_id"]
        context = self.session.exec(
            select(ExecutionContext).where(ExecutionContext.execution_id == execution_id)
        ).first()
        if context is not None:
            for key, value in fields.items():
                if key == "execution_id":
                    continue
                if key == "status" and context.status in ("cancelled", "completed", "failed"):
                    continue
                if hasattr(context, key):
                    setattr(context, key, value)
            context.touch()
            self._save_context(context)
            return context

        context = ExecutionContext(**fields)
        self.session.add(context)
        self.session.commit()
        self.session.refresh(context)
        return context

    def _save_context(self, context: ExecutionContext) -> None:
        context.touch()
        self.session.add(context)
        self.session.commit()
        self.session.refresh(context)

    def _init_reasoning(self, active_model: Any | None) -> None:
        """Wire the reasoning generator to a model provider when one is active."""
        if active_model is None:
            self.reasoning_generator = ReasoningGenerator()
            return

        from anvaya.llm.providers import get_model_provider_for_config

        provider = get_model_provider_for_config(active_model)
        stream = bool(
            provider
            and not getattr(provider, "name", "") == "anvaya-local"
            and getattr(provider, "supports_capability", lambda c: False)("streaming")
        )
        self.reasoning_generator = ReasoningGenerator(
            model_provider=provider if stream else None,
            stream=stream,
        )

    def _normalize_plan(self, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for step in plan:
            normalized.append(
                {
                    "tool": step["tool"],
                    "inputs": step.get("inputs", {}),
                    "label": step.get("label", step["tool"]),
                    "status": step.get("status", "pending"),
                    "optional": step.get("optional", False),
                    "stop_on_failure": step.get("stop_on_failure", False),
                    "result_summary": step.get("result_summary", ""),
                    "artifact_count": step.get("artifact_count", 0),
                    "progress": step.get("progress", "Processing..."),
                    "completed": step.get("completed", f"{step['tool']} completed"),
                    "step_index": step.get("step_index", len(normalized)),
                }
            )
            for key in ("target_artifact_type", "route"):
                if key in step:
                    normalized[-1][key] = step[key]
        return normalized

    def _plan_payload(
        self,
        context: ExecutionContext,
        profile: AgentProfile,
        **extra: Any,
    ) -> dict[str, Any]:
        """Build the ``agent.plan_created`` payload."""
        payload: dict[str, Any] = {
            "objective": context.objective,
            "steps": [s["tool"] for s in context.plan],
            "plan": context.plan,
            "can_update": True,
            "provider": context.provider or "anvaya",
            "profile": profile.id,
            "model": context.model or profile.model_name,
        }
        if context.incident_id:
            payload["incident_id"] = context.incident_id
        if context.project_id:
            payload["project_id"] = context.project_id
        payload.update(extra)
        return payload

    def _next_sequence(self, execution_id: str) -> int:
        last = self.session.exec(
            select(ExecutionEvent)
            .where(ExecutionEvent.execution_id == execution_id)
            .order_by(ExecutionEvent.sequence.desc())
        ).first()
        return (last.sequence + 1) if last else 1


    def _emit_reasoning(
        self,
        context: ExecutionContext,
        step: dict[str, Any],
        previous_result: ToolResult | None,
        execution_id: str,
    ) -> None:
        self._reasoning_counter += 1
        reasoning_id = f"reason-{execution_id}-{self._reasoning_counter}"

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.reasoning_started",
            label="Reasoning started",
            payload={"reasoning_id": reasoning_id},
        )

        full_text = ""
        for delta in self.reasoning_generator.stream(context, step, previous_result):
            full_text += delta
            sequence = self._next_sequence(execution_id)
            self.store.emit(
                self.session,
                execution_id,
                sequence,
                "agent.reasoning_delta",
                label="Reasoning delta",
                payload={"reasoning_id": reasoning_id, "delta": delta},
            )

        summary = self.reasoning_generator.generate(context, step, previous_result)
        source = "model_summary" if self.reasoning_generator.uses_model else "execution_summary"

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.reasoning_completed",
            label="Reasoning completed",
            payload={"reasoning_id": reasoning_id, "summary": summary, "source": source},
        )

        context.reasoning_summary = summary
        self._save_context(context)

    def _emit_decision_started(
        self, execution_id: str, step: dict[str, Any], step_index: int
    ) -> None:
        payload: dict[str, Any] = {
            "step_index": step_index,
            "tool_name": step["tool"],
            "inputs_safe": _safe_payload(step.get("inputs", {})),
        }
        if step.get("target_artifact_type"):
            payload["target_artifact_type"] = step["target_artifact_type"]
            payload["route"] = step.get("route") or step["target_artifact_type"]

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.decision_started",
            label=f"Deciding {step['tool']}",
            payload=payload,
        )

    def _emit_tool_requested(
        self, execution_id: str, step: dict[str, Any], step_index: int
    ) -> None:
        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.tool_requested",
            label=f"Requesting {step['tool']}",
            payload={
                "tool_name": step["tool"],
                "label": step.get("label", step["tool"]),
                "step_index": step_index,
            },
        )


    def _execute_tool_step(
        self,
        execution_id: str,
        step: dict[str, Any],
        step_index: int,
        profile: AgentProfile,
        messenger: MessageGenerator,
    ) -> ToolResult:
        tool_name = step["tool"]
        inputs = step.get("inputs", {})

        if "requested_artifacts" in inputs:
            requested = inputs["requested_artifacts"]
            if isinstance(requested, list) and "all" in requested:
                inputs = {**inputs, "requested_artifacts": list(ARTIFACT_TYPES)}

        tool = self.registry.get(tool_name)
        if not tool:
            self._emit_tool_failed(
                execution_id,
                tool_name,
                inputs,
                "tool_not_found",
                f"Tool {tool_name} not registered",
            )
            return ToolResult(
                tool_name=tool_name,
                status="failure",
                error_code="tool_not_found",
                error_message=f"Tool {tool_name} not registered",
            )

        valid, errors = self.registry.validate_inputs(tool_name, inputs)
        if not valid:
            self._emit_tool_failed(
                execution_id,
                tool_name,
                inputs,
                "validation_error",
                "; ".join(errors),
            )
            return ToolResult(
                tool_name=tool_name,
                status="failure",
                error_code="validation_error",
                error_message="; ".join(errors),
            )

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.message",
            label=f"Before {tool_name}",
            payload={
                "message": messenger.before_tool(tool_name, {}),
                "profile": profile.id,
            },
        )

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "tool.started",
            tool_call_id=f"{execution_id}-{tool_name}-{sequence}",
            tool_name=tool_name,
            provider=tool.provider,
            status="running",
            label=step.get("label", f"Running {tool_name}"),
            payload={"inputs": _safe_payload(inputs)},
        )

        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "tool.progress",
            tool_call_id=f"{execution_id}-{tool_name}-{sequence - 1}",
            tool_name=tool_name,
            provider=tool.provider,
            status="running",
            label=step.get("progress", "Processing..."),
        )

        tool_call_id = f"{execution_id}-{tool_name}-{sequence - 1}"
        result = self.executor.execute(
            tool_name, inputs, tool_call_id=tool_call_id, execution_id=execution_id
        )

        if result.fallback_used and result.fallback_reason:
            sequence = self._next_sequence(execution_id)
            self.store.emit(
                self.session,
                execution_id,
                sequence,
                "agent.message",
                label="Provider fallback",
                payload={
                    "message": messenger.fallback(tool.provider, result.provider),
                    "profile": profile.id,
                    "provider": result.provider,
                    "fallback_reason": result.fallback_reason,
                },
            )

        for artifact in result.artifact_refs:
            sequence = self._next_sequence(execution_id)
            self.store.emit(
                self.session,
                execution_id,
                sequence,
                "artifact.created",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                provider=result.provider,
                status="success",
                label=artifact.label,
                artifact_ref=artifact.ref_id,
                artifact_type=artifact.ref_type,
                payload={"link": artifact.link, "label": artifact.label},
            )

        sequence = self._next_sequence(execution_id)
        if result.status == "success":
            self.store.emit(
                self.session,
                execution_id,
                sequence,
                "tool.completed",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                provider=result.provider,
                status="completed",
                label=step.get("completed", f"{tool_name} completed"),
                payload={
                    "duration_ms": result.duration_ms,
                    "output_summary": result.output_summary,
                    "artifact_count": len(result.artifact_refs),
                    "fallback_used": result.fallback_used,
                    "fallback_reason": result.fallback_reason,
                },
            )
            if result.output_summary:
                sequence = self._next_sequence(execution_id)
                self.store.emit(
                    self.session,
                    execution_id,
                    sequence,
                    "agent.message",
                    label=f"After {tool_name}",
                    payload={
                        "message": messenger.after_tool(
                            tool_name,
                            result.output_summary,
                            "success",
                            len(result.artifact_refs),
                        ),
                        "profile": profile.id,
                    },
                )
        else:
            self.store.emit(
                self.session,
                execution_id,
                sequence,
                "tool.failed",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                provider=result.provider,
                status="failed",
                label=f"{tool_name} failed",
                error_code=result.error_code,
                error_message=result.error_message,
                payload={"output_summary": result.output_summary},
            )
            sequence = self._next_sequence(execution_id)
            self.store.emit(
                self.session,
                execution_id,
                sequence,
                "agent.message",
                label="Tool failure",
                payload={
                    "message": messenger.after_tool(
                        tool_name, result.error_message, "failure", 0
                    ),
                    "profile": profile.id,
                },
            )

        return result

    def _emit_tool_failed(
        self,
        execution_id: str,
        tool_name: str,
        inputs: dict[str, Any],
        error_code: str,
        error_message: str,
    ) -> None:
        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "tool.failed",
            tool_name=tool_name,
            status="failed",
            label=f"{tool_name} failed",
            error_code=error_code,
            error_message=error_message,
            payload={"inputs": _safe_payload(inputs)},
        )


    def _check_messages(
        self, execution: Execution, context: ExecutionContext
    ) -> tuple[bool, str]:
        """Process unprocessed user messages and return (should_stop, reason)."""
        self.session.refresh(context)

        if context.status == "cancelled":
            return True, "cancelled"

        messages = list(context.messages)
        updated = False
        for i, message in enumerate(messages):
            if message.get("processed"):
                continue

            content = str(message.get("content", ""))

            if _is_cancellation_request(content, context):
                message["processed"] = True
                messages[i] = message
                updated = True

                reason = "User cancelled execution"
                context.status = "cancelled"
                context.current_action = {}
                context.messages = messages
                context.completed_at = datetime.now(timezone.utc)
                self._save_context(context)

                self._emit_execution_interrupted(execution.execution_id, reason)
                self.store.complete_execution(
                    self.session,
                    execution.execution_id,
                    "cancelled",
                    result_summary=reason,
                    error_code="cancelled",
                    error_message=reason,
                )
                return True, "cancelled"

            if _is_plan_update_request(content, context):
                updated_plan, plan_reason = _apply_plan_update(content, context)
                if plan_reason:
                    message["processed"] = True
                    messages[i] = message
                    context.messages = messages
                    context.plan = plan_reason["plan"]
                    self._save_context(context)
                    self._emit_plan_updated(execution.execution_id, plan_reason)
                    updated = True

        if updated and not context.messages == messages:
            context.messages = messages
            self._save_context(context)

        return False, ""

    def _emit_execution_interrupted(self, execution_id: str, reason: str) -> None:
        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.execution_interrupted",
            label="Execution interrupted",
            payload={"reason": reason, "by": "user"},
        )

    def _emit_plan_updated(self, execution_id: str, update: dict[str, Any]) -> None:
        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.plan_updated",
            label="Plan updated",
            payload=update,
        )


    def _fail_execution(
        self,
        execution: Execution,
        context: ExecutionContext,
        error_code: str,
        error_message: str,
        fallback_used: bool,
        fallback_reason: str,
        label: str = "Investigation failed",
    ) -> None:
        execution_id = execution.execution_id
        sequence = self._next_sequence(execution_id)
        self.store.emit(
            self.session,
            execution_id,
            sequence,
            "agent.failed",
            label=label,
            error_code=error_code,
            error_message=error_message,
            payload={"fallback_used": fallback_used, "fallback_reason": fallback_reason},
        )

        context.status = "failed"
        context.reasoning_summary = f"{label}: {error_message}"
        context.current_action = {}
        context.completed_at = datetime.now(timezone.utc)
        self._save_context(context)

        self.store.complete_execution(
            self.session,
            execution_id,
            "failed",
            result_summary=f"{label}: {error_message}",
            error_code=error_code,
            error_message=error_message,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )




def _build_observation(tool_name: str, result: ToolResult, step_index: int) -> dict[str, Any]:
    """Build a user-safe observation from a tool result."""
    facts: dict[str, Any] = {"status": result.status}
    output = result.output or {}

    if result.status == "success":
        if tool_name == "get_telemetry":
            facts["total_events"] = output.get("total_events")
            facts["attack_events"] = output.get("attack_events")
        elif tool_name == "run_blastscope":
            facts["total_reachable"] = output.get("total_reachable")
            facts["impact_score"] = output.get("impact_score")
        elif tool_name == "validate_rule":
            facts["f1_score"] = output.get("f1_score")
            facts["tp"] = output.get("tp")
            facts["fp"] = output.get("fp")
        elif tool_name == "run_replay":
            facts["post_patch_detected"] = output.get("post_patch_detected")
            facts["replay_id"] = output.get("replay_id")
        elif tool_name == "run_what_if":
            facts["score_delta"] = output.get("score_delta")
        elif tool_name == "build_or_update_ecosystem":
            ecosystem = output.get("ecosystem", {})
            facts["node_count"] = len(ecosystem.get("nodes", []))
            facts["health"] = ecosystem.get("health")
        elif tool_name == "run_reachability":
            facts["asset_count"] = len(output.get("items", []))
        elif tool_name == "run_segment_analysis":
            facts["segment_count"] = len(output.get("items", []))
        elif tool_name == "run_orbit_analysis":
            facts["risk_score"] = output.get("risk_score")
            facts["blast_radius_score"] = output.get("blast_radius_score")
        elif tool_name == "get_incident":
            facts["incident_id"] = output.get("incident_id")
        elif tool_name == "verify_audit_chain":
            facts["valid"] = output.get("valid")
            facts["record_count"] = output.get("record_count")
        elif tool_name == "manage_artifacts" or tool_name == "generate_artifacts":
            facts["created"] = output.get("created", {})

        for key, value in output.items():
            if key in facts:
                continue
            if isinstance(value, (int, float, bool, str)):
                facts[key] = value
            elif isinstance(value, list):
                facts[f"{key}_count"] = len(value)

        facts["artifact_count"] = len(result.artifact_refs)
        facts["fallback_used"] = result.fallback_used
    else:
        facts["error_code"] = result.error_code

    facts = {k: v for k, v in facts.items() if v is not None}

    return {
        "summary": result.output_summary or result.error_message or f"{tool_name} finished",
        "facts": facts,
        "source": tool_name,
        "step_index": step_index,
    }




_CANCELLATION_KEYWORDS = ("cancel", "stop", "abort", "quit")


def _is_cancellation_request(content: str, context: ExecutionContext) -> bool:
    content_lower = content.lower().strip()

    if content_lower.startswith("skip ") and _extract_tool_mentions(content_lower, context):
        return False

    return any(k in content_lower for k in _CANCELLATION_KEYWORDS)


def _is_plan_update_request(content: str, context: ExecutionContext) -> bool:
    content_lower = content.lower().strip()
    return (
        content_lower.startswith("only ")
        or content_lower.startswith("skip ")
        or _is_project_artifact_request(content_lower, context)
    )


def _is_project_artifact_request(content_lower: str, context: ExecutionContext) -> bool:
    if not context.project_id and not any(
        s.get("tool") == "manage_artifacts" for s in context.plan
    ):
        return False
    artifact_keywords = (
        "ecosystem",
        "orbits",
        "segments",
        "reach",
        "arena",
        "trophy",
        "replay",
        "arbor",
        "impacts",
        "incidents",
        "ledger",
    )
    action_keywords = ("regenerate", "generate", "delete", "only")
    return any(a in content_lower for a in action_keywords) and any(
        a in content_lower for a in artifact_keywords
    )


def _apply_plan_update(
    content: str, context: ExecutionContext
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    """Return (updated_plan or None, payload or None) for ``agent.plan_updated``."""
    content_lower = content.lower().strip()

    if context.project_id or any(s.get("tool") == "manage_artifacts" for s in context.plan):
        return _apply_project_plan_update(content, context)

    mentioned = _extract_tool_mentions(content_lower, context)
    if not mentioned:
        return None, None

    updated = [dict(s) for s in context.plan]
    reason = ""

    if content_lower.startswith("only "):
        keep = set(mentioned)
        if updated:
            keep.add(updated[0]["tool"])
        for step in updated:
            if step["tool"] not in keep:
                step["status"] = "skipped"
        reason = f"Replaying after user request: focus on {', '.join(mentioned)}."

    elif content_lower.startswith("skip "):
        for step in updated:
            if step["tool"] in mentioned:
                step["status"] = "skipped"
        reason = f"Skipped {', '.join(mentioned)} based on user request."

    if reason:
        return updated, {"plan": updated, "reason": reason}
    return None, None


def _apply_project_plan_update(
    content: str, context: ExecutionContext
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    updated = [dict(s) for s in context.plan]

    manage_idx = next(
        (i for i, s in enumerate(updated) if s.get("tool") == "manage_artifacts"), None
    )
    if manage_idx is None:
        return None, None

    step = updated[manage_idx]
    inputs = dict(step.get("inputs", {}))

    inputs["action"] = infer_artifact_action(content)

    requested = infer_artifact_types(content)
    if requested:
        if "all" in requested:
            requested = list(ARTIFACT_TYPES)
        inputs["requested_artifacts"] = requested

    step["inputs"] = inputs
    label_map = {
        "delete": "Deleting artifacts",
        "regenerate": "Regenerating artifacts",
    }
    step["label"] = label_map.get(inputs["action"], "Generating artifacts")
    step["progress"] = f"{step['label']}..."
    step["completed"] = f"{step['label']} completed"

    requested_label = ", ".join(requested) if requested else "all"
    reason = (
        f"Updated artifact plan: {inputs.get('action', 'generate')} "
        f"{requested_label} artifacts."
    )
    return updated, {"plan": updated, "reason": reason}


def _extract_tool_mentions(content_lower: str, context: ExecutionContext) -> set[str]:
    mentioned: set[str] = set()
    plan_tools = {s["tool"] for s in context.plan}
    for tool in plan_tools:
        if tool.replace("_", " ") in content_lower or tool in content_lower:
            mentioned.add(tool)
    return mentioned




def _safe_payload(inputs: dict[str, Any]) -> dict[str, Any]:
    """Return a safe, display-friendly copy of tool inputs."""

    def _safe_value(v: Any) -> Any:
        if isinstance(v, (str, int, float, bool)):
            return v
        if isinstance(v, dict):
            return {sk: _safe_value(sv) for sk, sv in v.items()}
        if isinstance(v, list):
            return [_safe_value(item) for item in v]
        return str(v)[:120]

    return {k: _safe_value(v) for k, v in inputs.items()}


def _result_summary(results: list[ToolResult]) -> str:
    total = len(results)
    success = sum(1 for r in results if r.status == "success")
    failed = total - success
    artifacts = sum(len(r.artifact_refs) for r in results)
    fallback = any(r.fallback_used for r in results)
    parts = [f"Ran {total} tools: {success} succeeded, {failed} failed, {artifacts} artifacts."]
    if fallback:
        parts.append("External fallback used.")
    return " ".join(parts)


def _summary_items(results: list[ToolResult]) -> list[dict[str, Any]]:
    return [{"tool": r.tool_name, "status": r.status, "summary": r.output_summary} for r in results]


def _artifact_label(action: str, artifact_type: str) -> str:
    """Return a user-safe step label for a single artifact action."""
    action_label = {
        "delete": "Deleting",
        "regenerate": "Regenerating",
    }.get(action, "Generating")
    return f"{action_label} {artifact_type.title()}"


def _build_project_result_summary(action: str, results: list[ToolResult]) -> str:
    """Build a user-safe final summary for a project artifact plan."""
    if not results:
        return "No artifacts were processed"

    if len(results) == 1:
        return (
            results[0].output_summary
            or results[0].error_message
            or "Artifact management complete"
        )

    if action == "delete":
        verb = "Deleted"
    elif action == "regenerate":
        verb = "Regenerated"
    else:
        verb = "Generated"

    types: list[str] = []
    for r in results:
        if r.status == "success" and r.output:
            created = r.output.get("created")
            if isinstance(created, dict):
                types.extend(created.keys())
            deleted_types = r.output.get("types")
            if isinstance(deleted_types, list):
                types.extend(deleted_types)

    if not types:
        types = [r.tool_name for r in results if r.status == "success"]

    dataset_name = ""
    for r in results:
        if r.output_summary and " from " in r.output_summary:
            dataset_name = r.output_summary.split(" from ")[-1]
            break

    if dataset_name:
        return f"{verb} {len(types)} artifact types ({', '.join(types)}) from {dataset_name}"
    return f"{verb} {len(types)} artifact types ({', '.join(types)})"
