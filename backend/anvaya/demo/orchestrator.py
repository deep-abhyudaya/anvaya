"""Demo orchestrator — runs the complete self-correction showcase.

Executes:
generate → miss → ground_truth → backtrack → propose → validate → replay
→ caught → blastscope → whatif → seal
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlmodel import Session, select

from anvaya.blastscope import BlastScopeEngine
from anvaya.data import DataFactory
from anvaya.live.dispatch import on_incident_event
from anvaya.live.enums import IncidentEventType
from anvaya.logging import get_logger
from anvaya.ml.alertness import AlertnessEngine
from anvaya.models.audit import AuditRecord, verify_chain
from anvaya.models.detection import DetectionRun
from anvaya.models.enums import IncidentStatus
from anvaya.models.incident import Incident
from anvaya.models.replay import ReplayRun
from anvaya.models.rule import DetectionRule, RuleStatus
from anvaya.models.telemetry import TelemetryEvent
from anvaya.sentinel import SentinelEngine
from anvaya.simulator.generator import TelemetryGenerator
from anvaya.simulator.scenarios import (
    HOSTS,
    USERS,
    ScenarioTemplate,
    get_attack_scenarios,
    get_self_correction_scenario,
)
from anvaya.whatif import WhatIfEngine

logger = get_logger("anvaya.demo")

OnStepCallback = Callable[[str, dict[str, Any]], None]
OnIncidentCallback = Callable[[dict[str, Any]], None]


class DemoOrchestrator:
    """Orchestrates the complete ANVAYA self-correction demo."""

    def __init__(self, session: Session, generator_seed: int = 42):
        self.session = session
        self.generator = TelemetryGenerator(seed=generator_seed)

    def _emit(self, on_step: OnStepCallback | None, step: dict[str, Any]) -> dict[str, Any]:
        """Append a step to the internal result and notify the live callback."""
        if on_step:
            try:
                on_step(step["step"], step)
            except Exception:
                logger.exception("demo.on_step_failed", step=step.get("step"))
        return step

    def _generate_background_and_train(
        self,
        results: dict[str, Any],
        on_step: OnStepCallback | None = None,
    ) -> None:
        """Generate the background dataset and train the Alertness/What-If models."""
        log = logger.bind(step="demo")

        log.info("demo.step", step="generate_background_dataset")
        factory = DataFactory(self.session)
        bg_result = factory.generate(
            {
                "seed": self.generator.seed,
                "normal_count": 3,
                "suspicious_count": 2,
                "attack_count": 3,
                "include_self_correction": False,
            }
        )
        results["steps"].append(
            self._emit(
                on_step,
                {
                    "step": "generate_background_dataset",
                    "status": "done",
                    "events_persisted": bg_result["persisted_events"],
                    "dataset_id": bg_result.get("dataset_id"),
                    "metadata": bg_result.get("metadata"),
                },
            )
        )

        log.info("demo.step", step="train_models")
        all_events = list(self.session.exec(select(TelemetryEvent)).all())
        alertness = AlertnessEngine(self.session)
        alertness_metrics = alertness.train(all_events)
        whatif_trainer = WhatIfEngine(self.session)
        whatif_metrics = whatif_trainer.train(all_events)
        results["steps"].append(
            self._emit(
                on_step,
                {
                    "step": "train_models",
                    "status": "done",
                    "alertness_model": alertness_metrics.get("model_id"),
                    "whatif_model": whatif_metrics.get("model_id"),
                    "alertness_metrics": alertness_metrics,
                    "whatif_metrics": whatif_metrics,
                },
            )
        )

    def _persist_telemetry_events(
        self,
        events_data: list[dict[str, Any]],
    ) -> int:
        """Persist generated telemetry events, skipping duplicates by event_id."""
        existing_ids = {
            evt.event_id
            for evt in self.session.exec(
                select(TelemetryEvent).where(
                    TelemetryEvent.event_id.in_([e["event_id"] for e in events_data])
                )
            ).all()
        }
        persisted = 0
        for evt_data in events_data:
            if evt_data["event_id"] in existing_ids:
                continue
            event = TelemetryEvent(
                event_id=evt_data["event_id"],
                scenario_id=evt_data["scenario_id"],
                event_type=evt_data["event_type"],
                timestamp=datetime.fromisoformat(evt_data["timestamp"]),
                actor=evt_data["actor"],
                host=evt_data["host"],
                process=evt_data["process"],
                source=evt_data["source"],
                destination=evt_data["destination"],
                command=evt_data.get("command", ""),
                is_off_hours=evt_data["is_off_hours"],
                is_new_device=evt_data["is_new_device"],
                is_privilege_escalation=evt_data["is_privilege_escalation"],
                is_anomalous_process=evt_data["is_anomalous_process"],
                is_unusual_network=evt_data["is_unusual_network"],
                is_lateral_movement=evt_data["is_lateral_movement"],
                is_attack=evt_data["is_attack"],
                attack_family=evt_data["attack_family"],
                ground_truth_label=evt_data["ground_truth_label"],
                seed=evt_data["seed"],
                replay_id=evt_data["replay_id"],
                is_replay=evt_data["is_replay"],
            )
            self.session.add(event)
            persisted += 1
        self.session.commit()
        return persisted

    def _create_incident_for_scenario(
        self,
        scenario: ScenarioTemplate,
        events: list[TelemetryEvent],
    ) -> Incident:
        """Create and persist an incident linked to a scenario."""
        severity_by_family = {
            "lateral_movement": "high",
            "privilege_escalation": "high",
            "data_exfiltration": "high",
            "persistence": "medium",
            "credential_abuse": "medium",
            "unusual_network": "medium",
            "suspicious_login": "low",
        }

        anchor = next((e for e in events if e.is_attack), events[0])
        host = anchor.host or scenario.entities.get("hosts", ["WS-001"])[0]
        user = anchor.actor or scenario.entities.get("users", ["eve"])[0]
        severity = severity_by_family.get(scenario.attack_family, "medium")

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
        )
        self.session.add(incident)
        self.session.commit()
        self.session.refresh(incident)

        for existing in self.session.exec(select(Incident)).all():
            expected = severity_by_family.get(existing.attack_family, "medium")
            if existing.severity != expected:
                existing.severity = expected
                self.session.add(existing)
        self.session.commit()

        for evt in events:
            evt.incident_id = incident.incident_id
            self.session.add(evt)
        self.session.commit()

        return incident

    def _run_detection(
        self,
        incident: Incident,
        is_pre_patch: bool,
        detection_override: bool | None = None,
    ) -> dict[str, Any]:
        """Run detection on incident telemetry. Pre-patch intentionally misses."""
        events = self.session.exec(
            select(TelemetryEvent)
            .where(TelemetryEvent.scenario_id == incident.scenario_id)
            .order_by(TelemetryEvent.timestamp.asc())
        ).all()

        if detection_override is not None:
            detected = detection_override
        elif is_pre_patch:
            detected = False
            for evt in events:
                if evt.is_attack and evt.is_anomalous_process:
                    detected = True
                    break
        else:
            detected = True

        run = DetectionRun(
            run_id=f"DR-{uuid4().hex[:8].upper()}",
            incident_id=incident.incident_id,
            scenario_id=incident.scenario_id,
            detected=detected,
            score=1.0 if detected else -1.0,
            is_replay=not is_pre_patch,
            completed_at=datetime.now(timezone.utc),
            events_processed=len(events),
            events_flagged=sum(1 for e in events if e.is_attack) if detected else 0,
        )
        self.session.add(run)
        self.session.commit()

        return {
            "detected": detected,
            "run_id": run.run_id,
            "events_processed": len(events),
            "events_flagged": run.events_flagged,
        }

    def _run_self_correction(
        self,
        incident: Incident,
    ) -> dict[str, Any]:
        """Run the Sentinel full self-correction cycle for an incident."""
        sentinel = SentinelEngine(self.session)
        return sentinel.run_full_cycle(incident.incident_id)

    def _run_blastscope(self, incident: Incident) -> dict[str, Any]:
        """Run BlastScope and return its result."""
        blast = BlastScopeEngine(self.session)
        return blast.run(incident.incident_id)

    def _run_whatif(self, incident: Incident) -> dict[str, Any]:
        """Run What-If analysis and return its result."""
        whatif = WhatIfEngine(self.session)
        return whatif.analyze(
            incident.incident_id,
            changes={"is_off_hours": 0.0, "is_new_device": 0.0},
        )

    def _seal_incident(self, incident: Incident) -> AuditRecord:
        """Transition incident to sealed and append a tamper-evident audit record."""
        incident.transition_to(IncidentStatus.ANALYZED)
        incident.transition_to(IncidentStatus.SIMULATED)
        incident.transition_to(IncidentStatus.EXPLAINED)
        incident.transition_to(IncidentStatus.SEALED)
        self.session.add(incident)

        last_audit = self.session.exec(
            select(AuditRecord)
            .where(AuditRecord.incident_id == incident.incident_id)
            .order_by(AuditRecord.timestamp.desc())
        ).first()
        prev_hash = last_audit.record_hash if last_audit else ""
        seal_record = AuditRecord(
            record_id=f"AUD-{uuid4().hex[:8].upper()}",
            incident_id=incident.incident_id,
            actor="system",
            action="incident_sealed",
            previous_state="explained",
            new_state="sealed",
            reason=(
                "Complete self-correction cycle: miss→patch→replay→caught→blastscope→whatif→sealed"
            ),
            control_mapping="NIST.RESPOND.SEAL",
            result="success",
        )
        seal_record.compute_hash(prev_hash)
        self.session.add(seal_record)
        self.session.commit()

        on_incident_event(incident, IncidentEventType.SEALED, self.session)
        return seal_record

    def _verify_audit_chain(self, incident: Incident) -> dict[str, Any]:
        """Verify the audit chain for an incident."""
        audit_records = self.session.exec(
            select(AuditRecord)
            .where(AuditRecord.incident_id == incident.incident_id)
            .order_by(AuditRecord.timestamp.asc())
        ).all()
        chain_valid = verify_chain(list(audit_records))
        return {
            "chain_valid": chain_valid,
            "audit_records": len(audit_records),
        }

    def _run_single_incident(
        self,
        scenario: ScenarioTemplate,
        base_time: datetime | None = None,
        scenario_seed: int | None = None,
        actor: str | None = None,
        host: str | None = None,
        on_step: OnStepCallback | None = None,
        run_self_correction: bool = True,
        run_seal: bool = True,
    ) -> dict[str, Any]:
        """Run the full lifecycle for one incident and return structured results.

        This is the shared engine used by both the single demo and the batch demo.
        """
        log = logger.bind(step="demo", scenario=scenario.scenario_id)
        incident_results: dict[str, Any] = {
            "scenario_id": scenario.scenario_id,
            "attack_family": scenario.attack_family,
            "steps": [],
            "success": False,
        }

        if base_time is None:
            base_time = datetime(2026, 1, 4, tzinfo=timezone.utc)

        log.info("demo.step", step="generate_telemetry")
        events_data = self.generator.generate_for_scenario(
            scenario,
            base_time=base_time,
            replay_id=f"REPLAY-{scenario.scenario_id}-PRE",
            is_replay=True,
            scenario_seed=scenario_seed,
            actor=actor,
            host=host,
        )
        persisted = self._persist_telemetry_events(events_data)

        incident_results["steps"].append(
            self._emit(
                on_step,
                {
                    "step": "generate_telemetry",
                    "status": "done",
                    "events_generated": len(events_data),
                    "events_persisted": persisted,
                    "scenario_id": scenario.scenario_id,
                    "attack_family": scenario.attack_family,
                    "description": scenario.description,
                },
            )
        )

        events = self.session.exec(
            select(TelemetryEvent)
            .where(TelemetryEvent.scenario_id == scenario.scenario_id)
            .order_by(TelemetryEvent.timestamp.asc())
        ).all()

        log.info("demo.step", step="create_incident")
        incident = self._create_incident_for_scenario(scenario, list(events))
        incident_results["incident_id"] = incident.incident_id
        incident_results["steps"].append(
            self._emit(
                on_step,
                {
                    "step": "create_incident",
                    "status": "done",
                    "incident_id": incident.incident_id,
                    "host": incident.host,
                    "user": incident.user,
                },
            )
        )

        log.info("demo.step", step="pre_patch_detection")
        pre_patch_result = self._run_detection(incident, is_pre_patch=True)
        incident_results["pre_patch_detected"] = pre_patch_result["detected"]
        incident_results["steps"].append(
            self._emit(
                on_step,
                {
                    "step": "pre_patch_detection",
                    "status": "done",
                    "detected": pre_patch_result["detected"],
                    "result": "MISS" if not pre_patch_result["detected"] else "DETECTED",
                    "events_processed": pre_patch_result.get("events_processed", 0),
                    "events_flagged": pre_patch_result.get("events_flagged", 0),
                    "run_id": pre_patch_result.get("run_id"),
                },
            )
        )

        if run_self_correction:
            if pre_patch_result["detected"]:
                # Caught pre-patch: no self-correction needed.  Still fill in the
                # step so the caller can narrate the distinction.
                incident_results["steps"].append(
                    self._emit(
                        on_step,
                        {
                            "step": "self_correction",
                            "status": "skipped",
                            "reason": "pre_patch_detected",
                            "result": {
                                "final_status": "skipped",
                                "success": True,
                                "reason": (
                                    "Incident was caught by pre-patch rules; "
                                    "no self-correction needed."
                                ),
                            },
                        },
                    )
                )
            else:
                log.info("demo.step", step="self_correction")
                sc_result = self._run_self_correction(incident)
                incident_results["steps"].append(
                    self._emit(
                        on_step,
                        {
                            "step": "self_correction",
                            "status": "done",
                            "result": sc_result,
                        },
                    )
                )
                if sc_result.get("final_status") != "caught":
                    incident_results["success"] = False
                    incident_results["error"] = (
                        f"Self-correction failed: {sc_result.get('final_status')}"
                    )
                    return incident_results

        log.info("demo.step", step="blastscope")
        blast_result = self._run_blastscope(incident)
        incident_results["steps"].append(
            self._emit(
                on_step,
                {
                    "step": "blastscope",
                    "status": "done",
                    "result": blast_result,
                },
            )
        )

        log.info("demo.step", step="whatif")
        whatif_result = self._run_whatif(incident)
        incident_results["steps"].append(
            self._emit(
                on_step,
                {
                    "step": "whatif",
                    "status": "done",
                    "result": whatif_result,
                },
            )
        )

        if run_seal:
            log.info("demo.step", step="seal")
            seal_record = self._seal_incident(incident)
            incident_results["steps"].append(
                self._emit(
                    on_step,
                    {
                        "step": "seal",
                        "status": "done",
                        "incident_status": "sealed",
                        "record_id": seal_record.record_id,
                    },
                )
            )

            log.info("demo.step", step="verify_audit")
            audit_info = self._verify_audit_chain(incident)
            incident_results["steps"].append(
                self._emit(
                    on_step,
                    {
                        "step": "verify_audit",
                        "status": "done",
                        **audit_info,
                    },
                )
            )

        incident_results["success"] = True
        return incident_results

    def run_full_demo(
        self,
        on_step: OnStepCallback | None = None,
    ) -> dict[str, Any]:
        """Run the complete demo sequence. Returns structured result."""
        log = logger.bind(step="demo")
        results: dict[str, Any] = {"steps": [], "success": False}

        self._generate_background_and_train(results, on_step=on_step)

        scenario = get_self_correction_scenario()
        incident_result = self._run_single_incident(
            scenario,
            on_step=on_step,
            run_self_correction=True,
            run_seal=True,
        )

        # Flatten the per-incident steps into the legacy top-level steps list
        # so existing consumers (tests, API callers) continue to see the shape
        # they expect.
        for step in incident_result.get("steps", []):
            if step.get("step") == "generate_telemetry":
                step["scenario_id"] = scenario.scenario_id
            results["steps"].append(step)

        if not incident_result.get("success"):
            results["success"] = False
            results["error"] = incident_result.get("error", "Demo failed")
            return results

        results["success"] = True
        results["incident_id"] = incident_result["incident_id"]
        results["scenario_id"] = scenario.scenario_id
        results["audit_valid"] = next(
            (
                s.get("chain_valid", False)
                for s in incident_result.get("steps", [])
                if s.get("step") == "verify_audit"
            ),
            False,
        )
        log.info("demo.complete", success=True, incident_id=results["incident_id"])
        return results

    def run_batch_demo(
        self,
        count: int = 20,
        scenarios: str = "all",
        on_step: OnStepCallback | None = None,
        on_incident: OnIncidentCallback | None = None,
    ) -> dict[str, Any]:
        """Run the full self-correction cycle across a batch of varied incidents.

        Models are trained once at the start.  Incidents are drawn from the
        available attack templates (or a filtered subset), with each incident
        varied by actor, host, base timestamp, and seed so the batch looks like
        a realistic stream of distinct attacks built from a small set of
        behavioral patterns.
        """
        log = logger.bind(step="demo")
        results: dict[str, Any] = {
            "steps": [],
            "incidents": [],
            "success": False,
        }

        self._generate_background_and_train(results, on_step=on_step)

        if scenarios == "all":
            templates = get_attack_scenarios()
        else:
            wanted = {s.strip() for s in scenarios.split(",") if s.strip()}
            templates = [s for s in get_attack_scenarios() if s.scenario_id in wanted]

        if not templates:
            results["success"] = False
            results["error"] = f"No attack scenarios matched: {scenarios}"
            return results

        available_hosts = [h for h in HOSTS if h.startswith(("WS-", "SRV-"))]
        available_users = [u for u in USERS if u not in ("svc_backup",)]

        caught_immediately = 0
        missed_then_corrected = 0
        failed_self_correction = 0

        for i in range(count):
            scenario = templates[i % len(templates)]

            # Derive a distinct seed, actor, host, and timestamp for this
            # variation while preserving the underlying attack pattern.
            batch_seed = scenario.seed + (i + 1) * 1000
            host = available_hosts[i % len(available_hosts)]
            actor = available_users[i % len(available_users)]
            base_time = datetime(2026, 1, 4, tzinfo=timezone.utc) + timedelta(
                hours=i % 24, days=i // 24
            )

            def _per_incident_step(step_name: str, step_result: dict[str, Any]) -> None:
                if on_step:
                    on_step(step_name, {**step_result, "batch_index": i})

            incident_result = self._run_single_incident(
                scenario,
                base_time=base_time,
                scenario_seed=batch_seed,
                actor=actor,
                host=host,
                on_step=_per_incident_step,
                run_self_correction=True,
                run_seal=True,
            )

            if incident_result.get("pre_patch_detected"):
                caught_immediately += 1
            elif incident_result.get("success"):
                missed_then_corrected += 1
            else:
                failed_self_correction += 1

            results["incidents"].append(incident_result)
            if on_incident:
                try:
                    on_incident(incident_result)
                except Exception:
                    logger.exception("demo.on_incident_failed", index=i)

        results["summary"] = {
            "total": count,
            "caught_immediately": caught_immediately,
            "missed_then_corrected": missed_then_corrected,
            "failed_self_correction": failed_self_correction,
            "templates_used": [s.scenario_id for s in templates],
            "variations_per_template": count // len(templates),
            "remainder": count % len(templates),
        }
        results["success"] = failed_self_correction == 0
        results["audit_valid"] = all(
            next(
                (
                    s.get("chain_valid", False)
                    for s in inc.get("steps", [])
                    if s.get("step") == "verify_audit"
                ),
                False,
            )
            for inc in results["incidents"]
        )
        log.info(
            "demo.batch_complete",
            total=count,
            caught=caught_immediately,
            missed_corrected=missed_then_corrected,
            failed=failed_self_correction,
        )
        return results

    def get_status(self) -> dict[str, Any]:
        """Get current demo status from existing data."""
        incidents = self.session.exec(select(Incident)).all()
        replays = self.session.exec(select(ReplayRun)).all()
        audits = self.session.exec(select(AuditRecord)).all()
        rules = self.session.exec(select(DetectionRule)).all()

        return {
            "total_incidents": len(incidents),
            "sealed_incidents": sum(1 for i in incidents if i.status == IncidentStatus.SEALED),
            "total_replays": len(replays),
            "caught_replays": sum(1 for r in replays if r.post_patch_detected),
            "total_audits": len(audits),
            "total_rules": len(rules),
            "validated_rules": sum(1 for r in rules if r.status == RuleStatus.VALIDATED),
        }
