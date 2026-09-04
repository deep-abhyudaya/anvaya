"""Audit record model with hash-chain integrity."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class AuditRecord(SQLModel, table=True):
    __tablename__ = "audit_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    record_id: str = Field(unique=True, index=True, max_length=64)
    incident_id: str = Field(default="", index=True, max_length=64)

    actor: str = Field(default="system", max_length=128)
    action: str = Field(max_length=256)
    previous_state: str = ""
    new_state: str = ""
    reason: str = ""

    model_version: str = ""
    rule_version: str = ""
    simulation_id: str = ""
    replay_id: str = ""

    control_mapping: str = ""
    evidence_ref: str = ""

    result: str = ""
    payload_hash: str = ""
    previous_hash: str = ""
    record_hash: str = ""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_hash(self, prev_hash: str) -> str:
        """Compute the hash for this record linked to the previous record."""
        self.previous_hash = prev_hash
        ts = self.timestamp
        if ts.tzinfo is not None:
            ts = ts.replace(tzinfo=None)
        payload = {
            "record_id": self.record_id,
            "incident_id": self.incident_id,
            "actor": self.actor,
            "action": self.action,
            "previous_state": self.previous_state,
            "new_state": self.new_state,
            "reason": self.reason,
            "model_version": self.model_version,
            "rule_version": self.rule_version,
            "simulation_id": self.simulation_id,
            "replay_id": self.replay_id,
            "control_mapping": self.control_mapping,
            "result": self.result,
            "previous_hash": self.previous_hash,
            "timestamp": ts.isoformat(),
        }
        payload_str = json.dumps(payload, sort_keys=True)
        self.payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
        self.record_hash = hashlib.sha256(
            (self.payload_hash + self.previous_hash).encode()
        ).hexdigest()
        return self.record_hash


def _compute_expected_hash(record: AuditRecord, prev_hash: str) -> str:
    """Compute the expected hash for a record without mutating it."""
    ts = record.timestamp
    if ts.tzinfo is not None:
        ts = ts.replace(tzinfo=None)
    payload = {
        "record_id": record.record_id,
        "incident_id": record.incident_id,
        "actor": record.actor,
        "action": record.action,
        "previous_state": record.previous_state,
        "new_state": record.new_state,
        "reason": record.reason,
        "model_version": record.model_version,
        "rule_version": record.rule_version,
        "simulation_id": record.simulation_id,
        "replay_id": record.replay_id,
        "control_mapping": record.control_mapping,
        "result": record.result,
        "previous_hash": prev_hash,
        "timestamp": ts.isoformat(),
    }
    payload_str = json.dumps(payload, sort_keys=True)
    payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
    return hashlib.sha256((payload_hash + prev_hash).encode()).hexdigest()


def verify_chain(records: list[AuditRecord]) -> bool:
    """Verify the integrity of an audit chain. Returns False if tampered."""
    prev_hash = ""
    for record in records:
        if record.previous_hash != prev_hash:
            return False
        expected_hash = _compute_expected_hash(record, prev_hash)
        if record.record_hash != expected_hash:
            return False
        prev_hash = record.record_hash
    return True
