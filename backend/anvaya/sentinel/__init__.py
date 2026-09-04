"""SentinelBacktracker — self-correction engine.

Core differentiator: MISS → GROUND_TRUTH → BACKTRACK → RULE_PROPOSED → VALIDATED → REPLAY → CAUGHT
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from anvaya.config import settings
from anvaya.live.dispatch import on_incident_event
from anvaya.live.enums import IncidentEventType
from anvaya.logging import get_logger
from anvaya.ml.features import extract_features
from anvaya.models.audit import AuditRecord
from anvaya.models.detection import DetectionRun
from anvaya.models.enums import RuleStatus, SelfCorrectionStatus
from anvaya.models.incident import Incident
from anvaya.models.replay import ReplayRun, ReplayStatus
from anvaya.models.rule import DetectionRule, RuleCondition, RuleGroup
from anvaya.models.telemetry import TelemetryEvent

logger = get_logger("anvaya.sentinel")


class SentinelEngine:
    """SentinelBacktracker self-correction engine."""

    def __init__(
        self,
        session: Session,
        model_provider: str = "",
        model_id: str = "",
    ):
        self.session = session
        self.model_provider = model_provider
        self.model_id = model_id

    def backtrack(self, incident_id: str) -> dict[str, Any]:
        """Walk backward through telemetry evidence window."""
        incident = self._get_incident(incident_id)
        if not incident:
            return {"error": "Incident not found"}

        if incident.self_correction_status == SelfCorrectionStatus.GROUND_TRUTH_CONFIRMED:
            incident.self_correct_to(SelfCorrectionStatus.BACKTRACKING)
            self._audit(incident, "backtrack_started", "GROUND_TRUTH_CONFIRMED", "BACKTRACKING")
            self.session.commit()

        events = self._get_telemetry(incident)
        attack_events = [e for e in events if e.is_attack]

        evidence: list[dict[str, Any]] = []
        for evt in reversed(attack_events):
            features = extract_features(evt)
            suspicious_features = {
                k: v
                for k, v in features.items()
                if v != 0 and k not in ("hour_of_day", "is_weekend", "event_type_code")
            }
            evidence.append(
                {
                    "event_id": evt.event_id,
                    "event_type": evt.event_type.value
                    if hasattr(evt.event_type, "value")
                    else str(evt.event_type),
                    "timestamp": evt.timestamp.isoformat(),
                    "actor": evt.actor,
                    "host": evt.host,
                    "process": evt.process,
                    "ground_truth_label": evt.ground_truth_label,
                    "suspicious_features": suspicious_features,
                }
            )

        if incident.self_correction_status == SelfCorrectionStatus.BACKTRACKING:
            incident.self_correct_to(SelfCorrectionStatus.EVIDENCE_IDENTIFIED)
            incident.evidence_summary = json.dumps(evidence[:5], default=str)
            self._audit(
                incident,
                "evidence_identified",
                "BACKTRACKING",
                "EVIDENCE_IDENTIFIED",
                evidence_ref=str(len(evidence)),
            )
            self.session.commit()

        return {
            "incident_id": incident_id,
            "evidence_count": len(evidence),
            "evidence": evidence,
            "status": incident.self_correction_status.value,
        }

    def propose_rule(self, incident_id: str) -> dict[str, Any]:
        """Propose a candidate detection rule from evidence."""
        incident = self._get_incident(incident_id)
        if not incident:
            return {"error": "Incident not found"}

        if incident.self_correction_status == SelfCorrectionStatus.EVIDENCE_IDENTIFIED:
            events = self._get_telemetry(incident)
            attack_events = [e for e in events if e.is_attack]

            feature_counts: dict[str, int] = {}
            for evt in attack_events:
                features = extract_features(evt)
                for k, v in features.items():
                    if v != 0 and k not in ("hour_of_day", "is_weekend", "event_type_code"):
                        feature_counts[k] = feature_counts.get(k, 0) + 1

            conditions: list[dict[str, Any]] = []
            for feat, count in sorted(feature_counts.items(), key=lambda x: -x[1]):
                if count >= 1:
                    conditions.append(
                        {
                            "field": feat,
                            "operator": "eq",
                            "value": 1.0,
                        }
                    )

            if not conditions:
                conditions.append({"field": "is_off_hours", "operator": "eq", "value": 1.0})

            rule_group = RuleGroup(logic="or", conditions=[RuleCondition(**c) for c in conditions])
            conditions_json = json.dumps(
                {
                    "logic": rule_group.logic,
                    "conditions": [c.model_dump() for c in rule_group.conditions],
                }
            )

            llm_result = self._llm_propose_rule(incident, attack_events, conditions)
            if llm_result:
                rule_name = llm_result.get("name", f"Auto-rule for {incident.attack_family}")
                rule_description = llm_result.get("description", "")
                llm_model = llm_result.get("model", "")
            else:
                rule_name = f"Backtrack-Rule-{incident.attack_family}"
                rule_description = (
                    "Deterministically proposed rule from evidence analysis for "
                    f"{incident.attack_family}"
                )
                llm_model = ""

            rule = DetectionRule(
                rule_id=f"RL-{uuid4().hex[:8].upper()}",
                name=rule_name,
                description=rule_description,
                conditions_json=conditions_json,
                attack_family=incident.attack_family,
                scenario_id=incident.scenario_id,
                incident_id=incident_id,
                status=RuleStatus.PROPOSED,
                proposed_by="sentinel",
                llm_model=llm_model,
                llm_prompt_version="1.0",
            )
            self.session.add(rule)

            incident.self_correct_to(SelfCorrectionStatus.RULE_PROPOSED)
            incident.rule_id_applied = None
            self._audit(
                incident,
                "rule_proposed",
                "EVIDENCE_IDENTIFIED",
                "RULE_PROPOSED",
                rule_version=rule.rule_id,
            )
            self.session.commit()
            self.session.refresh(rule)

            return {
                "incident_id": incident_id,
                "rule_id": rule.rule_id,
                "rule_name": rule.name,
                "conditions": json.loads(conditions_json),
                "status": incident.self_correction_status.value,
                "llm_used": bool(llm_model),
            }

        return {
            "incident_id": incident_id,
            "status": incident.self_correction_status.value,
            "error": "Not in EVIDENCE_IDENTIFIED state",
        }

    def validate_rule(self, incident_id: str) -> dict[str, Any]:
        """Validate the proposed rule against historical telemetry."""
        incident = self._get_incident(incident_id)
        if not incident:
            return {"error": "Incident not found"}

        if incident.self_correction_status != SelfCorrectionStatus.RULE_PROPOSED:
            return {
                "error": f"Not in RULE_PROPOSED state (current: {incident.self_correction_status})"
            }

        stmt = (
            select(DetectionRule)
            .where(
                DetectionRule.incident_id == incident_id,
                DetectionRule.status == RuleStatus.PROPOSED,
            )
            .order_by(DetectionRule.created_at.desc())
        )
        rule = self.session.exec(stmt).first()
        if not rule:
            return {"error": "No proposed rule found"}

        events = self._get_telemetry(incident)
        conditions = json.loads(rule.conditions_json)

        tp, fp, tn, fn = 0, 0, 0, 0
        for evt in events:
            features = extract_features(evt)
            detected = self._evaluate_rule(conditions, features)
            is_attack = evt.is_attack
            if detected and is_attack:
                tp += 1
            elif detected and not is_attack:
                fp += 1
            elif not detected and is_attack:
                fn += 1
            else:
                tn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        rule.validated = True
        rule.validation_score = f1
        rule.true_positive_rate = recall
        rule.false_positive_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        rule.status = RuleStatus.VALIDATED
        self.session.add(rule)

        incident.self_correct_to(SelfCorrectionStatus.RULE_VALIDATED)
        self._audit(
            incident, "rule_validated", "RULE_PROPOSED", "RULE_VALIDATED", rule_version=rule.rule_id
        )
        self.session.commit()

        on_incident_event(incident, IncidentEventType.RULE_VALIDATED, self.session)

        return {
            "incident_id": incident_id,
            "rule_id": rule.rule_id,
            "validated": True,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "status": incident.self_correction_status.value,
        }

    def replay_attack(self, incident_id: str) -> dict[str, Any]:
        """Replay the identical attack with the patched rule."""
        incident = self._get_incident(incident_id)
        if not incident:
            return {"error": "Incident not found"}

        if incident.self_correction_status != SelfCorrectionStatus.RULE_VALIDATED:
            return {
                "error": f"Not in RULE_VALIDATED state (current: {incident.self_correction_status})"
            }

        stmt = (
            select(DetectionRule)
            .where(
                DetectionRule.incident_id == incident_id,
                DetectionRule.status == RuleStatus.VALIDATED,
            )
            .order_by(DetectionRule.created_at.desc())
        )
        rule = self.session.exec(stmt).first()
        if not rule:
            return {"error": "No validated rule found"}

        events = self._get_telemetry(incident)
        attack_events = [e for e in events if e.is_attack]
        conditions = json.loads(rule.conditions_json)

        detections: list[dict[str, Any]] = []
        detected_any = False
        for evt in attack_events:
            features = extract_features(evt)
            detected = self._evaluate_rule(conditions, features)
            if detected:
                detected_any = True
            detections.append(
                {
                    "event_id": evt.event_id,
                    "detected": detected,
                    "ground_truth": True,
                }
            )

        pre_patch_detected = False
        pre_run_stmt = (
            select(DetectionRun)
            .where(
                DetectionRun.incident_id == incident_id,
                DetectionRun.is_replay.is_(False),
            )
            .order_by(DetectionRun.started_at.desc())
        )
        pre_run = self.session.exec(pre_run_stmt).first()
        if pre_run:
            pre_patch_detected = pre_run.detected
        else:
            pre_patch_detected = False

        replay = ReplayRun(
            replay_id=f"REPLAY-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            scenario_id=incident.scenario_id,
            scenario_seed=incident.scenario_seed,
            pre_patch_rule_id="original",
            pre_patch_detected=pre_patch_detected,
            pre_patch_score=0.0,
            post_patch_rule_id=rule.rule_id,
            post_patch_detected=detected_any,
            post_patch_score=1.0 if detected_any else 0.0,
            status=ReplayStatus.CAUGHT if detected_any else ReplayStatus.MISSED,
            is_identical=True,
            timeline_json=json.dumps(detections),
            completed_at=datetime.now(timezone.utc),
        )
        self.session.add(replay)

        incident.self_correct_to(SelfCorrectionStatus.REPLAYING)
        self._audit(
            incident,
            "replay_started",
            "RULE_VALIDATED",
            "REPLAYING",
            rule_version=rule.rule_id,
        )
        self.session.commit()

        incident.self_correct_to(
            SelfCorrectionStatus.CAUGHT if detected_any else SelfCorrectionStatus.STILL_MISSED
        )
        incident.replay_id = replay.replay_id
        self._audit(
            incident,
            "replay_completed",
            "REPLAYING",
            "CAUGHT" if detected_any else "STILL_MISSED",
            replay_id=replay.replay_id,
            rule_version=rule.rule_id,
        )
        self.session.commit()
        self.session.refresh(replay)

        on_incident_event(incident, IncidentEventType.REPLAY_RUN, self.session)

        return {
            "incident_id": incident_id,
            "replay_id": replay.replay_id,
            "pre_patch_detected": pre_patch_detected,
            "post_patch_detected": detected_any,
            "is_identical": True,
            "status": replay.status.value,
            "self_correction_status": incident.self_correction_status.value,
            "detections": detections,
        }

    def run_full_cycle(self, incident_id: str) -> dict[str, Any]:
        """Run the complete self-correction cycle."""
        results: dict[str, Any] = {"incident_id": incident_id, "steps": []}

        incident = self._get_incident(incident_id)
        if not incident:
            return {"error": "Incident not found"}

        if incident.self_correction_status == SelfCorrectionStatus.NONE:
            incident.self_correct_to(SelfCorrectionStatus.MISS)
            self._audit(incident, "miss_confirmed", "NONE", "MISS")
            self.session.commit()
            results["steps"].append({"step": "miss", "status": "done"})

        if incident.self_correction_status == SelfCorrectionStatus.MISS:
            incident.self_correct_to(SelfCorrectionStatus.GROUND_TRUTH_CONFIRMED)
            self._audit(incident, "ground_truth_confirmed", "MISS", "GROUND_TRUTH_CONFIRMED")
            self.session.commit()
            results["steps"].append({"step": "ground_truth", "status": "done"})

        bt = self.backtrack(incident_id)
        results["steps"].append({"step": "backtrack", "result": bt})

        pr = self.propose_rule(incident_id)
        results["steps"].append({"step": "propose_rule", "result": pr})

        vr = self.validate_rule(incident_id)
        results["steps"].append({"step": "validate_rule", "result": vr})

        rr = self.replay_attack(incident_id)
        results["steps"].append({"step": "replay", "result": rr})

        results["final_status"] = incident.self_correction_status.value
        results["success"] = incident.self_correction_status == SelfCorrectionStatus.CAUGHT
        return results

    def _evaluate_rule(self, conditions: dict[str, Any], features: dict[str, float]) -> bool:
        """Safely evaluate a rule against features. No code execution."""
        logic = conditions.get("logic", "and")
        conds = conditions.get("conditions", [])

        results = []
        for cond in conds:
            field = cond.get("field", "")
            operator = cond.get("operator", "eq")
            value = cond.get("value", 1.0)

            feat_val = features.get(field, 0.0)

            if operator == "eq":
                results.append(feat_val == value)
            elif operator == "ne":
                results.append(feat_val != value)
            elif operator == "gt":
                results.append(feat_val > value)
            elif operator == "lt":
                results.append(feat_val < value)
            elif operator == "ge":
                results.append(feat_val >= value)
            elif operator == "le":
                results.append(feat_val <= value)
            elif operator == "in":
                results.append(feat_val in value)
            elif operator == "contains":
                results.append(str(value) in str(feat_val))
            elif operator == "exists":
                results.append(field in features)
            else:
                results.append(False)

        if logic == "and":
            return all(results) if results else False
        elif logic == "or":
            return any(results) if results else False
        return False

    def _llm_propose_rule(
        self, incident: Incident, attack_events: list[TelemetryEvent], conditions: list[dict]
    ) -> dict[str, Any] | None:
        """Use the active model provider, Lyzr, or OpenAI to propose a rule."""
        evidence_text = "\n".join(
            [
                f"- Event {e.event_id}: {e.event_type} by {e.actor} on {e.host}, "
                f"label={e.ground_truth_label}, process={e.process}"
                for e in attack_events
            ]
        )

        prompt = (
            "Analyze the following security telemetry evidence and "
            "propose a detection rule.\n"
            "\n"
            f"Evidence:\n{evidence_text}\n"
            "\n"
            f"Attack family: {incident.attack_family}\n"
            "\n"
            "Propose a concise rule name and description for detecting "
            "this attack pattern.\n"
            "Respond in JSON format with keys: name, description"
        )

        # Prefer the active model provider when it is configured and healthy.
        provider_name = (self.model_provider or "").lower()
        model_id = self.model_id or ""
        if not provider_name and "/" in model_id:
            provider_name = model_id.split("/", 1)[0].lower()

        if provider_name and provider_name not in ("anvaya", "anvaya-local", "local"):
            try:
                from anvaya.llm.providers import create_model_provider

                provider = create_model_provider(provider_name, model_id)
                if provider and provider.configured() and provider.healthy():
                    response = provider.chat_completion(
                        [{"role": "user", "content": prompt}],
                        response_format={"type": "json_object"},
                        temperature=0.2,
                    )
                    if isinstance(response, Iterator):
                        response = next(response)
                    if response and not response.error and response.text:
                        result = json.loads(response.text)
                        result["model"] = provider.name
                        return result
            except Exception as e:
                logger.warning(
                    "sentinel.provider_failed",
                    provider=provider_name,
                    error=str(e),
                )

        if not (settings.is_lyzr_enabled() or settings.is_llm_enabled()):
            logger.info("sentinel.llm_skipped", reason="no_api_key")
            return None

        if settings.is_lyzr_enabled():
            from anvaya.agent.adapters import LyzrAdapter

            lyzr = LyzrAdapter()
            result = lyzr.propose(prompt)
            if not result.get("fallback_used"):
                content = result.get("content", {})
                return {
                    "name": content.get("name", f"Auto-rule for {incident.attack_family}"),
                    "description": content.get("description", ""),
                    "model": "lyzr",
                }
            logger.info("sentinel.lyzr_fallback", reason=result.get("fallback_reason"))

        try:
            from openai import OpenAI

            client = OpenAI(api_key=settings.openai_api_key)
            openai_response = client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=200,
            )

            content = openai_response.choices[0].message.content or "{}"
            result = json.loads(content)
            result["model"] = settings.openai_model
            return result

        except Exception as e:
            logger.warning("sentinel.llm_failed", error=str(e))
            return None

    def _get_incident(self, incident_id: str) -> Incident | None:
        return self.session.exec(
            select(Incident).where(Incident.incident_id == incident_id)
        ).first()

    def _get_telemetry(self, incident: Incident) -> Sequence[TelemetryEvent]:
        stmt = (
            select(TelemetryEvent)
            .where(
                (TelemetryEvent.scenario_id == incident.scenario_id)
                | (TelemetryEvent.incident_id == incident.incident_id)
            )
            .order_by(TelemetryEvent.timestamp.asc())
        )
        return self.session.exec(stmt).all()

    def _audit(
        self,
        incident: Incident,
        action: str,
        prev_state: str,
        new_state: str,
        rule_version: str = "",
        replay_id: str = "",
        evidence_ref: str = "",
    ) -> None:
        """Create an audit record linked to the incident's chain."""
        last = self.session.exec(
            select(AuditRecord)
            .where(AuditRecord.incident_id == incident.incident_id)
            .order_by(AuditRecord.timestamp.desc())
        ).first()
        prev_hash = last.record_hash if last else ""

        record = AuditRecord(
            record_id=f"AUD-{uuid4().hex[:8].upper()}",
            incident_id=incident.incident_id,
            actor="sentinel",
            action=action,
            previous_state=prev_state,
            new_state=new_state,
            reason=f"Self-correction: {action}",
            rule_version=rule_version,
            replay_id=replay_id,
            control_mapping=f"NIST.DETECT.{action.upper()}",
            evidence_ref=evidence_ref,
            result="success",
        )
        record.compute_hash(prev_hash)
        self.session.add(record)
