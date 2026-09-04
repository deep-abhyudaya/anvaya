"""Scenario catalog — declarative attack and normal behavior templates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScenarioTemplate:
    scenario_id: str
    attack_family: str
    difficulty: str
    seed: int
    entities: dict[str, Any]
    timeline_template: list[dict[str, Any]]
    ground_truth_events: list[dict[str, Any]]
    expected_detection: str
    description: str = ""
    generator_version: str = "1.0.0"


HOSTS = [
    "WS-001", "WS-002", "SRV-DB01", "SRV-APP01", "JMP-01", "SRV-WEB01",
    "WS-003", "WS-004", "WS-005", "SRV-DB02", "SRV-APP02", "SRV-WEB02",
    "JMP-02", "SRV-MAIL01", "SRV-FILE01", "SRV-AD01", "WS-006", "WS-007",
    "SRV-CACHE01", "SRV-BACKUP01", "NAS-01", "PTR-01", "WS-LT-001", "WS-LT-002",
    "WS-008", "WS-009", "WS-010", "WS-011", "WS-012", "SRV-DB03",
    "SRV-APP03", "SRV-WEB03",
]
USERS = [
    "alice", "bob", "carol", "dave", "eve", "svc_backup",
    "frank", "grace", "heidi", "ivan", "judy", "svc_deploy",
    "mallory", "niaj", "olivia", "peggy", "troy", "ursa",
    "svc_monitor", "victor",
]

# Server-tier hosts shared by every dataset instance: they are NOT remapped by
# the topology namespace, so all instances converge on the same backbone the
# way real enterprise traffic converges on stable servers. This gives the
# world graph real hub-and-spoke degree variance instead of disjoint islands.
BACKBONE_HOSTS = {"SRV-DB01", "SRV-APP01", "SRV-WEB01", "JMP-01"}

# Mirrors world_architect.SEVERITY_BY_FAMILY so generated telemetry carries the
# same per-family severity the incident pipeline assigns. Kept here (not
# imported) because anvaya.world_architect already imports this package and a
# reverse import would be circular.
SEVERITY_BY_FAMILY = {
    "lateral_movement": "high",
    "privilege_escalation": "high",
    "data_exfiltration": "high",
    "persistence": "medium",
    "credential_abuse": "medium",
    "unusual_network": "medium",
    "suspicious_login": "low",
}
PROCESSES = ["chrome.exe", "outlook.exe", "cmd.exe", "powershell.exe", "ssh", "scp", "mimikatz.exe", "psexec.exe"]
SERVICES = ["SAP-ERP", "PAYROLL-DB", "CUSTOMER-DB", "AD-DC", "FILE-SHARE"]


NORMAL_SCENARIOS = [
    ScenarioTemplate(
        scenario_id="NORMAL-001",
        attack_family="normal",
        difficulty="easy",
        seed=1001,
        entities={"users": USERS[:3], "hosts": HOSTS[:3], "processes": PROCESSES[:2]},
        timeline_template=[
            {"event_type": "auth_login", "actor": "alice", "host": "WS-001", "hour": 9, "is_off_hours": False, "is_new_device": False},
            {"event_type": "process_create", "actor": "alice", "host": "WS-001", "process": "chrome.exe", "is_anomalous_process": False},
            {"event_type": "network_connect", "actor": "alice", "host": "WS-001", "source": "WS-001", "destination": "SRV-WEB01", "is_unusual_network": False},
            {"event_type": "file_access", "actor": "alice", "host": "WS-001", "is_lateral_movement": False},
        ],
        ground_truth_events=[],
        expected_detection="normal",
        description="Normal morning login and browsing",
    ),
    ScenarioTemplate(
        scenario_id="NORMAL-002",
        attack_family="normal",
        difficulty="easy",
        seed=1002,
        entities={"users": USERS[:3], "hosts": HOSTS[:3], "processes": PROCESSES[:2]},
        timeline_template=[
            {"event_type": "auth_login", "actor": "bob", "host": "WS-002", "hour": 10, "is_off_hours": False, "is_new_device": False},
            {"event_type": "process_create", "actor": "bob", "host": "WS-002", "process": "outlook.exe", "is_anomalous_process": False},
            {"event_type": "network_connect", "actor": "bob", "host": "WS-002", "source": "WS-002", "destination": "SRV-APP01", "is_unusual_network": False},
        ],
        ground_truth_events=[],
        expected_detection="normal",
        description="Normal daily work pattern",
    ),
    ScenarioTemplate(
        scenario_id="NORMAL-003",
        attack_family="normal",
        difficulty="easy",
        seed=1003,
        entities={"users": USERS[3:5], "hosts": HOSTS[3:5], "processes": PROCESSES[:2]},
        timeline_template=[
            {"event_type": "auth_login", "actor": "carol", "host": "SRV-DB01", "hour": 8, "is_off_hours": False, "is_new_device": False},
            {"event_type": "process_create", "actor": "carol", "host": "SRV-DB01", "process": "chrome.exe", "is_anomalous_process": False},
            {"event_type": "file_access", "actor": "carol", "host": "SRV-DB01", "is_lateral_movement": False},
        ],
        ground_truth_events=[],
        expected_detection="normal",
        description="Database admin normal access",
    ),
]

SUSPICIOUS_SCENARIOS = [
    ScenarioTemplate(
        scenario_id="SUSP-001",
        attack_family="suspicious_login",
        difficulty="easy",
        seed=2001,
        entities={"users": ["alice"], "hosts": ["WS-001", "WS-002"], "processes": PROCESSES[:2]},
        timeline_template=[
            {"event_type": "auth_login", "actor": "alice", "host": "WS-002", "hour": 2, "is_off_hours": True, "is_new_device": True},
            {"event_type": "process_create", "actor": "alice", "host": "WS-002", "process": "chrome.exe", "is_anomalous_process": False},
        ],
        ground_truth_events=[
            {"event_index": 0, "label": "suspicious_login", "description": "Off-hours login from new device"},
        ],
        expected_detection="suspicious",
        description="Off-hours login from new device",
    ),
    ScenarioTemplate(
        scenario_id="SUSP-002",
        attack_family="unusual_network",
        difficulty="medium",
        seed=2002,
        entities={"users": ["bob"], "hosts": ["WS-002", "SRV-DB01"], "processes": PROCESSES[:3]},
        timeline_template=[
            {"event_type": "auth_login", "actor": "bob", "host": "WS-002", "hour": 14, "is_off_hours": False, "is_new_device": False},
            {"event_type": "network_connect", "actor": "bob", "host": "WS-002", "source": "WS-002", "destination": "SRV-DB01", "is_unusual_network": True},
        ],
        ground_truth_events=[
            {"event_index": 1, "label": "unusual_network", "description": "Unusual network connection to DB server"},
        ],
        expected_detection="suspicious",
        description="Unusual network connection to database",
    ),
]

ATTACK_SCENARIOS = [
    ScenarioTemplate(
        scenario_id="ATK-001",
        attack_family="credential_abuse",
        difficulty="medium",
        seed=3001,
        entities={"users": ["alice", "svc_backup"], "hosts": ["WS-001", "SRV-DB01", "JMP-01"], "processes": PROCESSES[:4]},
        timeline_template=[
            {"event_type": "auth_login", "actor": "alice", "host": "WS-001", "hour": 3, "is_off_hours": True, "is_new_device": True},
            {"event_type": "process_create", "actor": "alice", "host": "WS-001", "process": "cmd.exe", "is_anomalous_process": True},
            {"event_type": "network_connect", "actor": "alice", "host": "WS-001", "source": "WS-001", "destination": "JMP-01", "is_unusual_network": True},
            {"event_type": "lateral_move", "actor": "alice", "host": "JMP-01", "source": "JMP-01", "destination": "SRV-DB01", "is_lateral_movement": True},
        ],
        ground_truth_events=[
            {"event_index": 0, "label": "credential_abuse", "description": "Stolen credentials used off-hours"},
            {"event_index": 1, "label": "suspicious_process", "description": "Command shell spawned in unusual context"},
            {"event_index": 2, "label": "lateral_movement", "description": "Connection to jump host"},
            {"event_index": 3, "label": "lateral_movement", "description": "Lateral movement to database server"},
        ],
        expected_detection="detect",
        description="Credential abuse with lateral movement",
    ),
    ScenarioTemplate(
        scenario_id="ATK-002",
        attack_family="privilege_escalation",
        difficulty="hard",
        seed=3002,
        entities={"users": ["bob", "svc_backup"], "hosts": ["WS-002", "SRV-APP01"], "processes": PROCESSES[2:5]},
        timeline_template=[
            {"event_type": "auth_login", "actor": "bob", "host": "WS-002", "hour": 9, "is_off_hours": False, "is_new_device": False},
            {"event_type": "process_create", "actor": "bob", "host": "WS-002", "process": "powershell.exe", "is_anomalous_process": True},
            {"event_type": "privilege_change", "actor": "bob", "host": "WS-002", "is_privilege_escalation": True},
            {"event_type": "process_create", "actor": "bob", "host": "WS-002", "process": "psexec.exe", "is_anomalous_process": True},
        ],
        ground_truth_events=[
            {"event_index": 1, "label": "suspicious_process", "description": "PowerShell spawned in unusual context"},
            {"event_index": 2, "label": "privilege_escalation", "description": "Privilege escalation detected"},
            {"event_index": 3, "label": "suspicious_process", "description": "PsExec used for remote execution"},
        ],
        expected_detection="detect",
        description="Privilege escalation via PowerShell and PsExec",
    ),
    ScenarioTemplate(
        scenario_id="ATK-003",
        attack_family="persistence",
        difficulty="hard",
        seed=3003,
        entities={"users": ["carol"], "hosts": ["SRV-DB01"], "processes": PROCESSES[2:4]},
        timeline_template=[
            {"event_type": "auth_login", "actor": "carol", "host": "SRV-DB01", "hour": 22, "is_off_hours": True, "is_new_device": False},
            {"event_type": "process_create", "actor": "carol", "host": "SRV-DB01", "process": "cmd.exe", "is_anomalous_process": True},
            {"event_type": "scheduled_task", "actor": "carol", "host": "SRV-DB01", "is_privilege_escalation": False},
        ],
        ground_truth_events=[
            {"event_index": 0, "label": "off_hours_access", "description": "Off-hours access to DB server"},
            {"event_index": 1, "label": "suspicious_process", "description": "Command shell on DB server"},
            {"event_index": 2, "label": "persistence", "description": "Scheduled task creation for persistence"},
        ],
        expected_detection="detect",
        description="Persistence via scheduled task on database server",
    ),
    ScenarioTemplate(
        scenario_id="ATK-MISS-001",
        attack_family="lateral_movement",
        difficulty="hard",
        seed=4001,
        entities={"users": ["eve"], "hosts": ["WS-001", "JMP-01", "SRV-DB01", "SRV-APP01"], "processes": PROCESSES[2:5]},
        timeline_template=[
            {"event_type": "auth_login", "actor": "eve", "host": "WS-001", "hour": 1, "is_off_hours": True, "is_new_device": True},
            {"event_type": "process_create", "actor": "eve", "host": "WS-001", "process": "ssh", "is_anomalous_process": False},
            {"event_type": "network_connect", "actor": "eve", "host": "WS-001", "source": "WS-001", "destination": "JMP-01", "is_unusual_network": True},
            {"event_type": "lateral_move", "actor": "eve", "host": "JMP-01", "source": "JMP-01", "destination": "SRV-DB01", "is_lateral_movement": True},
            {"event_type": "process_create", "actor": "eve", "host": "SRV-DB01", "process": "scp", "is_anomalous_process": False},
        ],
        ground_truth_events=[
            {"event_index": 0, "label": "credential_abuse", "description": "Off-hours login from new device"},
            {"event_index": 2, "label": "lateral_movement", "description": "Connection to jump host"},
            {"event_index": 3, "label": "lateral_movement", "description": "Lateral movement to database"},
            {"event_index": 4, "label": "data_exfiltration", "description": "SCP for data exfiltration"},
        ],
        expected_detection="miss",
        description="Lateral movement attack that evades initial detection rules",
    ),
]


def get_all_scenarios() -> list[ScenarioTemplate]:
    return NORMAL_SCENARIOS + SUSPICIOUS_SCENARIOS + ATTACK_SCENARIOS


def get_scenario(scenario_id: str) -> ScenarioTemplate | None:
    for s in get_all_scenarios():
        if s.scenario_id == scenario_id:
            return s
    return None


def get_attack_scenarios() -> list[ScenarioTemplate]:
    return ATTACK_SCENARIOS


def get_self_correction_scenario() -> ScenarioTemplate:
    return ATTACK_SCENARIOS[-1]
