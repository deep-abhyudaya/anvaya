"""Execution event store and streaming."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from sqlmodel import Session, select

from anvaya.agent.schemas import ExecutionEventPayload
from anvaya.logging import get_logger
from anvaya.models.agent_context import ExecutionContext
from anvaya.models.execution import Execution, ExecutionEvent
from anvaya.startuped_signals import emit_agent_event_signal

logger = get_logger("anvaya.agent.events")


class EventStore:
    """Persist and retrieve execution events.

    Events are persisted to the database so they survive restarts and can be
    replayed. An in-memory cache of the latest events is kept for SSE/streaming.
    """

    def __init__(self):
        self._cache: dict[str, list[ExecutionEventPayload]] = defaultdict(list)
        self._lock = Lock()

    def create_execution(
        self,
        session: Session,
        objective: str,
        incident_id: str = "",
        provider: str = "anvaya",
    ) -> str:
        """Create a new execution record and return its ID."""
        from uuid import uuid4

        execution_id = f"exec-{uuid4().hex[:12]}"
        execution = Execution(
            execution_id=execution_id,
            objective=objective,
            incident_id=incident_id,
            status="running",
            provider=provider,
        )
        session.add(execution)
        session.commit()

        self.emit(
            session,
            execution_id,
            1,
            "agent.started",
            label="Agent started",
            payload={"objective": objective, "incident_id": incident_id, "provider": provider},
        )
        return execution_id

    def emit(
        self,
        session: Session,
        execution_id: str,
        sequence: int,
        event_type: str,
        *,
        tool_call_id: str = "",
        tool_name: str = "",
        provider: str = "",
        status: str = "",
        label: str = "",
        payload: dict[str, Any] | None = None,
        artifact_ref: str = "",
        artifact_type: str = "",
        error_code: str = "",
        error_message: str = "",
        fallback_reason: str = "",
    ) -> ExecutionEventPayload:
        """Emit an execution event, persist it, and cache it."""
        payload = payload or {}
        event = ExecutionEvent(
            execution_id=execution_id,
            sequence=sequence,
            type=event_type,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            provider=provider,
            status=status,
            label=label,
            payload_json=json.dumps(payload, default=str),
            artifact_ref=artifact_ref,
            artifact_type=artifact_type,
            error_code=error_code,
            error_message=error_message,
            fallback_reason=fallback_reason,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        envelope = _to_payload(event)
        with self._lock:
            self._cache[execution_id].append(envelope)

        emit_agent_event_signal(envelope)

        logger.info(
            "agent.event",
            execution_id=execution_id,
            sequence=sequence,
            type=event_type,
            tool=tool_name,
            label=label,
        )
        return envelope

    def get_events(
        self,
        session: Session,
        execution_id: str,
        after_sequence: int = 0,
    ) -> list[ExecutionEventPayload]:
        """Get events for an execution, optionally after a sequence number."""
        stmt = (
            select(ExecutionEvent)
            .where(ExecutionEvent.execution_id == execution_id)
            .where(ExecutionEvent.sequence > after_sequence)
            .order_by(ExecutionEvent.sequence.asc())
        )
        rows = list(session.exec(stmt).all())
        return [_to_payload(r) for r in rows]

    def get_cached_events(self, execution_id: str) -> list[ExecutionEventPayload]:
        with self._lock:
            return list(self._cache.get(execution_id, []))

    def complete_execution(
        self,
        session: Session,
        execution_id: str,
        status: str,
        result_summary: str = "",
        error_code: str = "",
        error_message: str = "",
        fallback_used: bool = False,
        fallback_reason: str = "",
    ) -> None:
        """Mark an execution as completed/failed."""
        execution = session.exec(
            select(Execution).where(Execution.execution_id == execution_id)
        ).first()
        if not execution:
            return

        now = datetime.now(timezone.utc)
        started = execution.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        execution.status = status
        execution.completed_at = now
        execution.duration_ms = round((now - started).total_seconds() * 1000, 2)
        execution.result_summary = result_summary
        execution.error_code = error_code
        execution.error_message = error_message
        execution.fallback_used = fallback_used
        execution.fallback_reason = fallback_reason
        session.add(execution)
        session.commit()

    def get_execution(self, session: Session, execution_id: str) -> Execution | None:
        return session.exec(select(Execution).where(Execution.execution_id == execution_id)).first()

    def list_executions(
        self,
        session: Session,
        incident_id: str = "",
        limit: int = 50,
    ) -> list[Execution]:
        stmt = select(Execution)
        if incident_id:
            stmt = stmt.where(Execution.incident_id == incident_id)
        stmt = stmt.order_by(Execution.started_at.desc()).limit(limit)
        return list(session.exec(stmt).all())

    def next_sequence(self, session: Session, execution_id: str) -> int:
        """Return the next event sequence number for an execution."""
        last = session.exec(
            select(ExecutionEvent)
            .where(ExecutionEvent.execution_id == execution_id)
            .order_by(ExecutionEvent.sequence.desc())
        ).first()
        return (last.sequence + 1) if last else 1

    def get_context(self, session: Session, execution_id: str) -> ExecutionContext | None:
        """Return the live execution context, if one has been created."""
        return session.exec(
            select(ExecutionContext).where(ExecutionContext.execution_id == execution_id)
        ).first()

    def ensure_context(
        self,
        session: Session,
        execution_id: str,
    ) -> ExecutionContext:
        """Return the live context, creating a stub from ``Execution`` if needed."""
        context = self.get_context(session, execution_id)
        if context:
            return context

        execution = self.get_execution(session, execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        context = ExecutionContext(
            execution_id=execution_id,
            objective=execution.objective,
            incident_id=execution.incident_id or "",
            status=execution.status,
        )
        session.add(context)
        session.commit()
        session.refresh(context)
        return context

    def append_message(
        self,
        session: Session,
        execution_id: str,
        content: str,
        role: str = "user",
    ) -> ExecutionContext:
        """Append a user message to the execution context."""
        context = self.ensure_context(session, execution_id)
        messages = list(context.messages)
        messages.append(
            {
                "role": role,
                "content": content,
                "processed": False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        context.messages = messages
        context.touch()
        session.add(context)
        session.commit()
        session.refresh(context)
        return context

    def cancel_context(
        self,
        session: Session,
        execution_id: str,
    ) -> ExecutionContext:
        """Mark an execution context as cancelled and emit the interruption."""
        context = self.ensure_context(session, execution_id)
        if context.status in ("completed", "failed", "cancelled"):
            return context

        now = datetime.now(timezone.utc)
        context.status = "cancelled"
        context.completed_at = now
        context.touch()
        session.add(context)
        session.commit()
        session.refresh(context)

        reason = "User cancelled execution"
        self.emit(
            session,
            execution_id,
            self.next_sequence(session, execution_id),
            "agent.execution_interrupted",
            label="Execution interrupted",
            payload={"reason": reason, "by": "user"},
        )
        self.complete_execution(
            session,
            execution_id,
            "cancelled",
            result_summary=reason,
            error_code="cancelled",
            error_message=reason,
        )
        return context


def _to_payload(event: ExecutionEvent) -> ExecutionEventPayload:
    try:
        payload = json.loads(event.payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    return ExecutionEventPayload(
        id=event.id or 0,
        execution_id=event.execution_id,
        sequence=event.sequence,
        type=event.type,
        timestamp=event.timestamp.isoformat(),
        tool_call_id=event.tool_call_id,
        tool_name=event.tool_name,
        provider=event.provider,
        status=event.status,
        label=event.label,
        payload=payload,
        artifact_ref=event.artifact_ref,
        artifact_type=event.artifact_type,
        error_code=event.error_code,
        error_message=event.error_message,
        fallback_reason=event.fallback_reason,
    )


event_store = EventStore()




def emit_artifact_progress(
    store: EventStore,
    session: Session,
    execution_id: str,
    *,
    artifact_type: str,
    status: str,
    progress: float = 0.0,
    label: str = "",
    created_count: int = 0,
    tool_call_id: str = "",
) -> None:
    """Emit a structured artifact.progress event."""
    seq = store.next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        seq,
        "artifact.progress",
        tool_call_id=tool_call_id,
        artifact_type=artifact_type,
        status=status,
        label=label or f"Generating {artifact_type}",
        payload={
            "artifact_type": artifact_type,
            "status": status,
            "progress": round(progress, 2),
            "label": label or f"Building {artifact_type}",
            "created_count": created_count,
        },
    )


def emit_verification_event(
    store: EventStore,
    session: Session,
    execution_id: str,
    *,
    passed: bool,
    reason: str = "",
    missing: list[str] | None = None,
    contradictions: list[str] | None = None,
    confidence: float = 0.0,
    evidence_count: int = 0,
) -> None:
    """Emit agent.verification_started and agent.verification_completed events."""
    seq = store.next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        seq,
        "agent.verification_started",
        label="Verification started",
    )

    seq = store.next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        seq,
        "agent.verification_completed",
        label="Verification " + ("passed" if passed else "failed"),
        payload={
            "passed": passed,
            "reason": reason,
            "missing": missing or [],
            "contradictions": contradictions or [],
            "confidence": confidence,
            "evidence_count": evidence_count,
        },
    )


def emit_plan_step_update(
    store: EventStore,
    session: Session,
    execution_id: str,
    *,
    step_index: int,
    tool_name: str,
    new_status: str,
    result_summary: str = "",
) -> None:
    """Emit an agent.plan_step_update event for a single plan step change."""
    seq = store.next_sequence(session, execution_id)
    store.emit(
        session,
        execution_id,
        seq,
        "agent.plan_step_update",
        tool_name=tool_name,
        label=f"{tool_name} → {new_status}",
        payload={
            "step_index": step_index,
            "tool_name": tool_name,
            "new_status": new_status,
            "result_summary": result_summary,
        },
    )
