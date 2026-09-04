"""Incident model with state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

from anvaya.models.enums import IncidentStatus, SelfCorrectionStatus

LIFECYCLE_TRANSITIONS: dict[IncidentStatus, list[IncidentStatus]] = {
    IncidentStatus.DETECTED: [IncidentStatus.ANALYZED, IncidentStatus.ACTIVE],
    IncidentStatus.ACTIVE: [IncidentStatus.ANALYZED],
    IncidentStatus.ANALYZED: [IncidentStatus.SIMULATED],
    IncidentStatus.SIMULATED: [IncidentStatus.EXPLAINED],
    IncidentStatus.EXPLAINED: [IncidentStatus.SEALED],
    IncidentStatus.SEALED: [],
}

SELF_CORRECTION_TRANSITIONS: dict[SelfCorrectionStatus, list[SelfCorrectionStatus]] = {
    SelfCorrectionStatus.NONE: [SelfCorrectionStatus.MISS],
    SelfCorrectionStatus.MISS: [SelfCorrectionStatus.GROUND_TRUTH_CONFIRMED],
    SelfCorrectionStatus.GROUND_TRUTH_CONFIRMED: [SelfCorrectionStatus.BACKTRACKING],
    SelfCorrectionStatus.BACKTRACKING: [SelfCorrectionStatus.EVIDENCE_IDENTIFIED],
    SelfCorrectionStatus.EVIDENCE_IDENTIFIED: [SelfCorrectionStatus.RULE_PROPOSED],
    SelfCorrectionStatus.RULE_PROPOSED: [
        SelfCorrectionStatus.RULE_VALIDATED,
        SelfCorrectionStatus.STILL_MISSED,
    ],
    SelfCorrectionStatus.RULE_VALIDATED: [SelfCorrectionStatus.REPLAYING],
    SelfCorrectionStatus.REPLAYING: [
        SelfCorrectionStatus.CAUGHT,
        SelfCorrectionStatus.STILL_MISSED,
    ],
    SelfCorrectionStatus.CAUGHT: [],
    SelfCorrectionStatus.STILL_MISSED: [SelfCorrectionStatus.BACKTRACKING],
}


class Incident(SQLModel, table=True):
    __tablename__ = "incidents"

    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: str = Field(unique=True, index=True, max_length=64)
    title: str = Field(max_length=256)
    description: str = ""
    status: IncidentStatus = Field(default=IncidentStatus.DETECTED, index=True)
    self_correction_status: SelfCorrectionStatus = Field(
        default=SelfCorrectionStatus.NONE, index=True
    )
    severity: str = Field(default="medium", max_length=32)
    attack_family: str = Field(default="", max_length=128)
    scenario_id: str = Field(default="", max_length=128, index=True)
    scenario_seed: int = 0
    replay_id: str = Field(default="", max_length=128)

    blast_radius_score: float = 0.0
    risk_score: float = 0.0
    whatif_risk_delta: float = 0.0

    host: str = Field(default="", max_length=128)
    user: str = Field(default="", max_length=128)
    tenant_id: str = Field(default="default", max_length=64)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sealed_at: Optional[datetime] = None

    evidence_summary: str = ""
    event_count: Optional[int] = Field(default=None)
    rule_id_applied: Optional[int] = Field(default=None, foreign_key="detection_rules.id")
    model_version_id: Optional[int] = Field(default=None, foreign_key="model_versions.id")

    def can_transition_to(self, new_status: IncidentStatus) -> bool:
        return new_status in LIFECYCLE_TRANSITIONS.get(self.status, [])

    def transition_to(self, new_status: IncidentStatus) -> None:
        if not self.can_transition_to(new_status):
            raise ValueError(f"Invalid lifecycle transition: {self.status} → {new_status}")
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        if new_status == IncidentStatus.SEALED:
            self.sealed_at = datetime.now(timezone.utc)

    def can_self_correct_to(self, new_status: SelfCorrectionStatus) -> bool:
        return new_status in SELF_CORRECTION_TRANSITIONS.get(self.self_correction_status, [])

    def self_correct_to(self, new_status: SelfCorrectionStatus) -> None:
        if not self.can_self_correct_to(new_status):
            raise ValueError(
                f"Invalid self-correction transition: {self.self_correction_status} → {new_status}"
            )
        self.self_correction_status = new_status
        self.updated_at = datetime.now(timezone.utc)

    def is_sealed(self) -> bool:
        return self.status == IncidentStatus.SEALED
