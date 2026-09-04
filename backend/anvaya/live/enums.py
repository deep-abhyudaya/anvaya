"""Incident event types for the shared live dispatch point."""

from __future__ import annotations

from enum import Enum


class IncidentEventType(str, Enum):
    """Incident lifecycle events that can trigger downstream integrations."""

    DETECTED = "detected"
    SEALED = "sealed"
    RULE_APPROVED = "rule_approved"
    RULE_VALIDATED = "rule_validated"
    REPLAY_RUN = "replay_run"
    INCIDENT_VIEWED = "incident_viewed"
