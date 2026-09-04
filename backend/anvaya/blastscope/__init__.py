"""BlastScope engine — NetworkX graph traversal and blast-radius simulation."""

from __future__ import annotations

import json
from typing import Any

import networkx as nx
from sqlmodel import Session, select

from anvaya.models.asset import Asset, AssetRelationship
from anvaya.models.graph import BlastRadiusResult, GraphEdge, GraphNode
from anvaya.models.incident import Incident


class BlastScopeEngine:
    """NetworkX-based blast-radius computation engine."""

    def __init__(self, session: Session):
        self.session = session

    def build_graph(self, incident_id: str) -> nx.DiGraph:
        """Build a NetworkX graph from asset relationships for an incident."""
        G = nx.DiGraph()

        assets = self.session.exec(select(Asset)).all()
        for asset in assets:
            G.add_node(
                asset.asset_id,
                label=asset.name,
                node_type=asset.asset_type.value
                if hasattr(asset.asset_type, "value")
                else str(asset.asset_type),
                is_critical=asset.is_critical,
                is_compromised=asset.is_compromised,
                is_neutralized=asset.is_neutralized,
                ip=asset.ip_address,
                hostname=asset.hostname,
            )

        rels = self.session.exec(select(AssetRelationship)).all()
        for rel in rels:
            G.add_edge(
                rel.source_asset_id,
                rel.target_asset_id,
                relationship_type=rel.relationship_type,
                is_observed=rel.is_observed,
                is_simulated=rel.is_simulated,
                weight=rel.weight,
            )

        return G

    def run(self, incident_id: str) -> dict[str, Any]:
        """Run blast-radius analysis for an incident."""
        incident = self.session.exec(
            select(Incident).where(Incident.incident_id == incident_id)
        ).first()
        if not incident:
            return {"error": "Incident not found"}

        G = self.build_graph(incident_id)

        compromised_host = incident.host
        origin_node = None
        for node_id, data in G.nodes(data=True):
            if (
                data.get("hostname") == compromised_host
                or data.get("label") == compromised_host
                or node_id == compromised_host
            ):
                origin_node = node_id
                break

        if origin_node is None:
            origin_node = f"ORIGIN-{incident_id}"
            G.add_node(
                origin_node,
                label=compromised_host,
                node_type="host",
                is_critical=False,
                is_compromised=True,
                is_neutralized=False,
            )

        G.nodes[origin_node]["is_compromised"] = True

        reachable = set()
        if G.has_node(origin_node):
            reachable = set(nx.descendants(G, origin_node))
        reachable.add(origin_node)

        max_depth = 0
        paths: list[list[str]] = []
        for target in reachable:
            if target == origin_node:
                continue
            try:
                path = nx.shortest_path(G, origin_node, target)
                depth = len(path) - 1
                max_depth = max(max_depth, depth)
                paths.append(path)
            except nx.NetworkXNoPath:
                pass

        critical_exposed = sum(1 for n in reachable if G.nodes[n].get("is_critical", False))

        total_critical = sum(1 for _, d in G.nodes(data=True) if d.get("is_critical", False))
        critical_ratio = critical_exposed / total_critical if total_critical > 0 else 0
        reach_ratio = len(reachable) / G.number_of_nodes() if G.number_of_nodes() > 0 else 0
        impact_score = critical_ratio * 0.6 + reach_ratio * 0.3 + min(max_depth / 5, 1.0) * 0.1

        self._persist_graph(incident_id, G, reachable, origin_node)

        existing = self.session.exec(
            select(BlastRadiusResult).where(BlastRadiusResult.incident_id == incident_id)
        ).first()
        if existing:
            self.session.delete(existing)
            self.session.commit()

        blast = BlastRadiusResult(
            incident_id=incident_id,
            total_reachable=len(reachable),
            critical_exposed=critical_exposed,
            max_depth=max_depth,
            impact_score=round(impact_score, 4),
            reachable_assets_json=json.dumps(list(reachable)),
            propagation_paths_json=json.dumps(paths[:20]),
        )
        self.session.add(blast)

        incident.blast_radius_score = round(impact_score, 4)
        self.session.add(incident)
        self.session.commit()

        return {
            "incident_id": incident_id,
            "origin_node": origin_node,
            "total_reachable": len(reachable),
            "critical_exposed": critical_exposed,
            "max_depth": max_depth,
            "impact_score": round(impact_score, 4),
            "reachable_assets": list(reachable),
            "propagation_paths": paths[:20],
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
        }

    def _persist_graph(
        self, incident_id: str, G: nx.DiGraph, reachable: set[str], origin_node: str
    ) -> None:
        """Persist graph nodes and edges to database."""
        existing_nodes = self.session.exec(
            select(GraphNode).where(GraphNode.incident_id == incident_id)
        ).all()
        for n in existing_nodes:
            self.session.delete(n)

        existing_edges = self.session.exec(
            select(GraphEdge).where(GraphEdge.incident_id == incident_id)
        ).all()
        for e in existing_edges:
            self.session.delete(e)
        self.session.commit()

        for node_id, data in G.nodes(data=True):
            is_compromised = node_id in reachable
            depth = 0
            if node_id != origin_node and node_id in reachable:
                try:
                    depth = len(nx.shortest_path(G, origin_node, node_id)) - 1
                except nx.NetworkXNoPath:
                    depth = 0

            gn = GraphNode(
                node_id=f"{incident_id}-{node_id}",
                incident_id=incident_id,
                label=data.get("label", node_id),
                node_type=data.get("node_type", "host"),
                state="compromised"
                if is_compromised
                else ("critical" if data.get("is_critical") else "normal"),
                is_compromised=is_compromised,
                is_critical=data.get("is_critical", False),
                depth=depth,
                impact_score=impact_score_for_node(data, is_compromised, depth),
                blast_contribution=0.1 if is_compromised else 0.0,
            )
            self.session.add(gn)

        for u, v, data in G.edges(data=True):
            ge = GraphEdge(
                incident_id=incident_id,
                source_node_id=f"{incident_id}-{u}",
                target_node_id=f"{incident_id}-{v}",
                edge_type=data.get("relationship_type", "network"),
                is_observed=data.get("is_observed", False),
                is_simulated=data.get("is_simulated", False),
                is_possible=not data.get("is_observed", False),
                weight=data.get("weight", 1.0),
            )
            self.session.add(ge)
        self.session.commit()

    def get_result(self, incident_id: str) -> dict[str, Any]:
        """Get persisted blast-radius result."""
        blast = self.session.exec(
            select(BlastRadiusResult).where(BlastRadiusResult.incident_id == incident_id)
        ).first()
        if not blast:
            return {"error": "No blast-radius result found. Run analysis first."}
        return blast.model_dump()


def impact_score_for_node(data: dict, is_compromised: bool, depth: int) -> float:
    """Compute impact score for a node."""
    base = 0.8 if data.get("is_critical", False) else 0.3
    if is_compromised:
        base = min(base + 0.2, 1.0)
    depth_penalty = max(0, 0.1 * (5 - depth)) if is_compromised else 0
    return round(min(base + depth_penalty, 1.0), 4)
