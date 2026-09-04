"""Graph data API router for visualization."""

from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from anvaya.db import get_session
from anvaya.models.graph import BlastRadiusResult, GraphEdge, GraphNode

router = APIRouter()


@router.get("/graph/segments")
def get_segments(session: Session = Depends(get_session)) -> dict:
    """Get ranked network segments for Segments page.

    Derived from the most recent BlastScope propagation paths. Returns an
    empty result when no blast radius exists yet.
    """
    blast = session.exec(
        select(BlastRadiusResult).order_by(BlastRadiusResult.computed_at.desc())
    ).first()
    if blast:
        incident_id = blast.incident_id
        paths = json.loads(blast.propagation_paths_json or "[]")
        nodes = session.exec(select(GraphNode).where(GraphNode.incident_id == incident_id)).all()
        prefix = f"{incident_id}-"
        node_map = {n.node_id.removeprefix(prefix): n for n in nodes}

        items = []
        rank = 1
        for path in paths:
            for i in range(len(path) - 1):
                src = path[i]
                dst = path[i + 1]
                dst_node = node_map.get(dst)
                if dst_node is None:
                    continue

                if dst_node.is_compromised:
                    risk = "critical"
                elif dst_node.is_critical:
                    risk = "high"
                elif dst_node.impact_score >= 0.6:
                    risk = "medium"
                else:
                    risk = "low"

                traffic = round(min(max(dst_node.impact_score, 0.1), 0.95), 2)
                items.append(
                    {
                        "id": f"SEG-{rank:03d}",
                        "from": src,
                        "to": dst,
                        "rank": rank,
                        "depth": i + 1,
                        "reach": len(path) - i - 1,
                        "traffic": traffic,
                        "risk": risk,
                        "neutralized": dst_node.state == "neutralized",
                    }
                )
                rank += 1
        return {"items": items, "incident_id": incident_id, "nodes": [], "extra_edges": []}

    return {"items": [], "incident_id": "", "nodes": [], "extra_edges": []}


@router.get("/graph/reachability")
def get_reachability(session: Session = Depends(get_session)) -> dict:
    """Get asset reachability data for Reach Board.

    Derived from the most recent BlastScope run. Returns an empty result
    when no blast radius exists yet.
    """
    blast = session.exec(
        select(BlastRadiusResult).order_by(BlastRadiusResult.computed_at.desc())
    ).first()
    if blast:
        incident_id = blast.incident_id
        nodes = session.exec(select(GraphNode).where(GraphNode.incident_id == incident_id)).all()
        edges = session.exec(select(GraphEdge).where(GraphEdge.incident_id == incident_id)).all()

        adjacency: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            adjacency[edge.source_node_id].append(edge.target_node_id)

        items = []
        for node in nodes:
            if node.is_compromised:
                state = "COMPROMISED"
            elif node.is_critical:
                state = "CRITICAL"
            else:
                state = "REACHABLE"
            attack = round(node.impact_score, 2)
            defense = round(max(0.0, 1.0 - attack), 2)
            items.append(
                {
                    "id": node.node_id,
                    "name": node.label,
                    "state": state,
                    "hops": node.depth,
                    "attackScore": attack,
                    "defenseScore": defense,
                    "adjacent": adjacency.get(node.node_id, []),
                }
            )
        return {"items": items, "incident_id": incident_id}

    return {"items": [], "incident_id": ""}


@router.get("/graph/{incident_id}")
def get_graph(incident_id: str, session: Session = Depends(get_session)) -> dict:
    nodes_stmt = select(GraphNode).where(GraphNode.incident_id == incident_id)
    edges_stmt = select(GraphEdge).where(GraphEdge.incident_id == incident_id)
    blast_stmt = select(BlastRadiusResult).where(BlastRadiusResult.incident_id == incident_id)

    nodes = session.exec(nodes_stmt).all()
    edges = session.exec(edges_stmt).all()
    blast = session.exec(blast_stmt).first()

    return {
        "nodes": [n.model_dump() for n in nodes],
        "edges": [e.model_dump() for e in edges],
        "blast_radius": blast.model_dump() if blast else None,
    }


@router.get("/graph/{incident_id}/nodes")
def get_nodes(incident_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(GraphNode).where(GraphNode.incident_id == incident_id)
    nodes = session.exec(stmt).all()
    return {"items": [n.model_dump() for n in nodes]}


@router.get("/graph/{incident_id}/edges")
def get_edges(incident_id: str, session: Session = Depends(get_session)) -> dict:
    stmt = select(GraphEdge).where(GraphEdge.incident_id == incident_id)
    edges = session.exec(stmt).all()
    return {"items": [e.model_dump() for e in edges]}
