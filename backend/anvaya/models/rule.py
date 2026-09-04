"""Detection rule model with safe JSON condition DSL."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel
from sqlmodel import Field, SQLModel

from anvaya.models.enums import RuleStatus


class RuleCondition(BaseModel):
    """A single condition in the rule DSL. Safe — no code execution."""

    field: str
    operator: str
    value: Any


class RuleGroup(BaseModel):
    """A group of conditions combined with AND/OR."""

    logic: str = "and"
    conditions: list[RuleCondition] = []


class DetectionRule(SQLModel, table=True):
    __tablename__ = "detection_rules"

    id: Optional[int] = Field(default=None, primary_key=True)
    rule_id: str = Field(unique=True, index=True, max_length=64)
    name: str = Field(max_length=256)
    description: str = ""
    version: int = 1
    status: RuleStatus = Field(default=RuleStatus.DRAFT, index=True)

    conditions_json: str = ""

    attack_family: str = Field(default="", max_length=128)
    scenario_id: str = Field(default="", max_length=128)
    proposed_by: str = Field(default="system", max_length=64)
    llm_model: str = Field(default="", max_length=128)
    llm_prompt_version: str = Field(default="", max_length=64)

    validated: bool = False
    validation_score: float = 0.0
    false_positive_rate: float = 0.0
    true_positive_rate: float = 0.0

    parent_rule_id: Optional[str] = Field(default=None, max_length=64)
    incident_id: str = Field(default="", index=True, max_length=64)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    activated_at: Optional[datetime] = None
