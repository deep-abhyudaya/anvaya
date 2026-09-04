"""Agent execution runner for the ANVAYA interactive CLI."""

from __future__ import annotations

import threading
import time
from typing import Any

from rich.markdown import Markdown
from sqlmodel import Session

from anvaya.agent import (
    AgentOrchestrator,
    ChatEngine,
    get_profile,
    get_profile_for_objective,
)
from anvaya.agent.events import event_store
from anvaya.cli.files import extract_at_refs, read_file
from anvaya.cli.render import AnvayaRenderer
from anvaya.cli.state import CLIState

_POLL_INTERVAL = 0.4
_TERMINAL_WIDTH = 80


def _resolve_objective_context(state: CLIState, objective: str, workspace: Any) -> str:
    """Resolve ``@path`` references and file context into the objective."""
    refs = extract_at_refs(objective)
    if not refs and not state.file_contexts and not state.search_context:
        return objective

    parts: list[str] = []

    if state.search_context:
        parts.append(f"SEARCH: {state.search_context}")
        for r in state.search_results[:20]:
            parts.append(f"  {r.get('file', '')}:{r.get('line', '')} {r.get('text', '')[:120]}")

    if refs:
        for ref in refs:
            try:
                data = read_file(ref, workspace)
                snippet = "\n".join(data["lines"])
                state.add_file_context(data["path"], 1, data["total"], snippet, data["total"])
                parts.append(f"FILE: {data['path']}\n{snippet}")
            except (OSError, ValueError) as exc:
                parts.append(f"FILE: {ref} (could not read: {exc})")

    for ctx in reversed(state.file_contexts):
        path = ctx.get("path", "")
        start = ctx.get("start", 1)
        end = ctx.get("end", 0)
        if not path:
            continue
        try:
            data = read_file(path, workspace, line_start=start, line_end=end)
            parts.append(f"FILE: {data['path']} (lines {start}-{end})\n" + "\n".join(data["lines"]))
        except (OSError, ValueError) as exc:
            parts.append(f"FILE: {path} (could not read: {exc})")

    context_text = "\n\n".join(parts)[:6000]
    objective = objective + f"\n\nContext:\n{context_text}"
    return objective


def _context_prefix(state: CLIState) -> str:
    """Return a short ID snippet for the current project/incident."""
    if state.incident_id:
        return f" incident {state.incident_id}"
    if state.project_id:
        return f" project {state.project_id}"
    return ""


def run_agentic(
    session: Session,
    state: CLIState,
    renderer: AnvayaRenderer,
    objective: str,
    *,
    workspace: Any,
    cancel_requested: threading.Event | None = None,
) -> dict[str, Any]:
    """Start an agent execution and stream its events into the terminal.

    Returns a summary dict with ``execution_id`` and ``status``.
    """
    objective = _resolve_objective_context(state, objective, workspace)

    from anvaya.agent.orchestrator import _extract_incident_id, _extract_project_id

    incident_id = _extract_incident_id(objective) or state.incident_id
    project_id = _extract_project_id(objective) or state.project_id

    if not incident_id and not project_id:
        renderer.error(
            "No project or incident context. Use /project or /incident first.",
            "/project",
        )
        return {"execution_id": "", "status": "failed", "error": "no context"}

    profile = get_profile(state.profile_id) or get_profile_for_objective(objective)
    model_id = state.model_id or ""

    if not _extract_incident_id(objective) and not _extract_project_id(objective):
        if state.incident_id:
            objective = f"{objective} for incident {state.incident_id}"
            incident_id = state.incident_id
        elif state.project_id:
            objective = f"{objective} for project {state.project_id}"
            project_id = state.project_id

    renderer.console.print(f"\n[bold cyan]AGENT · WORKING[/bold cyan] {profile.display_name}")
    renderer.console.print(f"  Objective\n    {objective.splitlines()[0]}")

    orchestrator = AgentOrchestrator(session, profile_id=profile.id, model_id=model_id)
    execution_id = orchestrator.start(objective, incident_id=incident_id)

    def _worker() -> None:
        with Session(session.get_bind()) as worker_session:
            worker_orch = AgentOrchestrator(
                worker_session, profile_id=profile.id, model_id=model_id
            )
            worker_orch.run(execution_id, objective=objective, incident_id=incident_id)

    thread = threading.Thread(target=_worker, daemon=True, name=f"cli-agent-{execution_id}")
    thread.start()

    last_sequence = 0
    seen: set[tuple[str, int]] = set()
    final_status = "running"
    final_summary = ""

    try:
        while thread.is_alive() or final_status == "running":
            if cancel_requested and cancel_requested.is_set():
                event_store.cancel_context(session, execution_id)
                break

            rows = event_store.get_events(session, execution_id, after_sequence=last_sequence)
            if rows:
                for event in rows:
                    key = (event.execution_id, event.sequence)
                    if key in seen:
                        continue
                    seen.add(key)
                    renderer.event(event.model_dump(), compact=True)
                    last_sequence = max(last_sequence, event.sequence)
                    if event.type in (
                        "agent.completed",
                        "agent.failed",
                        "agent.execution_interrupted",
                    ):
                        final_status = event.payload.get("status", event.type.replace("agent.", ""))
                        if event.type == "agent.completed":
                            final_summary = event.payload.get("result_summary", "")
                        if event.type == "agent.failed":
                            final_summary = event.payload.get("error_message", "")

            execution = event_store.get_execution(session, execution_id)
            if execution and execution.status in ("completed", "failed", "cancelled"):
                if not rows:
                    break

            time.sleep(_POLL_INTERVAL)
    except KeyboardInterrupt:
        renderer.warning("Cancellation requested...")
        event_store.cancel_context(session, execution_id)
        thread.join(timeout=5)
        final_status = "cancelled"

    if thread.is_alive():
        thread.join(timeout=2)

    rows = event_store.get_events(session, execution_id, after_sequence=last_sequence)
    for event in rows:
        key = (event.execution_id, event.sequence)
        if key not in seen:
            seen.add(key)
            renderer.event(event.model_dump(), compact=True)
            last_sequence = max(last_sequence, event.sequence)

    execution = event_store.get_execution(session, execution_id)
    status = execution.status if execution else final_status
    result_summary = execution.result_summary if execution else final_summary

    state.set_active_execution(execution_id)

    return {
        "execution_id": execution_id,
        "status": status,
        "result_summary": result_summary,
    }


def run_chat(
    session: Session,
    state: CLIState,
    renderer: AnvayaRenderer,
    message: str,
    *,
    workspace: Any,
    extra_context: str = "",
    objective_context: bool = True,
) -> dict[str, Any]:
    """Run a single streaming chat turn with the selected model."""
    if objective_context:
        message = _resolve_objective_context(state, message, workspace)
    engine = ChatEngine(session)
    file_context = "\n\n".join([f"FILE: {c['path']}" for c in reversed(state.file_contexts)])
    context_text = extra_context if extra_context else file_context

    renderer.console.print(f"\n[magenta]ANVAYA[/magenta] {message.splitlines()[0]}")
    full = ""
    result: dict[str, Any] = {}
    streamed = False
    for payload in engine.stream(
        message=message,
        model_id=state.model_id,
        context_text=context_text,
        project_id=state.project_id,
    ):
        etype = payload.get("type", "")
        p = payload.get("payload", {})
        if etype == "chat.assistant" and p.get("streaming"):
            text = p.get("message", "")
            if text.startswith(full):
                delta = text[len(full) :]
                full = text
                if delta:
                    renderer.console.print(delta, end="")
                    streamed = True
        elif etype == "chat.assistant":
            full = p.get("message", "") or full
            result = p
        elif etype in ("agent.completed", "agent.failed"):
            result = p

    renderer.console.print()
    if full and not streamed:
        renderer.console.print(Markdown(full))
    return {
        "execution_id": result.get("execution_id", ""),
        "status": result.get("status", "completed"),
        "response": full,
    }
