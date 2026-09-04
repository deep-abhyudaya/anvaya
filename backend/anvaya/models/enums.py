"""Enums shared across models."""

from __future__ import annotations

from enum import Enum


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    ACTIVE = "active"
    ANALYZED = "analyzed"
    SIMULATED = "simulated"
    EXPLAINED = "explained"
    SEALED = "sealed"


class SelfCorrectionStatus(str, Enum):
    NONE = "none"
    MISS = "miss"
    GROUND_TRUTH_CONFIRMED = "ground_truth_confirmed"
    BACKTRACKING = "backtracking"
    EVIDENCE_IDENTIFIED = "evidence_identified"
    RULE_PROPOSED = "rule_proposed"
    RULE_VALIDATED = "rule_validated"
    REPLAYING = "replaying"
    CAUGHT = "caught"
    STILL_MISSED = "still_missed"


class RuleStatus(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    VALIDATED = "validated"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DEAD = "dead"


class ReplayStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    CAUGHT = "caught"
    MISSED = "missed"
    ERROR = "error"


class AssetType(str, Enum):
    HOST = "host"
    USER = "user"
    SERVICE = "service"
    DATABASE = "database"
    APP_SERVER = "app_server"
    JUMP_HOST = "jump_host"
    NETWORK = "network"
    CREDENTIAL = "credential"


class TelemetryEventType(str, Enum):
    AUTH_LOGIN = "auth_login"
    AUTH_LOGOUT = "auth_logout"
    PROCESS_CREATE = "process_create"
    NETWORK_CONNECT = "network_connect"
    FILE_ACCESS = "file_access"
    SCHEDULED_TASK = "scheduled_task"
    PRIVILEGE_CHANGE = "privilege_change"
    LATERAL_MOVE = "lateral_move"
