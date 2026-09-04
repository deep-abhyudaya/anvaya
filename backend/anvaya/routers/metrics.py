"""Dashboard metrics API router."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.models.asset import Asset, AssetRelationship
from anvaya.models.audit import AuditRecord, verify_chain
from anvaya.models.counterfactual import CounterfactualAnalysis
from anvaya.models.dataset import DatasetVersion
from anvaya.models.enums import RuleStatus
from anvaya.models.graph import BlastRadiusResult, GraphEdge, GraphNode
from anvaya.models.incident import Incident, IncidentStatus
from anvaya.models.model_version import ModelVersion
from anvaya.models.replay import ReplayRun
from anvaya.models.rule import DetectionRule
from anvaya.models.telemetry import TelemetryEvent

router = APIRouter()


@router.get("/metrics")
def get_metrics(session: Session = Depends(get_session)) -> dict:
    incidents = session.exec(select(Incident)).all()
    replays = session.exec(select(ReplayRun)).all()
    rules = session.exec(select(DetectionRule)).all()
    audit_records = session.exec(select(AuditRecord)).all()

    status_counts: dict[str, int] = {}
    for inc in incidents:
        status_counts[inc.status.value] = status_counts.get(inc.status.value, 0) + 1

    sc_counts: dict[str, int] = {}
    for inc in incidents:
        sc_counts[inc.self_correction_status.value] = (
            sc_counts.get(inc.self_correction_status.value, 0) + 1
        )

    caught_replays = sum(1 for r in replays if r.post_patch_detected)
    total_replays = len(replays)

    active_rules = sum(1 for r in rules if r.status == RuleStatus.ACTIVE)
    proposed_rules = sum(1 for r in rules if r.status == RuleStatus.PROPOSED)

    return {
        "total_incidents": len(incidents),
        "status_counts": status_counts,
        "self_correction_counts": sc_counts,
        "sealed_incidents": status_counts.get("sealed", 0),
        "active_incidents": status_counts.get("detected", 0)
        + status_counts.get("analyzed", 0)
        + status_counts.get("simulated", 0)
        + status_counts.get("explained", 0),
        "total_replays": total_replays,
        "caught_replays": caught_replays,
        "replay_success_rate": caught_replays / total_replays if total_replays > 0 else 0.0,
        "active_rules": active_rules,
        "proposed_rules": proposed_rules,
        "total_rules": len(rules),
        "audit_records": len(audit_records),
        "miss_patch_catch_cycles": caught_replays,
    }


@router.get("/metrics/engines")
def get_engine_consensus(stage: str = "after", session: Session = Depends(get_session)) -> dict:
    """Get engine voting consensus data for Nerve Arena."""
    if stage == "before":
        return {
            "engines": {"SENTINEL": 0.25, "BLASTSCOPE": 0.0, "LEDGER": 0.0, "WHATIF": 0.0},
            "severity": 0.41,
            "consensus": 0.18,
            "counterfactuals": 0,
        }
    elif stage == "after":
        return {
            "engines": {"SENTINEL": 0.71, "BLASTSCOPE": 0.64, "LEDGER": 0.22, "WHATIF": 0.31},
            "severity": 0.74,
            "consensus": 0.61,
            "counterfactuals": 0,
        }
    else:
        return {
            "engines": {"SENTINEL": 0.71, "BLASTSCOPE": 0.45, "LEDGER": 0.42, "WHATIF": 0.52},
            "severity": 0.58,
            "consensus": 0.72,
            "counterfactuals": 2,
        }


def _time_str(dt: datetime | None) -> str | None:
    """Format a datetime as HH:MM, or None if missing."""
    if not dt:
        return None
    return (
        dt.strftime("%H:%M") if dt.tzinfo is None else dt.astimezone(timezone.utc).strftime("%H:%M")
    )


@router.get("/metrics/trophies")
def get_trophies(session: Session = Depends(get_session)) -> dict:
    """Get trophy/achievement data for Trophy Wall.

    Returns sealed incidents shaped for the trophy-wall UI, with real engine
    scores and counts derived from persisted engine results.
    """
    incidents = session.exec(select(Incident).where(Incident.status == IncidentStatus.SEALED)).all()

    incident_ids = [inc.incident_id for inc in incidents]
    blast_results = {
        b.incident_id: b
        for b in session.exec(
            select(BlastRadiusResult).where(BlastRadiusResult.incident_id.in_(incident_ids))
        ).all()
    }
    replay_rows = session.exec(
        select(ReplayRun).where(ReplayRun.incident_id.in_(incident_ids))
    ).all()
    replays_by_incident: dict[str, list[ReplayRun]] = {}
    for r in replay_rows:
        replays_by_incident.setdefault(r.incident_id, []).append(r)
    counterfactual_counts: dict[str, int] = {}
    for cf in session.exec(
        select(CounterfactualAnalysis).where(CounterfactualAnalysis.incident_id.in_(incident_ids))
    ).all():
        counterfactual_counts[cf.incident_id] = counterfactual_counts.get(cf.incident_id, 0) + 1
    audit_controls: dict[str, set[str]] = {}
    for a in session.exec(
        select(AuditRecord).where(AuditRecord.incident_id.in_(incident_ids))
    ).all():
        if a.control_mapping:
            audit_controls.setdefault(a.incident_id, set()).add(a.control_mapping)

    trophies: list[dict[str, Any]] = []
    for inc in incidents:
        blast = blast_results.get(inc.incident_id)
        replays = replays_by_incident.get(inc.incident_id, [])
        caught = any(r.post_patch_detected for r in replays)

        engines = {
            "sentinel": 1.0 if caught else 0.0,
            "blastscope": inc.blast_radius_score,
            "whatif": inc.whatif_risk_delta,
            "ledger": 1.0 if audit_controls.get(inc.incident_id) else 0.0,
        }

        blast_radius = inc.blast_radius_score or (blast.impact_score if blast else 0.0)
        hops = blast.max_depth if blast else 0
        counterfactuals = counterfactual_counts.get(inc.incident_id, 0)
        controls = len(audit_controls.get(inc.incident_id, set()))

        engines_fired = sum(1 for v in engines.values() if v > 0.3)
        score = engines_fired * (blast_radius or 0.1)
        weight: float
        if score >= 20:
            tier = "MYTHIC"
            weight = 2.0
        elif score >= 12:
            tier = "RARE"
            weight = 1.5
        else:
            tier = "COMMON"
            weight = 1.0

        trophies.append(
            {
                "id": inc.incident_id,
                "status": inc.status.value,
                "title": inc.title,
                "severity": inc.severity,
                "host": inc.host,
                "user": inc.user,
                "blastRadius": blast_radius,
                "hops": hops,
                "counterfactuals": counterfactuals,
                "controls": controls,
                "engines": engines,
                "tier": tier,
                "weight": weight,
                "sealedAt": _time_str(inc.sealed_at),
                "started": _time_str(inc.created_at),
            }
        )

    trophies.sort(key=lambda x: (-x["weight"], x["started"] or ""))

    return {"items": trophies}


@router.get("/metrics/world")
def get_world_manifest(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Get the current world/ecosystem manifest.

    This endpoint exposes the same counts produced by `anvaya world build`
    and is the World Architect's observable proof that every module has been
    populated from the dataset.
    """
    ds = session.exec(select(DatasetVersion).order_by(DatasetVersion.created_at.desc())).first()

    manifest = {
        "dataset_id": ds.dataset_id if ds else None,
        "total_events": len(session.exec(select(TelemetryEvent)).all()),
        "incidents": len(session.exec(select(Incident)).all()),
        "sealed_incidents": len(
            session.exec(select(Incident).where(Incident.status == IncidentStatus.SEALED)).all()
        ),
        "assets": len(session.exec(select(Asset)).all()),
        "relationships": len(session.exec(select(AssetRelationship)).all()),
        "graph_nodes": len(session.exec(select(GraphNode)).all()),
        "graph_edges": len(session.exec(select(GraphEdge)).all()),
        "blast_radius_results": len(session.exec(select(BlastRadiusResult)).all()),
        "counterfactuals": len(session.exec(select(CounterfactualAnalysis)).all()),
        "audit_records": len(session.exec(select(AuditRecord)).all()),
        "detection_rules": len(session.exec(select(DetectionRule)).all()),
        "replay_runs": len(session.exec(select(ReplayRun)).all()),
        "model_versions": len(session.exec(select(ModelVersion)).all()),
        "scenarios": sorted({e.scenario_id for e in session.exec(select(TelemetryEvent)).all()}),
        "source_type": "world_seed",
        "leakage_check_passed": bool(ds.leakage_check_passed) if ds else False,
        "domain": "cyber_soc_synthetic",
    }

    sealed = session.exec(select(Incident).where(Incident.status == IncidentStatus.SEALED)).all()
    manifest["incident_ids"] = [inc.incident_id for inc in sealed]

    chain_errors: list[str] = []
    for incident in sealed:
        records = list(
            session.exec(
                select(AuditRecord)
                .where(AuditRecord.incident_id == incident.incident_id)
                .order_by(AuditRecord.timestamp.asc())
            ).all()
        )
        if records and not verify_chain(records):
            chain_errors.append(incident.incident_id)
    manifest["audit_chain_errors"] = chain_errors
    manifest["audit_chain_valid"] = not chain_errors

    return manifest
