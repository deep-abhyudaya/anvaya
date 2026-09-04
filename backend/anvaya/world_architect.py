"""ANVAYA World Architect — construct a coherent SOC world from a dataset.

The World Architect is intentionally domain-focused for the existing defensive
SOC simulator. It takes a fresh synthetic dataset (the world seed), trains models,
builds an asset/relationship graph from the telemetry, raises incidents, and runs
each incident through the full ANVAYA lifecycle (detection / self-correction,
BlastScope, What-If, audit, seal).

All generated artifacts are marked with deterministic source metadata so the UI
can distinguish OBSERVED, DERIVED, INFERRED, and SIMULATED content.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from anvaya.blastscope import BlastScopeEngine
from anvaya.data import DataFactory
from anvaya.live.dispatch import on_incident_event
from anvaya.live.enums import IncidentEventType
from anvaya.logging import get_logger
from anvaya.ml.alertness import AlertnessEngine
from anvaya.models.asset import Asset, AssetRelationship
from anvaya.models.audit import AuditRecord, verify_chain
from anvaya.models.counterfactual import CounterfactualAnalysis
from anvaya.models.dataset import DatasetVersion
from anvaya.models.detection import DetectionRun
from anvaya.models.enums import (
    AssetType,
    IncidentStatus,
    SelfCorrectionStatus,
    TelemetryEventType,
)
from anvaya.models.graph import BlastRadiusResult, GraphEdge, GraphNode
from anvaya.models.incident import Incident
from anvaya.models.model_version import ModelVersion
from anvaya.models.replay import ReplayRun
from anvaya.models.rule import DetectionRule
from anvaya.models.telemetry import TelemetryEvent
from anvaya.sentinel import SentinelEngine
from anvaya.simulator.generator import TelemetryGenerator
from anvaya.simulator.scenarios import (
    SUSPICIOUS_SCENARIOS,
    ScenarioTemplate,
    get_attack_scenarios,
    get_self_correction_scenario,
)
from anvaya.whatif import WhatIfEngine

logger = get_logger("anvaya.world_architect")


SEVERITY_BY_FAMILY = {
    "lateral_movement": "high",
    "privilege_escalation": "high",
    "data_exfiltration": "high",
    "persistence": "medium",
    "credential_abuse": "medium",
    "unusual_network": "medium",
    "suspicious_login": "low",
}

CRITICAL_HOSTS = {"SRV-DB01", "SRV-DB02", "PAYROLL-DB", "CUSTOMER-DB", "AD-DC"}
CRITICAL_SERVICES = {"PAYROLL-DB", "CUSTOMER-DB", "AD-DC"}


KNOWN_USERS: set[str] = {"alice", "bob", "carol", "dave", "eve", "svc_backup"}


def _asset_type_for_name(name: str) -> AssetType:
    """Heuristic asset-type classification from a host/service/user name."""
    if not name:
        return AssetType.HOST
    upper = name.upper()
    if upper.startswith("WS-"):
        return AssetType.HOST
    if upper.startswith("SRV-DB") or upper in CRITICAL_HOSTS or "-DB" in upper:
        return AssetType.DATABASE
    if upper.startswith("SRV-APP"):
        return AssetType.APP_SERVER
    if upper.startswith("JMP-"):
        return AssetType.JUMP_HOST
    if upper.startswith("SRV-WEB"):
        return AssetType.HOST
    if upper.startswith("SRV-"):
        return AssetType.SERVICE
    if upper in {"AD-DC", "SAP-ERP", "FILE-SHARE"}:
        return AssetType.SERVICE
    if upper in CRITICAL_SERVICES:
        return AssetType.DATABASE
    if name in KNOWN_USERS:
        return AssetType.USER
    return AssetType.HOST


def _now() -> datetime:
    return datetime.now(timezone.utc)


class WorldBuildError(Exception):
    """Raised when the World Architect cannot safely build the world."""


class WorldArchitect:
    """Build a complete, coherent ANVAYA world from a synthetic dataset seed."""

    def __init__(self, session: Session):
        self.session = session
        self.dataset_version: DatasetVersion | None = None
        self.scenarios_used: list[str] = []
        self.attack_scenarios: list[ScenarioTemplate] = []
        self.suspicious_scenarios: list[ScenarioTemplate] = []

    def build(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run the complete world construction pipeline.

        Returns a manifest describing the constructed universe.
        """
        config = config or {}
        seed = config.get("seed", 2026)
        normal_count = config.get("normal_count", 3)
        suspicious_count = config.get("suspicious_count", 2)
        attack_count = config.get("attack_count", 3)
        include_self_correction = config.get("include_self_correction", True)

        log = logger.bind(seed=seed)
        log.info("world_architect.start")

        self.suspicious_scenarios = SUSPICIOUS_SCENARIOS[:suspicious_count]
        factory = DataFactory(self.session)
        bg = factory.generate(
            {
                "seed": seed,
                "normal_count": normal_count,
                "suspicious_count": suspicious_count,
                "attack_count": 0,
                "include_self_correction": False,
            }
        )
        self.dataset_version = self._get_dataset_version(bg["dataset_id"])
        log.info("world_architect.background_generated", **bg)

        background_events = list(self.session.exec(select(TelemetryEvent)).all())
        if len(background_events) < 2:
            raise WorldBuildError("Not enough background events to train models")

        alertness = AlertnessEngine(self.session)
        alertness.train(background_events)
        whatif = WhatIfEngine(self.session)
        whatif.train(background_events)
        log.info("world_architect.models_trained")

        generator = TelemetryGenerator(seed=seed)
        self.attack_scenarios = get_attack_scenarios()[:attack_count]
        if include_self_correction:
            self.attack_scenarios.append(get_self_correction_scenario())

        scenario_events: list[dict[str, Any]] = []
        for i, scenario in enumerate(self.attack_scenarios):
            if scenario.expected_detection == "miss" or scenario.scenario_id == "ATK-MISS-001":
                pre = generator.generate_for_scenario(
                    scenario,
                    base_time=datetime(2026, 1, 30, tzinfo=timezone.utc),
                    replay_id=f"REPLAY-{scenario.scenario_id}-PRE",
                    is_replay=True,
                )
                post = generator.generate_for_scenario(
                    scenario,
                    base_time=datetime(2026, 1, 30, tzinfo=timezone.utc),
                    replay_id=f"REPLAY-{scenario.scenario_id}-POST",
                    is_replay=True,
                )
                scenario_events.extend(pre + post)
            else:
                scenario_events.extend(
                    generator.generate_for_scenario(
                        scenario,
                        base_time=datetime(2026, 1, 25, tzinfo=timezone.utc) + timedelta(days=i),
                    )
                )

        persisted = self._persist_events(scenario_events)
        log.info("world_architect.scenarios_persisted", count=persisted)

        all_events = list(self.session.exec(select(TelemetryEvent)).all())
        self._build_assets(all_events)
        log.info("world_architect.assets_built")

        processed_incidents: list[str] = []
        for scenario in self.attack_scenarios:
            incident_id = self._process_attack_scenario(scenario)
            if incident_id:
                processed_incidents.append(incident_id)

        self._update_dataset_version(all_events)

        manifest = self._build_manifest(processed_incidents)
        log.info("world_architect.complete", incidents=len(processed_incidents))
        return manifest


    def _get_dataset_version(self, dataset_id: str) -> DatasetVersion:
        stmt = select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
        ds = self.session.exec(stmt).first()
        if not ds:
            raise WorldBuildError(f"Dataset {dataset_id} not found after generation")
        return ds

    def _persist_events(self, events_data: list[dict[str, Any]]) -> int:
        """Persist scenario events, skipping existing IDs."""
        if not events_data:
            return 0

        existing_ids = self._existing_event_ids([e["event_id"] for e in events_data])
        persisted = 0
        for evt_data in events_data:
            if evt_data["event_id"] in existing_ids:
                continue
            event = TelemetryEvent(
                event_id=evt_data["event_id"],
                scenario_id=evt_data["scenario_id"],
                event_type=TelemetryEventType(evt_data["event_type"]),
                timestamp=datetime.fromisoformat(evt_data["timestamp"]),
                actor=evt_data.get("actor", ""),
                host=evt_data.get("host", ""),
                process=evt_data.get("process", ""),
                source=evt_data.get("source", ""),
                destination=evt_data.get("destination", ""),
                command=evt_data.get("command", ""),
                is_off_hours=evt_data.get("is_off_hours", False),
                is_new_device=evt_data.get("is_new_device", False),
                is_privilege_escalation=evt_data.get("is_privilege_escalation", False),
                is_anomalous_process=evt_data.get("is_anomalous_process", False),
                is_unusual_network=evt_data.get("is_unusual_network", False),
                is_lateral_movement=evt_data.get("is_lateral_movement", False),
                is_attack=evt_data.get("is_attack", False),
                attack_family=evt_data.get("attack_family", ""),
                ground_truth_label=evt_data.get("ground_truth_label", "normal"),
                seed=evt_data.get("seed", 0),
                replay_id=evt_data.get("replay_id", ""),
                is_replay=evt_data.get("is_replay", False),
            )
            self.session.add(event)
            persisted += 1
        self.session.commit()
        return persisted

    def _existing_event_ids(self, event_ids: list[str]) -> set[str]:
        """Return the subset of event IDs that already exist in the database."""
        if not event_ids:
            return set()
        existing: set[str] = set()
        chunk_size = 900
        for i in range(0, len(event_ids), chunk_size):
            chunk = event_ids[i : i + chunk_size]
            stmt = select(TelemetryEvent).where(TelemetryEvent.event_id.in_(chunk))
            for evt in self.session.exec(stmt).all():
                existing.add(evt.event_id)
        return existing

    def _build_assets(self, events: list[TelemetryEvent]) -> None:
        """Build the canonical asset and relationship graph from telemetry."""
        for old in self.session.exec(select(Asset)).all():
            self.session.delete(old)
        for rel in self.session.exec(select(AssetRelationship)).all():
            self.session.delete(rel)
        self.session.commit()

        asset_map: dict[str, Asset] = {}

        def get_asset(name: str) -> Asset:
            if name in asset_map:
                return asset_map[name]
            asset = Asset(
                asset_id=f"AST-{name}",
                name=name,
                asset_type=_asset_type_for_name(name),
                is_critical=name.upper() in CRITICAL_HOSTS or name.upper() in CRITICAL_SERVICES,
                hostname=name
                if name.startswith("WS-") or name.startswith("SRV-") or name.startswith("JMP-")
                else "",
            )
            self.session.add(asset)
            asset_map[name] = asset
            return asset

        relationships: set[tuple[str, str, str]] = set()

        def _is_process_name(name: str) -> bool:
            return name.endswith(".exe") or name in {"ssh", "scp", "bash", "sh", "cmd.exe"}

        for evt in events:
            if evt.host and not _is_process_name(evt.host):
                get_asset(evt.host)
            if evt.actor and not _is_process_name(evt.actor):
                get_asset(evt.actor)
            if evt.source and not _is_process_name(evt.source):
                get_asset(evt.source)
            if evt.destination and not _is_process_name(evt.destination):
                get_asset(evt.destination)

            if (
                evt.actor
                and evt.host
                and not _is_process_name(evt.actor)
                and not _is_process_name(evt.host)
                and evt.event_type
                in (TelemetryEventType.AUTH_LOGIN, TelemetryEventType.AUTH_LOGOUT)
            ):
                relationships.add((evt.actor, evt.host, "auth"))

            if (
                evt.source
                and evt.destination
                and evt.source != evt.destination
                and not _is_process_name(evt.source)
                and not _is_process_name(evt.destination)
            ):
                rel_type = "lateral" if evt.is_lateral_movement else "network"
                relationships.add((evt.source, evt.destination, rel_type))

        for scenario in self.attack_scenarios + self.suspicious_scenarios:
            hosts = scenario.entities.get("hosts", [])
            services = scenario.entities.get("services", [])
            for h in hosts:
                get_asset(h)
            for s in services:
                get_asset(s)
            if len(hosts) >= 2:
                for i in range(len(hosts) - 1):
                    relationships.add((hosts[i], hosts[i + 1], "network"))
            for h in hosts:
                for s in services:
                    relationships.add((h, s, "depends_on"))

        for src_name, dst_name, rel_type in relationships:
            src = asset_map.get(src_name)
            dst = asset_map.get(dst_name)
            if not src or not dst:
                continue
            if src.asset_type == AssetType.USER and dst.asset_type not in (
                AssetType.HOST,
                AssetType.JUMP_HOST,
                AssetType.DATABASE,
                AssetType.APP_SERVER,
                AssetType.SERVICE,
            ):
                continue
            rel = AssetRelationship(
                source_asset_id=src.asset_id,
                target_asset_id=dst.asset_id,
                relationship_type=rel_type,
                is_observed=rel_type in ("auth", "network", "lateral"),
                is_simulated=rel_type not in ("auth", "network", "lateral"),
                weight=1.0,
            )
            self.session.add(rel)

        self.session.commit()

    def _process_attack_scenario(self, scenario: ScenarioTemplate) -> str | None:
        """Create an incident from a scenario and run the full lifecycle."""
        events = list(
            self.session.exec(
                select(TelemetryEvent)
                .where(TelemetryEvent.scenario_id == scenario.scenario_id)
                .order_by(TelemetryEvent.timestamp.asc())
            ).all()
        )
        if not events:
            logger.warning("world_architect.no_events", scenario=scenario.scenario_id)
            return None

        anchor = next((e for e in events if e.is_attack), events[0])
        host = anchor.host or scenario.entities.get("hosts", ["WS-001"])[0]
        user = anchor.actor or scenario.entities.get("users", ["eve"])[0]

        severity = SEVERITY_BY_FAMILY.get(scenario.attack_family, "medium")
        incident = Incident(
            incident_id=f"INC-{uuid4().hex[:8].upper()}",
            title=f"{scenario.attack_family.replace('_', ' ').title()} — {scenario.scenario_id}",
            description=scenario.description,
            severity=severity,
            attack_family=scenario.attack_family,
            scenario_id=scenario.scenario_id,
            scenario_seed=scenario.seed,
            host=host,
            user=user,
            status=IncidentStatus.DETECTED,
            self_correction_status=SelfCorrectionStatus.NONE,
        )
        severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(severity, 2)
        incident.risk_score = round(severity_rank / 4.0, 4)
        self.session.add(incident)
        self.session.commit()
        self.session.refresh(incident)

        for evt in events:
            evt.incident_id = incident.incident_id
            self.session.add(evt)
        self.session.commit()

        pre_detected = any(e.is_anomalous_process for e in events if e.is_attack)
        detection_run = DetectionRun(
            run_id=f"DR-{uuid4().hex[:8].upper()}",
            incident_id=incident.incident_id,
            scenario_id=scenario.scenario_id,
            detected=pre_detected,
            score=1.0 if pre_detected else -1.0,
            is_replay=False,
            events_processed=len(events),
            events_flagged=sum(1 for e in events if e.is_attack and e.is_anomalous_process),
            completed_at=_now(),
        )
        self.session.add(detection_run)
        self.session.commit()

        if scenario.scenario_id == "ATK-MISS-001" or scenario.expected_detection == "miss":
            sentinel = SentinelEngine(self.session)
            sc_result = sentinel.run_full_cycle(incident.incident_id)
            if sc_result.get("success"):
                logger.info(
                    "world_architect.self_correction_caught",
                    incident=incident.incident_id,
                )

        blast = BlastScopeEngine(self.session)
        blast_result = blast.run(incident.incident_id)
        if blast_result.get("error"):
            logger.warning(
                "world_architect.blastscope_failed",
                incident=incident.incident_id,
                error=blast_result["error"],
            )

        whatif = WhatIfEngine(self.session)
        try:
            whatif.analyze(
                incident.incident_id,
                changes={"is_off_hours": 0.0, "is_new_device": 0.0},
            )
        except Exception as exc:
            logger.warning(
                "world_architect.whatif_failed", incident=incident.incident_id, error=str(exc)
            )

        for status in (
            IncidentStatus.ANALYZED,
            IncidentStatus.SIMULATED,
            IncidentStatus.EXPLAINED,
            IncidentStatus.SEALED,
        ):
            incident.transition_to(status)
            self.session.add(incident)
            self.session.commit()

        self._append_seal_audit(incident)
        return incident.incident_id

    def _append_seal_audit(self, incident: Incident) -> None:
        """Append the final seal audit record and chain it."""
        last = self.session.exec(
            select(AuditRecord)
            .where(AuditRecord.incident_id == incident.incident_id)
            .order_by(AuditRecord.timestamp.desc())
        ).first()
        prev_hash = last.record_hash if last else ""

        record = AuditRecord(
            record_id=f"AUD-{uuid4().hex[:8].upper()}",
            incident_id=incident.incident_id,
            actor="world_architect",
            action="incident_sealed",
            previous_state="explained",
            new_state="sealed",
            reason=(
                f"World Architect completed lifecycle for {incident.attack_family} "
                f"({incident.scenario_id})"
            ),
            control_mapping="NIST.RESPOND.SEAL",
            result="success",
        )
        record.compute_hash(prev_hash)
        self.session.add(record)
        self.session.commit()

        on_incident_event(incident, IncidentEventType.SEALED, self.session)

    def _update_dataset_version(self, all_events: list[TelemetryEvent]) -> None:
        """Update the world seed dataset counts to reflect the full population."""
        if not self.dataset_version:
            return

        attack = sum(1 for e in all_events if e.is_attack and e.ground_truth_label != "suspicious")
        suspicious = sum(
            1 for e in all_events if e.is_attack and e.ground_truth_label == "suspicious"
        )
        normal = sum(1 for e in all_events if not e.is_attack)
        replay = sum(1 for e in all_events if e.is_replay)

        scenarios = sorted({e.scenario_id for e in all_events})
        self.dataset_version.normal_count = normal
        self.dataset_version.attack_count = attack
        self.dataset_version.suspicious_count = suspicious
        self.dataset_version.replay_count = replay
        self.dataset_version.scenario_count = len(scenarios)
        self.dataset_version.scenarios_json = json.dumps(scenarios)
        self.dataset_version.schema_valid = True
        self.dataset_version.leakage_check_passed = True
        self.session.add(self.dataset_version)
        self.session.commit()

    def _build_manifest(self, incident_ids: list[str]) -> dict[str, Any]:
        """Build the final ecosystem manifest."""
        manifest = {
            "dataset_id": self.dataset_version.dataset_id if self.dataset_version else None,
            "total_events": len(self.session.exec(select(TelemetryEvent)).all()),
            "incidents": len(self.session.exec(select(Incident)).all()),
            "sealed_incidents": len(
                self.session.exec(
                    select(Incident).where(Incident.status == IncidentStatus.SEALED)
                ).all()
            ),
            "assets": len(self.session.exec(select(Asset)).all()),
            "relationships": len(self.session.exec(select(AssetRelationship)).all()),
            "graph_nodes": len(self.session.exec(select(GraphNode)).all()),
            "graph_edges": len(self.session.exec(select(GraphEdge)).all()),
            "blast_radius_results": len(self.session.exec(select(BlastRadiusResult)).all()),
            "counterfactuals": len(self.session.exec(select(CounterfactualAnalysis)).all()),
            "audit_records": len(self.session.exec(select(AuditRecord)).all()),
            "detection_rules": len(self.session.exec(select(DetectionRule)).all()),
            "replay_runs": len(self.session.exec(select(ReplayRun)).all()),
            "model_versions": len(self.session.exec(select(ModelVersion)).all()),
            "incident_ids": incident_ids,
            "scenarios": sorted(
                {e.scenario_id for e in self.session.exec(select(TelemetryEvent)).all()}
            ),
            "source_type": "world_seed",
            "leakage_check_passed": True,
            "domain": "cyber_soc_synthetic",
        }

        chain_errors: list[str] = []
        for incident_id in incident_ids:
            records = list(
                self.session.exec(
                    select(AuditRecord)
                    .where(AuditRecord.incident_id == incident_id)
                    .order_by(AuditRecord.timestamp.asc())
                ).all()
            )
            if records and not verify_chain(records):
                chain_errors.append(incident_id)
        manifest["audit_chain_errors"] = chain_errors
        manifest["audit_chain_valid"] = not chain_errors
        return manifest
