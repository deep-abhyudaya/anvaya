"""Shared event dispatch point for incidents and projects.

All workflows that fire on lifecycle events (Tavily enrichment, n8n Signal
API, Launchpad account creation, Gmail notification, etc.) register as steps
inside `on_incident_event` or `on_project_created`. This keeps one auditable
place that shows exactly what fires on which event type, regardless of
whether the incident came from the live-scoring path or the demo orchestrator.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from anvaya.config import settings
from anvaya.live.enums import IncidentEventType
from anvaya.logging import get_logger
from anvaya.models.audit import AuditRecord
from anvaya.models.incident import Incident
from anvaya.models.project import Project

logger = get_logger("anvaya.live.dispatch")


def _last_audit_hash(session: Session, incident_id: str) -> str:
    last = session.exec(
        select(AuditRecord)
        .where(AuditRecord.incident_id == incident_id)
        .order_by(AuditRecord.timestamp.desc())
    ).first()
    return last.record_hash if last else ""


def _append_dispatch_audit(
    incident: Incident,
    session: Session,
    action: str,
    provider: str,
    reason: str,
) -> AuditRecord:
    record = AuditRecord(
        record_id=f"AUD-{uuid4().hex[:8].upper()}",
        incident_id=incident.incident_id,
        actor="system",
        action=action,
        previous_state=incident.status.value,
        new_state=incident.status.value,
        reason=reason,
        control_mapping="NIST.DETECT.ANOMALY",
        result="success",
    )
    record.compute_hash(_last_audit_hash(session, incident.incident_id))
    session.add(record)
    return record


def _tavily_enrich(incident: Incident, session: Session) -> dict[str, Any] | None:
    """Enrich a live-detected incident with Tavily threat intelligence."""
    if not settings.is_tavily_enabled():
        return None

    from anvaya.agent.adapters import TavilyAdapter

    adapter = TavilyAdapter()
    indicator = incident.attack_family or "unknown"
    result = adapter.search(
        indicator,
        indicator_type="technique",
        query_context=f"threat intelligence {indicator}",
    )

    record_count = len(result.get("records", []))
    source = result.get("source", "anvaya-local-fixture")
    summary = f"Tavily returned {record_count} record(s) for {indicator} (source={source})"
    logger.info("tavily.enrich", incident_id=incident.incident_id, source=source)

    existing = incident.evidence_summary or ""
    incident.evidence_summary = f"{existing}\n[Tavily] {summary}".strip()
    session.add(incident)

    _append_dispatch_audit(
        incident,
        session,
        "threat_intelligence_enriched",
        source,
        summary,
    )
    session.commit()

    return {
        "provider": source,
        "fallback_used": source != "tavily",
        "fallback_reason": "" if source == "tavily" else result.get("note", "Tavily not available"),
        "record_count": record_count,
        "result": result,
    }


def _n8n_notify(
    incident: Incident,
    event_type: IncidentEventType,
    session: Session,
    workflow: str = "anvaya_incident_event",
) -> dict[str, Any] | None:
    """Notify n8n of an incident lifecycle event."""
    if not settings.is_n8n_enabled():
        return None

    from anvaya.agent.adapters import N8NAdapter

    adapter = N8NAdapter()
    payload = {
        "incident_id": incident.incident_id,
        "event_type": event_type.value,
        "status": incident.status.value,
        "attack_family": incident.attack_family or "",
        "severity": incident.severity or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    result = adapter.trigger(workflow, payload)
    source = result.get("source", "anvaya-local-handler")
    logger.info("n8n.notify", incident_id=incident.incident_id, source=source)

    _append_dispatch_audit(
        incident,
        session,
        f"automation_{workflow}",
        source,
        result.get("note", f"n8n notification for {event_type.value}"),
    )
    session.commit()

    return {
        "provider": source,
        "fallback_used": result.get("fallback_used", source != "n8n"),
        "fallback_reason": result.get("fallback_reason", ""),
        "result": result,
    }


def _signal_api_notify(
    incident: Incident,
    event_type: IncidentEventType,
    session: Session,
) -> dict[str, Any] | None:
    """Route the event to a dedicated n8n Signal API workflow.

    The n8n webhook is a single URL; n8n routes internally by the
    `workflow` field. The payload is intentionally generic
    (`event_type`, `incident_id`, etc.) so the n8n workflow can map it
    to the real Signal API contract once that contract is known.
    """
    if not settings.is_n8n_enabled():
        return None

    from anvaya.agent.adapters import N8NAdapter

    adapter = N8NAdapter()
    payload = {
        "event_type": event_type.value,
        "incident_id": incident.incident_id,
        "attack_family": incident.attack_family or "",
        "severity": incident.severity or "",
        "status": incident.status.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    result = adapter.trigger("signal", payload)
    source = result.get("source", "anvaya-local-handler")
    logger.info("signal_api.notify", incident_id=incident.incident_id, source=source)

    _append_dispatch_audit(
        incident,
        session,
        "signal_api_event",
        source,
        result.get("note", f"Signal API event for {event_type.value}"),
    )
    session.commit()

    return {
        "provider": source,
        "workflow": "signal",
        "fallback_used": result.get("fallback_used", source != "n8n"),
        "fallback_reason": result.get("fallback_reason", ""),
        "result": result,
    }


def _gmail_notify(incident: Incident, session: Session) -> dict[str, Any] | None:
    """Email the SOC team when an incident is sealed."""
    if not settings.is_gmail_enabled():
        return None

    from anvaya.agent.adapters import GmailAdapter

    adapter = GmailAdapter()
    attack = incident.attack_family or "unknown"
    subject = f"ANVAYA: incident {incident.incident_id} sealed — {attack}"
    body = (
        f"Incident {incident.incident_id} has been sealed.\n\n"
        f"Attack family: {incident.attack_family or 'unknown'}\n"
        f"Severity: {incident.severity or 'unknown'}\n"
        f"Host: {incident.host or 'unknown'}\n"
        f"User: {incident.user or 'unknown'}\n\n"
        "Review the sealed audit record in ANVAYA."
    )
    to = settings.gmail_from_email
    result = adapter.send(to, subject, body)
    source = result.get("source", "anvaya-local-handler")
    logger.info("gmail.notify", incident_id=incident.incident_id, source=source)

    _append_dispatch_audit(
        incident,
        session,
        "notify_via_email",
        source,
        result.get("note", f"Gmail notification for sealed incident {incident.incident_id}"),
    )
    session.commit()

    return {
        "provider": source,
        "fallback_used": result.get("fallback_used", source != "gmail"),
        "fallback_reason": result.get("fallback_reason", ""),
        "result": result,
    }


def on_incident_event(
    incident: Incident,
    event_type: IncidentEventType,
    session: Session,
) -> dict[str, Any]:
    """Dispatch a single incident event to enabled downstream integrations.

    This function is intentionally the only place downstream workflows should
    hook into incident lifecycle events. Each step gates on `event_type` and
    the provider's own `is_<provider>_enabled()` check.
    """
    logger.info(
        "incident_event",
        incident_id=incident.incident_id,
        event_type=event_type.value,
        status=incident.status.value,
    )

    results: list[dict[str, Any]] = []

    if event_type in {IncidentEventType.DETECTED}:
        tavily = _tavily_enrich(incident, session)
        if tavily:
            results.append({"provider": "tavily", **tavily})

    if event_type in {IncidentEventType.DETECTED, IncidentEventType.SEALED}:
        n8n = _n8n_notify(incident, event_type, session)
        if n8n:
            results.append({"provider": "n8n", **n8n})

    signal = _signal_api_notify(incident, event_type, session)
    if signal:
        results.append({"provider": "n8n", **signal})

    if event_type in {IncidentEventType.SEALED}:
        gmail = _gmail_notify(incident, session)
        if gmail:
            results.append({"provider": "gmail", **gmail})

    return {
        "incident_id": incident.incident_id,
        "event_type": event_type.value,
        "dispatched": len(results),
        "results": results,
    }


def on_project_created(project: Project, session: Session) -> dict[str, Any] | None:
    """Dispatch a project creation event to Launchpad via n8n.

    The n8n workflow receives a generic account/lead payload and maps it to
    the real Launchpad API contract once that contract is known.
    """
    if not settings.is_n8n_enabled():
        return None

    from anvaya.agent.adapters import N8NAdapter

    adapter = N8NAdapter()
    payload = {
        "event_type": "project_created",
        "project_id": project.project_id,
        "name": project.name,
        "description": project.description or "",
        "organization_id": project.organization_id or "",
        "created_by": project.created_by or "",
        "created_at": project.created_at.isoformat() if project.created_at else "",
    }
    result = adapter.trigger("launchpad_account", payload)
    source = result.get("source", "anvaya-local-handler")
    logger.info("launchpad.notify", project_id=project.project_id, source=source)

    return {
        "provider": source,
        "workflow": "launchpad_account",
        "fallback_used": result.get("fallback_used", source != "n8n"),
        "fallback_reason": result.get("fallback_reason", ""),
        "result": result,
    }
