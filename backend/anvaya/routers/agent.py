"""Agent API router for real-time tool execution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from anvaya.agent import (
    AgentOrchestrator,
    ChatEngine,
    all_provider_status,
    default_models,
    default_profiles,
    default_subagent_profiles,
    default_tool_registry,
    get_model,
    get_profile,
    get_subagent_profile,
    subagent_spawner,
)
from anvaya.agent.adapters import TavilyAdapter
from anvaya.agent.events import event_store
from anvaya.data import DataFactory
from anvaya.db import get_session
from anvaya.ml.alertness import AlertnessEngine
from anvaya.models.agent_context import ExecutionContext
from anvaya.models.execution import Execution
from anvaya.models.incident import Incident
from anvaya.models.telemetry import TelemetryEvent
from anvaya.simulator.generator import TelemetryGenerator
from anvaya.simulator.scenarios import get_attack_scenarios
from anvaya.whatif import WhatIfEngine

router = APIRouter()


@router.post("/agent/execute")
def execute_agent(
    data: dict[str, Any],
    background: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> dict:
    """Start an agent execution for the given objective.

    By default the execution runs to completion in the request so the response
    contains the final status. Pass ``background=true`` to start the loop in a
    background worker and poll/stream events.

    If an `incident_id` is not provided in `data`, the orchestrator will try to
    extract one from the `objective` string. A `profile_id` may also be
    supplied.
    """
    from threading import Thread

    from anvaya.db import engine

    objective = data.get("objective", "")
    if not objective:
        raise HTTPException(status_code=400, detail="objective is required")

    execution_id = data.get("execution_id", "")
    incident_id = data.get("incident_id", "")
    profile_id = data.get("profile_id", "")
    model_id = data.get("model_id", "")
    project_id = data.get("project_id", "")
    orchestrator = AgentOrchestrator(session, profile_id=profile_id, model_id=model_id)

    if execution_id:
        execution = event_store.get_execution(session, execution_id)
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        execution.status = "running"
        execution.completed_at = None
        execution.duration_ms = 0.0
        session.add(execution)
        session.commit()
    else:
        execution_id = orchestrator.start(objective, incident_id=incident_id, project_id=project_id)

    def _run() -> None:
        with Session(engine) as thread_session:
            thread_orchestrator = AgentOrchestrator(
                thread_session, profile_id=profile_id, model_id=model_id
            )
            thread_orchestrator.run(
                execution_id,
                objective=objective,
                incident_id=incident_id,
                project_id=project_id,
            )

    if background:
        Thread(target=_run, daemon=True, name=f"agent-{execution_id}").start()
    else:
        orchestrator.run(
            execution_id,
            objective=objective,
            incident_id=incident_id,
            project_id=project_id,
        )

    execution = event_store.get_execution(session, execution_id)
    if not execution:
        raise HTTPException(status_code=500, detail="Execution not found after start")

    from sqlmodel import select

    from anvaya.models.agent_context import ExecutionContext

    ctx = session.exec(
        select(ExecutionContext).where(ExecutionContext.execution_id == execution_id)
    ).first()
    ctx_project_id = ctx.project_id if ctx else project_id

    return {
        "execution_id": execution.execution_id,
        "status": execution.status,
        "incident_id": execution.incident_id,
        "project_id": ctx_project_id,
        "started_at": execution.started_at.isoformat(),
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
        "duration_ms": execution.duration_ms,
        "result_summary": execution.result_summary,
        "profile_id": profile_id,
    }


@router.post("/agent/chat")
def chat_agent(
    data: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict:
    """Run a general chat turn with the selected model.

    This is the "Ask" mode: it does not require an incident and does not call
    tools. It accepts a message, optional conversation history, and optional
    base64 images for multimodal models.
    """
    message = data.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    model_id = data.get("model_id", "")
    conversation = data.get("conversation") or []
    images = data.get("images") or []
    context_text = data.get("context_text", "")
    project_id = data.get("project_id", "")
    execution_id = data.get("execution_id", "")

    chat_engine = ChatEngine(session)
    result = chat_engine.run(
        message=message,
        model_id=model_id,
        conversation=conversation,
        images=images,
        context_text=context_text,
        project_id=project_id,
        execution_id=execution_id,
    )
    return result


@router.post("/agent/chat/stream")
def chat_agent_stream(
    data: dict[str, Any],
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Stream a general chat turn with the selected model.

    Returns Server-Sent Events for a Devin-like streaming response. Each event
    is a JSON object with ``type``, ``label``, and ``payload``.
    """
    import json as _json

    message = data.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    model_id = data.get("model_id", "")
    conversation = data.get("conversation") or []
    images = data.get("images") or []
    context_text = data.get("context_text", "")
    project_id = data.get("project_id", "")
    execution_id = data.get("execution_id", "")

    chat_engine = ChatEngine(session)

    def event_stream():
        for payload in chat_engine.stream(
            message=message,
            model_id=model_id,
            conversation=conversation,
            images=images,
            context_text=context_text,
            project_id=project_id,
            execution_id=execution_id,
        ):
            yield f"data: {_json.dumps(payload, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/agent/profiles")
def list_profiles() -> dict:
    """List built-in agent profiles."""
    return {"items": [p.model_dump() for p in default_profiles()]}


@router.get("/agent/profiles/{profile_id}")
def get_profile_route(profile_id: str) -> dict:
    """Get a single agent profile."""
    profile = get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile.model_dump()


@router.get("/agent/models")
def list_models() -> dict:
    """List model configurations with truthful availability."""
    return {"items": [m.model_dump() for m in default_models()]}


@router.get("/agent/models/{model_id:path}")
def get_model_route(model_id: str) -> dict:
    """Get a single model configuration."""
    model = get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return model.model_dump()


@router.get("/agent/providers")
def list_providers() -> dict:
    """List all tool and model providers with truthful status."""
    return {"items": all_provider_status()}


@router.get("/agent/tools")
def list_tools() -> dict:
    """List all tools in the provider-neutral registry."""
    registry = default_tool_registry()
    return {"items": [t.model_dump() for t in registry.list_tools()]}


@router.post("/agent/tools/{tool_name}/validate")
def validate_tool_inputs(
    tool_name: str,
    data: dict[str, Any],
) -> dict:
    """Validate inputs against a tool's schema without executing."""
    registry = default_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    valid, errors = registry.validate_inputs(tool_name, data)
    return {"valid": valid, "errors": errors, "tool": tool.model_dump()}


@router.get("/agent/executions")
def list_executions(
    incident_id: str | None = None,
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
) -> dict:
    """List recent agent executions."""
    stmt = select(Execution)
    if incident_id:
        stmt = stmt.where(Execution.incident_id == incident_id)
    stmt = stmt.order_by(Execution.started_at.desc()).limit(limit)
    rows = session.exec(stmt).all()
    return {"items": [r.model_dump() for r in rows], "total": len(rows)}


@router.get("/agent/executions/{execution_id}")
def get_execution(
    execution_id: str,
    session: Session = Depends(get_session),
) -> dict:
    """Get a single execution summary."""
    execution = event_store.get_execution(session, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution.model_dump()


@router.get("/agent/executions/{execution_id}/events")
def get_execution_events(
    execution_id: str,
    after: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    """Poll execution events after a given sequence number."""
    events = event_store.get_events(session, execution_id, after_sequence=after)
    return {
        "execution_id": execution_id,
        "after": after,
        "count": len(events),
        "items": [e.model_dump() for e in events],
    }


@router.get("/agent/executions/{execution_id}/stream")
def stream_execution_events(
    execution_id: str,
    after: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Server-Sent Events stream for an execution.

    This is an optional upgrade to polling. The stream emits each new event as
    it is persisted, starting from `after`. If the execution is already
    finished, all events are sent and the stream closes.
    """
    import asyncio
    import json

    from anvaya.db import engine as current_engine

    async def event_stream():
        last_sequence = after
        yield ":ok\n\n"
        for _ in range(7200):
            with Session(current_engine) as fresh_session:
                rows = event_store.get_events(
                    fresh_session, execution_id, after_sequence=last_sequence
                )
                if rows:
                    for event in rows:
                        last_sequence = event.sequence
                        payload = json.dumps(event.model_dump(), default=str)
                        yield f"data: {payload}\n\n"
                execution = event_store.get_execution(fresh_session, execution_id)
                if execution and execution.status in ("completed", "failed", "cancelled"):
                    rows = event_store.get_events(
                        fresh_session, execution_id, after_sequence=last_sequence
                    )
                    for event in rows:
                        last_sequence = event.sequence
                        payload = json.dumps(event.model_dump(), default=str)
                        yield f"data: {payload}\n\n"
                    yield "event: close\ndata: done\n\n"
                    return
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/agent/executions/{execution_id}/message")
def post_execution_message(
    execution_id: str,
    data: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict:
    """Append a user follow-up message to a running execution.

    The message is stored in the execution context and will be processed by
    the agent loop at the next safe checkpoint.
    """
    content = data.get("message") or data.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="message is required")

    try:
        context = event_store.append_message(session, execution_id, content)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"ok": True, "execution_id": execution_id, "status": context.status}


@router.post("/agent/executions/{execution_id}/cancel")
def cancel_execution(
    execution_id: str,
    session: Session = Depends(get_session),
) -> dict:
    """Request cancellation of a running execution."""
    execution = event_store.get_execution(session, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    if execution.status in ("completed", "failed", "cancelled"):
        return {"ok": False, "status": execution.status, "reason": "execution already finished"}

    try:
        context = event_store.cancel_context(session, execution_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"ok": True, "status": context.status, "execution_id": execution_id}


@router.get("/agent/executions/{execution_id}/context")
def get_execution_context(
    execution_id: str,
    session: Session = Depends(get_session),
) -> dict:
    """Get the live execution context for the reasoning panel.

    This is the source of truth for the current plan, observations, action,
    and reasoning summary, and can be used to restore state after a reconnect.
    """
    context = session.exec(
        select(ExecutionContext).where(ExecutionContext.execution_id == execution_id)
    ).first()
    if not context:
        raise HTTPException(status_code=404, detail="Execution context not found")

    return {
        "execution_id": context.execution_id,
        "objective": context.objective,
        "incident_id": context.incident_id,
        "project_id": context.project_id,
        "plan": context.plan or [],
        "observations": context.observations or [],
        "messages": context.messages or [],
        "reasoning_summary": context.reasoning_summary or "",
        "current_action": context.current_action or {},
        "model": context.model,
        "provider": context.provider,
        "status": context.status,
        "started_at": context.started_at.isoformat() if context.started_at else None,
        "updated_at": context.updated_at.isoformat() if context.updated_at else None,
        "completed_at": context.completed_at.isoformat() if context.completed_at else None,
        "mission": context.get_mission(),
        "blackboard": context.get_blackboard(),
        "hypotheses": context.get_hypotheses(),
        "memory": context.get_memory(),
        "findings": context.get_findings(),
        "verification": context.get_verification(),
    }


@router.post("/agent/seed")
def seed_agent_demo(
    session: Session = Depends(get_session),
) -> dict:
    """Generate a demo incident with telemetry and trained models for the agent."""
    from uuid import uuid4

    factory = DataFactory(session)
    bg = factory.generate(
        {
            "seed": 42,
            "normal_count": 3,
            "suspicious_count": 2,
            "attack_count": 3,
            "include_self_correction": False,
        }
    )

    all_events = list(session.exec(select(TelemetryEvent)).all())
    alertness = AlertnessEngine(session)
    alertness.train(all_events)
    whatif = WhatIfEngine(session)
    whatif.train(all_events)

    attack_scenarios = get_attack_scenarios()
    incident_count = len(list(session.exec(select(Incident)).all()))
    scenario = attack_scenarios[incident_count % len(attack_scenarios)]
    severity_by_family = {
        "lateral_movement": "high",
        "privilege_escalation": "high",
        "data_exfiltration": "high",
        "persistence": "medium",
        "credential_abuse": "medium",
        "unusual_network": "medium",
        "suspicious_login": "low",
    }
    severity = severity_by_family.get(scenario.attack_family, "medium")
    incident_id = f"INC-{uuid4().hex[:8].upper()}"
    incident = Incident(
        incident_id=incident_id,
        title=f"Agent demo — {scenario.attack_family.replace('_', ' ').title()}",
        description=scenario.description,
        severity=severity,
        attack_family=scenario.attack_family,
        scenario_id=scenario.scenario_id,
        scenario_seed=scenario.seed,
        host="WS-001",
        user="eve",
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)

    for existing in session.exec(select(Incident)).all():
        expected = severity_by_family.get(existing.attack_family, "medium")
        if existing.severity != expected:
            existing.severity = expected
            session.add(existing)
    session.commit()

    generator = TelemetryGenerator(seed=scenario.seed)
    events_data = generator.generate_for_scenario(
        scenario,
        base_time=datetime(2026, 1, 4, tzinfo=timezone.utc),
        replay_id=f"REPLAY-{scenario.scenario_id}-PRE",
        is_replay=True,
    )

    existing_ids = {
        evt.event_id
        for evt in session.exec(
            select(TelemetryEvent).where(
                TelemetryEvent.event_id.in_([e["event_id"] for e in events_data])
            )
        ).all()
    }
    for evt_data in events_data:
        if evt_data["event_id"] in existing_ids:
            continue
        event = TelemetryEvent(
            event_id=evt_data["event_id"],
            incident_id=incident.incident_id,
            scenario_id=evt_data["scenario_id"],
            event_type=evt_data["event_type"],
            timestamp=datetime.fromisoformat(evt_data["timestamp"]),
            actor=evt_data["actor"],
            host=evt_data["host"],
            process=evt_data["process"],
            source=evt_data["source"],
            destination=evt_data["destination"],
            command=evt_data["command"],
            is_off_hours=evt_data["is_off_hours"],
            is_new_device=evt_data["is_new_device"],
            is_privilege_escalation=evt_data["is_privilege_escalation"],
            is_anomalous_process=evt_data["is_anomalous_process"],
            is_unusual_network=evt_data["is_unusual_network"],
            is_lateral_movement=evt_data["is_lateral_movement"],
            is_attack=evt_data["is_attack"],
            attack_family=evt_data["attack_family"],
            ground_truth_label=evt_data["ground_truth_label"],
            seed=evt_data["seed"],
            replay_id=evt_data["replay_id"],
            is_replay=evt_data["is_replay"],
        )
        session.add(event)
    session.commit()

    return {
        "incident_id": incident.incident_id,
        "scenario_id": scenario.scenario_id,
        "background_events": bg.get("persisted_events", 0),
        "attack_events": len(events_data),
    }


@router.get("/agent/subagents/profiles")
def list_subagent_profiles() -> dict:
    """List built-in subagent profiles."""
    return {"items": [p.model_dump() for p in default_subagent_profiles()]}


@router.get("/agent/subagents/profiles/{profile_id}")
def get_subagent_profile_route(profile_id: str) -> dict:
    """Get a single subagent profile."""
    profile = get_subagent_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Subagent profile not found")
    return profile.model_dump()


@router.post("/agent/subagents")
def spawn_subagent(
    data: dict[str, Any],
    session: Session = Depends(get_session),
) -> dict:
    """Spawn a new subagent from the console.

    Requires `task`, `profile_id`, and `parent_execution_id`. If `incident_id`
    is omitted, the spawner tries to inherit it from the parent execution.
    """
    task = data.get("task", "")
    if not task:
        raise HTTPException(status_code=400, detail="task is required")

    profile_id = data.get("profile_id", "general")
    parent_execution_id = data.get("parent_execution_id", "")
    if not parent_execution_id:
        raise HTTPException(status_code=400, detail="parent_execution_id is required")

    profile = get_subagent_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Subagent profile not found")

    incident_id = data.get("incident_id", "")
    if not incident_id:
        parent = event_store.get_execution(session, parent_execution_id)
        if parent:
            incident_id = parent.incident_id

    mode = data.get("mode", "background")
    try:
        sub = subagent_spawner.spawn(
            session,
            task=task,
            profile_id=profile_id,
            parent_execution_id=parent_execution_id,
            incident_id=incident_id,
            mode=mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "subagent_id": sub.subagent_id,
        "parent_execution_id": sub.parent_execution_id,
        "child_execution_id": sub.child_execution_id,
        "profile_id": sub.profile_id,
        "title": sub.title,
        "task": sub.task,
        "mode": sub.mode,
        "status": sub.status,
        "started_at": sub.started_at.isoformat() if sub.started_at else None,
    }


@router.get("/agent/subagents")
def list_subagents(
    parent_execution_id: str | None = None,
    status: str = "",
    limit: int = Query(default=50, le=200),
    session: Session = Depends(get_session),
) -> dict:
    """List subagent executions."""
    rows = subagent_spawner.list(
        session,
        parent_execution_id=parent_execution_id or "",
        status=status,
        limit=limit,
    )
    return {
        "items": [r.model_dump() for r in rows],
        "total": len(rows),
    }


@router.get("/agent/subagents/{subagent_id}")
def get_subagent(
    subagent_id: str,
    session: Session = Depends(get_session),
) -> dict:
    """Get a single subagent execution."""
    sub = subagent_spawner.get(session, subagent_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Subagent not found")
    return sub.model_dump()


@router.post("/agent/subagents/{subagent_id}/cancel")
def cancel_subagent(
    subagent_id: str,
    session: Session = Depends(get_session),
) -> dict:
    """Cancel a pending or running subagent."""
    try:
        sub = subagent_spawner.cancel(session, subagent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return sub.model_dump()


@router.post("/agent/subagents/{subagent_id}/resume")
def resume_subagent(
    subagent_id: str,
    data: dict[str, Any] | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """Resume a subagent in the foreground with an optional follow-up task."""
    data = data or {}
    task = data.get("task", "")
    try:
        sub = subagent_spawner.resume(session, subagent_id, task=task or None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return sub.model_dump()


@router.get("/agent/executions/{execution_id}/subagents")
def list_execution_subagents(
    execution_id: str,
    session: Session = Depends(get_session),
) -> dict:
    """List subagents spawned by an execution."""
    rows = subagent_spawner.list(session, parent_execution_id=execution_id)
    return {
        "items": [r.model_dump() for r in rows],
        "total": len(rows),
    }


@router.post("/tavily/search")
def tavily_search(data: dict[str, Any]) -> dict:
    """Run a real Tavily web search for a threat-intelligence indicator.

    Returns Tavily's response shape when the TAVILY_API_KEY is configured;
    otherwise returns the same honest local fixture the adapter uses elsewhere.
    """
    indicator = data.get("indicator", "")
    if not indicator:
        raise HTTPException(status_code=400, detail="indicator is required")

    query_context = data.get("query_context", "")
    indicator_type = data.get("indicator_type", "auto")
    adapter = TavilyAdapter()
    return adapter.search(indicator, indicator_type=indicator_type, query_context=query_context)
