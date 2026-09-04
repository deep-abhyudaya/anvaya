"""Simulation API router for threat ecosystem and other visualizations."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.models.project import ProjectArtifact, ProjectArtifactPayload
from anvaya.visual_layouts import (
    ECO_CONTAIN_STEPS,
    ECO_EDGES,
    ECO_IGNORE_STEPS,
    ECO_NODES,
    ECO_REF_VIEW_H,
    ECO_REF_VIEW_W,
)

router = APIRouter()


def _hash_float(s: str, lo: float = 0.5, hi: float = 0.8) -> float:
    """Return a deterministic float in [lo, hi] for a string."""
    h = int(hashlib.sha256(s.encode()).hexdigest()[:8], 16)
    return round(lo + (h % 1000) / 1000 * (hi - lo), 2)


def _canonical_id(kind: str, index: int) -> str:
    prefix = {"attacker": "P", "asset": "A", "defender": "D"}.get(kind, "N")
    return f"{prefix}-{index + 1:02d}"


def _map_ecosystem_nodes(
    payload_nodes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Map dataset-derived ecosystem nodes onto the reference layout.

    Returns canonical nodes plus an ``original_id -> canonical_id`` map.
    """
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for n in payload_nodes:
        by_kind.setdefault(n.get("kind", "asset"), []).append(n)

    original_to_canonical: dict[str, str] = {}
    canonical_nodes: list[dict[str, Any]] = []

    fallback_x = {
        "attacker": 80,
        "asset": 560,
        "defender": 1230,
    }

    for kind in ("attacker", "asset", "defender"):
        for i, n in enumerate(by_kind.get(kind, [])):
            orig_id = n.get("id") or n.get("name") or f"{kind}-{i}"
            if (kind == "asset" and i < 9) or (kind != "asset" and i < 4):
                canonical_id = _canonical_id(kind, i)
                ref = ECO_NODES[canonical_id]
                x, y = ref["x"], ref["y"]
            else:
                canonical_id = f"{kind}-{i + 1:02d}"
                x = fallback_x.get(kind, 560)
                y = 110 + i * 80

            original_to_canonical[orig_id] = canonical_id
            canonical_nodes.append(
                {
                    "id": canonical_id,
                    "name": n.get("name") or n.get("id") or canonical_id,
                    "kind": kind,
                    "x": x,
                    "y": y,
                    "compromised": bool(n.get("compromised")),
                    "original_id": orig_id,
                }
            )

    return canonical_nodes, original_to_canonical


def _map_ecosystem_edges(
    payload_edges: list[dict[str, Any]],
    original_to_canonical: dict[str, str],
) -> list[dict[str, Any]]:
    """Map payload edges to canonical IDs and merge with the reference topology."""
    canonical_ids = set(original_to_canonical.values())

    payload_by_key: dict[str, dict[str, Any]] = {}
    for e in payload_edges:
        orig_from = e.get("from", "")
        orig_to = e.get("to", "")
        from_id = original_to_canonical.get(orig_from)
        to_id = original_to_canonical.get(orig_to)
        if not from_id or not to_id:
            continue
        key = f"{from_id}->{to_id}"
        is_attack = e.get("kind") == "attacks" or e.get("attack") is True
        deviation = e.get("deviation")
        if deviation is None and is_attack:
            deviation = _hash_float(f"{from_id}->{to_id}")
        payload_by_key[key] = {
            "from": from_id,
            "to": to_id,
            "attack": is_attack,
            "deviation": deviation,
            "weight": e.get("weight", 1.0),
        }

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for e in ECO_EDGES:
        from_id = str(e["from"])
        to_id = str(e["to"])
        if from_id not in canonical_ids or to_id not in canonical_ids:
            continue
        key = f"{from_id}->{to_id}"
        seen.add(key)
        if key in payload_by_key:
            merged.append(payload_by_key[key])
        else:
            merged.append(
                {
                    "from": from_id,
                    "to": to_id,
                    "attack": bool(e.get("attack", False)),
                    "deviation": e.get("deviation"),
                    "weight": 1.0,
                }
            )

    for key, e in payload_by_key.items():
        if key not in seen:
            seen.add(key)
            merged.append(e)

    return merged


CANONICAL_ATTACK_ORDER = ["P-01->A-01", "P-02->A-06", "P-03->A-04", "P-04->A-08"]


def _map_attack_schedule(
    attack_edges: list[dict[str, Any]],
) -> dict[str, str]:
    """Map the canonical reference attack edges onto the real dataset-derived edges.

    Returns ``canonical_edge_id -> actual_edge_id``.  The first real attack edge
    takes the first canonical slot, the second the second slot, and so on.  This
    lets the reference step schedule animate real attack paths while keeping the
    canonical node positions used by the UI.
    """

    def _sort_key(e: dict[str, Any]) -> tuple[int, int]:
        return (
            int(e["from"].split("-")[1]) if "-" in e["from"] else 0,
            int(e["to"].split("-")[1]) if "-" in e["to"] else 0,
        )

    sorted_edges = sorted(attack_edges, key=_sort_key)
    mapping: dict[str, str] = {}
    for i, canonical in enumerate(CANONICAL_ATTACK_ORDER):
        if i < len(sorted_edges):
            e = sorted_edges[i]
            mapping[canonical] = f"{e['from']}->{e['to']}"
    return mapping


def _translate_edge_list(edge_ids: list[str], mapping: dict[str, str]) -> list[str]:
    return [mapping[eid] for eid in edge_ids if eid in mapping]


def _translate_compromised(
    node_ids: list[str], mapping: dict[str, str], actual_node_ids: set[str]
) -> list[str]:
    """Translate canonical compromised asset IDs to actual asset IDs."""
    result: set[str] = set()
    for canonical in node_ids:
        matched = next(
            (actual for c, actual in mapping.items() if c.endswith(f"->{canonical}")),
            None,
        )
        if matched:
            target = matched.split("->")[1]
            if target in actual_node_ids:
                result.add(target)
        elif canonical in actual_node_ids:
            result.add(canonical)
    return sorted(result)


def _compute_step_state(
    mode: str,
    step: int,
    attack_edges: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    defenders: list[dict[str, Any]],
    actual_node_ids: set[str],
) -> tuple[list[str], list[str], list[str], int, str | None]:
    """Compute compromised, blocked, live, health, and note for the given step.

    Uses the reference step schedules as the simulation narrative and maps them
    onto the dataset-derived attack edges so the graph changes in sync with the
    real artifact while preserving the reference visual behavior.
    """
    step = max(0, min(8, step))
    mode = "CONTAIN" if mode.upper() == "CONTAIN" else "IGNORE"

    schedule = (ECO_CONTAIN_STEPS if mode == "CONTAIN" else ECO_IGNORE_STEPS)[step]
    mapping = _map_attack_schedule(attack_edges)

    live = _translate_edge_list(schedule.get("liveAttacks", []), mapping)
    blocked = _translate_edge_list(schedule.get("blockedEdges", []), mapping)
    compromised = _translate_compromised(schedule.get("compromised", []), mapping, actual_node_ids)
    note = schedule.get("note")

    asset_count = len(assets)
    defended_count = len(blocked)
    compromised_count = len(compromised)
    health = max(
        0,
        min(
            99,
            round(
                ((asset_count - compromised_count) / max(asset_count, 1)) * 74 + defended_count * 3
            ),
        ),
    )

    return (
        sorted(compromised),
        blocked,
        live,
        health,
        note,
    )


@router.get("/simulation/ecosystem")
def get_ecosystem(
    mode: str = "CONTAIN",
    step: int = Query(default=0, ge=0, le=8),
    project_id: str = "",
    session: Session = Depends(get_session),
) -> dict:
    """Return a step-specific threat ecosystem simulation state.

    When ``project_id`` is provided, the state is derived from the latest
    generated ecosystem artifact for that project. Otherwise an empty state is
    returned so callers that do not yet have a project context do not display
    stale demo data.
    """
    empty = {
        "nodes": [],
        "edges": [],
        "step": step,
        "mode": mode,
        "compromised": [],
        "blockedEdges": [],
        "liveAttacks": [],
        "health": 0,
        "note": "Select a project to generate a dataset-derived ecosystem.",
    }

    if not project_id:
        return empty

    artifact = session.exec(
        select(ProjectArtifact)
        .where(
            ProjectArtifact.project_id == project_id,
            ProjectArtifact.artifact_type == "ecosystem",
        )
        .order_by(ProjectArtifact.created_at.desc())
    ).first()

    if not artifact:
        return empty

    payload = session.exec(
        select(ProjectArtifactPayload).where(
            ProjectArtifactPayload.artifact_id == artifact.artifact_id,
            ProjectArtifactPayload.artifact_type == "ecosystem",
        )
    ).first()

    if not payload:
        return empty

    try:
        data = json.loads(payload.payload_json)
    except json.JSONDecodeError:
        return empty

    nodes, original_to_canonical = _map_ecosystem_nodes(data.get("nodes", []))
    edges = _map_ecosystem_edges(data.get("edges", []), original_to_canonical)

    payload_compromised: set[str] = {
        canonical_id
        for n in data.get("nodes", [])
        if n.get("compromised")
        and (canonical_id := original_to_canonical.get(n.get("id") or n.get("name")))
    }
    for n in nodes:
        n["compromised"] = n["id"] in payload_compromised

    attack_edges = [e for e in edges if e.get("attack")]
    assets = [n for n in nodes if n["kind"] == "asset"]
    defenders = [n for n in nodes if n["kind"] == "defender"]
    actual_node_ids = {n["id"] for n in nodes}

    compromised, blocked, live, health, note = _compute_step_state(
        mode, step, attack_edges, assets, defenders, actual_node_ids
    )

    compromised = sorted(set(compromised) | payload_compromised)

    return {
        "nodes": nodes,
        "edges": edges,
        "step": step,
        "mode": mode,
        "compromised": compromised,
        "blockedEdges": blocked,
        "liveAttacks": live,
        "health": health,
        "note": note,
        "viewW": ECO_REF_VIEW_W,
        "viewH": ECO_REF_VIEW_H,
    }
