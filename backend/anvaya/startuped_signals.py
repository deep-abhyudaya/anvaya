"""Non-blocking Startuped behavioral signal adapter.

Signals are queued and emitted from a daemon worker so product request paths
and the CLI never wait on the external Startuped API. Payloads are restricted
to safe observable metadata; no credentials, raw prompts, model scratch-space,
telemetry rows, or raw form contents are sent.
"""

from __future__ import annotations

import json
import os
import queue
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from anvaya.config import settings
from anvaya.logging import get_logger

logger = get_logger("anvaya.startuped")

_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=settings.startuped_queue_size)
_worker_lock = threading.Lock()
_worker_started = False
_cached_api_key: str | None = None


def _local_api_key() -> str:
    """Read the development key from ignored local MCP config when allowed."""
    if not settings.startuped_allow_local_config:
        return ""
    path = settings.base_dir / ".devin" / "mcp_config.local.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        header = data["mcpServers"]["startuped-ai"]["env"]["AUTH_HEADER"]
        return header.removeprefix("Bearer ").strip()
    except Exception:
        return ""


def _api_key() -> str:
    global _cached_api_key
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return ""
    if _cached_api_key is None:
        _cached_api_key = settings.startuped_api_key or _local_api_key()
    return _cached_api_key


def _enabled() -> bool:
    return bool(settings.startuped_signals_enabled and _api_key())


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only scalar/simple values and truncate strings."""
    if not metadata:
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            safe[key] = value[:160] if isinstance(value, str) else value
        elif isinstance(value, (list, tuple)):
            safe[key] = [v[:80] if isinstance(v, str) else v for v in value[:20]]
        elif isinstance(value, dict):
            safe[key] = {
                k: (v[:120] if isinstance(v, str) else v)
                for k, v in list(value.items())[:20]
                if isinstance(v, (str, int, float, bool, type(None)))
            }
    return safe


def _post_payload(payload: dict[str, Any]) -> dict[str, Any]:
    api_key = _api_key()
    if not api_key:
        return {"ok": False, "disabled": True, "reason": "Startuped API key not configured"}
    url = f"{settings.startuped_base_url.rstrip('/')}/api/v1/marketing/signals"
    try:
        response = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Startuped-Client": settings.startuped_client_header,
            },
            json=payload,
            timeout=settings.startuped_timeout_seconds,
        )
        ok = 200 <= response.status_code < 300
        return {
            "ok": ok,
            "status": response.status_code,
            "signal_id": response.json().get("signal", {}).get("id") if ok else None,
        }
    except Exception as exc:
        logger.warning("startuped.signal_failed", error=type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}


def _worker() -> None:
    while True:
        item = _queue.get()
        if item is None:
            return
        result = _post_payload(item)
        if not result.get("ok"):
            logger.warning(
                "startuped.signal_not_delivered",
                name=item.get("name", ""),
                status=result.get("status"),
                reason=result.get("error") or result.get("reason"),
            )


def _ensure_worker() -> None:
    global _worker_started
    with _worker_lock:
        if _worker_started:
            return
        threading.Thread(target=_worker, name="startuped-signals", daemon=True).start()
        _worker_started = True


def emit_startuped_signal(
    name: str,
    description: str,
    *,
    type: str = "behavioral",
    status: str = "active",
    strength: int = 25,
    value: str = "Medium",
    signal_key: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Queue one signal for asynchronous delivery. Never blocks the caller."""
    if not settings.startuped_signals_enabled or not _api_key():
        return False

    safe_metadata = _safe_metadata(metadata)
    event_id = str(safe_metadata.get("eventId") or uuid4())
    payload = {
        "name": name,
        "description": description,
        "type": type,
        "status": status,
        "strength": max(0, min(100, int(strength))),
        "value": value,
        "signalKey": signal_key or f"anvaya:{name}:{event_id}",
        "metadata": {**safe_metadata, "eventId": event_id},
    }
    try:
        _queue.put_nowait(payload)
        _ensure_worker()
        return True
    except queue.Full:
        logger.warning("startuped.signal_queue_full", name=name)
        return False


def emit_api_request_signal(method: str, path: str, status_code: int) -> None:
    """Automatically emit a signal for a state-changing API interaction."""
    if method.upper() == "GET" or status_code >= 400:
        return

    clean_path = "/" + path.strip("/")
    event_name = "anvaya.api.request"
    description = f"ANVAYA API {method.upper()} {clean_path} completed with {status_code}."
    metadata = {"surface": "backend", "method": method.upper(), "path": clean_path, "status": status_code}
    strength = 25
    value = "Medium"
    signal_type = "behavioral"

    if "/agent/execute" in clean_path:
        event_name = "anvaya.agent.objective.submitted"
        description = "User submitted an agentic objective."
        strength, value, signal_type = 65, "High", "engagement"
    elif "/agent/chat" in clean_path:
        event_name = "anvaya.agent.chat.message_sent"
        description = "User sent an agent chat message."
        strength, value, signal_type = 45, "Medium", "engagement"
    elif "/projects" in clean_path and method.upper() == "POST" and "/datasets" not in clean_path:
        event_name = "anvaya.project.created"
        description = "User created a project."
        strength, value, signal_type = 65, "High", "conversion"
    elif "/datasets" in clean_path:
        event_name = "anvaya.dataset.uploaded"
        description = "User uploaded or generated a dataset."
        strength, value, signal_type = 55, "Medium", "engagement"
    elif "/generate" in clean_path or "/build" in clean_path:
        event_name = "anvaya.artifact.generation.started"
        description = "User started artifact generation."
        strength, value, signal_type = 60, "High", "engagement"
    elif "/incidents" in clean_path and method.upper() == "POST" and "/transition" not in clean_path:
        event_name = "anvaya.incident.created"
        description = "An incident was created."
        strength, value, signal_type = 60, "High", "engagement"
    elif "/transition" in clean_path:
        event_name = "anvaya.incident.transitioned"
        description = "An incident lifecycle transition completed."
        strength, value, signal_type = 70, "High", "conversion"
    elif "/replay" in clean_path:
        event_name = "anvaya.replay.started"
        description = "A replay run was requested."
        strength, value, signal_type = 65, "High", "engagement"
    elif "/blastscope" in clean_path:
        event_name = "anvaya.blastscope.started"
        description = "A BlastScope simulation was started."
        strength, value, signal_type = 65, "High", "engagement"
    elif "/whatif" in clean_path:
        event_name = "anvaya.whatif.started"
        description = "A What-If analysis was started."
        strength, value, signal_type = 65, "High", "engagement"
    elif "/audit" in clean_path:
        event_name = "anvaya.audit.verified"
        description = "Audit integrity verification was requested."
        strength, value, signal_type = 80, "High", "measurement"
    elif "/demo" in clean_path:
        event_name = "anvaya.demo.started"
        description = "A demo workflow was started."
        strength, value, signal_type = 60, "High", "engagement"

    emit_startuped_signal(
        event_name,
        description,
        type=signal_type,
        strength=strength,
        value=value,
        metadata=metadata,
    )


def emit_cli_signal(command: str, phase: str, metadata: dict[str, Any] | None = None) -> None:
    """Emit CLI command lifecycle signals."""
    event_name = f"anvaya.cli.{command}.{phase}"
    emit_startuped_signal(
        event_name,
        f"ANVAYA CLI /{command} {phase}.",
        type="engagement",
        strength=45 if phase == "started" else 60,
        value="Medium" if phase == "started" else "High",
        metadata={"surface": "cli", "command": command, "phase": phase, **(metadata or {})},
    )


def emit_agent_event_signal(event: Any) -> None:
    """Map an existing ANVAYA execution event to a Startuped signal."""
    def get(name: str, default: Any = "") -> Any:
        if isinstance(event, dict):
            return event.get(name, default)
        return getattr(event, name, default)

    event_type = str(get("type") or "")
    if not event_type:
        return

    mapping = {
        "agent.started": ("anvaya.agent.execution.started", 55, "Medium", "engagement"),
        "agent.reasoning_started": ("anvaya.agent.reasoning.step.started", 25, "Low", "behavioral"),
        "agent.reasoning_completed": ("anvaya.agent.reasoning.step.completed", 35, "Medium", "behavioral"),
        "agent.decision_started": ("anvaya.agent.decision.started", 35, "Medium", "behavioral"),
        "agent.decision": ("anvaya.agent.decision.made", 40, "Medium", "behavioral"),
        "agent.tool_requested": ("anvaya.agent.tool.requested", 35, "Medium", "behavioral"),
        "tool.started": ("anvaya.agent.tool.started", 35, "Medium", "behavioral"),
        "tool.completed": ("anvaya.agent.tool.completed", 45, "Medium", "engagement"),
        "tool.failed": ("anvaya.agent.tool.failed", 35, "Medium", "behavioral"),
        "tool.fallback": ("anvaya.agent.tool.fallback", 30, "Medium", "behavioral"),
        "agent.observation": ("anvaya.agent.observation.recorded", 30, "Medium", "behavioral"),
        "agent.observation_created": ("anvaya.agent.observation.created", 35, "Medium", "behavioral"),
        "agent.plan_created": ("anvaya.agent.plan.created", 45, "Medium", "behavioral"),
        "agent.verification_completed": ("anvaya.agent.verification.completed", 55, "Medium", "measurement"),
        "agent.completed": ("anvaya.agent.completed", 70, "High", "conversion"),
        "agent.failed": ("anvaya.agent.failed", 35, "Medium", "behavioral"),
        "generation.started": ("anvaya.artifact.generation.started", 60, "High", "engagement"),
        "generation.completed": ("anvaya.artifact.generation.completed", 75, "High", "conversion"),
        "generation.failed": ("anvaya.artifact.generation.failed", 35, "Medium", "behavioral"),
        "artifact.thinking": ("anvaya.artifact.reasoning.started", 25, "Low", "behavioral"),
        "artifact.creating": ("anvaya.artifact.creation.started", 40, "Medium", "engagement"),
        "artifact.created": ("anvaya.artifact.created", 55, "Medium", "engagement"),
        "artifact.attaching": ("anvaya.artifact.attaching", 35, "Medium", "behavioral"),
        "artifact.completed": ("anvaya.artifact.completed", 65, "High", "engagement"),
        "artifact.failed": ("anvaya.artifact.failed", 35, "Medium", "behavioral"),
        "navigation.started": ("anvaya.navigation.started", 20, "Low", "behavioral"),
        "navigation.completed": ("anvaya.navigation.completed", 30, "Low", "behavioral"),
    }
    if event_type not in mapping:
        return

    name, strength, value, signal_type = mapping[event_type]
    payload = get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    metadata = {
        "surface": "agent",
        "executionId": get("execution_id"),
        "eventType": event_type,
        "tool": get("tool_name") or payload.get("tool_name"),
        "status": get("status") or payload.get("status"),
        "artifactType": get("artifact_type") or payload.get("artifact_type"),
        "stepIndex": payload.get("step_index"),
        "label": get("label") or payload.get("label"),
    }
    emit_startuped_signal(
        name,
        str(get("label") or name),
        type=signal_type,
        strength=strength,
        value=value,
        metadata=metadata,
    )
