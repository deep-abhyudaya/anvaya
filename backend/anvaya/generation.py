"""Dataset-driven artifact generation for ANVAYA projects.

All artifacts are projections of a single canonical WorldModel derived from the
dataset's schema profile. No artifact is an independent fabrication.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd
from sqlmodel import Session, delete, select

from anvaya.config import settings
from anvaya.dataset_profile import build_dataset_profile
from anvaya.logging import get_logger
from anvaya.models.enums import IncidentStatus
from anvaya.models.graph import BlastRadiusResult, GraphEdge, GraphNode
from anvaya.models.incident import Incident
from anvaya.models.project import (
    ARTIFACT_TYPES,
    Dataset,
    Generation,
    Project,
    ProjectArtifact,
    ProjectArtifactPayload,
)
from anvaya.models.replay import ReplayRun
from anvaya.world import WorldModel, build_world_model

logger = get_logger("anvaya.generation")


def _timestamp_from_str(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


class ArtifactGenerator:
    """Generate project artifacts from a dataset using a canonical world model."""

    def __init__(
        self,
        session: Session,
        project: Project,
        generation: Generation,
        dataset: Dataset | None = None,
        progress_callback: Any | None = None,
    ):
        self.session = session
        self.project = project
        self.generation = generation
        self.dataset = dataset
        self._df: pd.DataFrame | None = None
        self._profile: Any | None = None
        self._world: WorldModel | None = None
        self._progress_callback = progress_callback

    def generate_all(self, requested: list[str]) -> dict[str, int]:
        """Generate all requested artifact types and return counts."""
        created: dict[str, int] = {}

        if any(t in requested for t in ARTIFACT_TYPES):
            try:
                self._progress("artifact.world_build_started", "Building canonical world model")
                self._ensure_world()
                self._progress(
                    "artifact.world_build_completed",
                    "World model built",
                    {
                        "entities": len(self._world.entities) if self._world else 0,
                        "events": len(self._world.telemetry) if self._world else 0,
                        "incidents": len(self._world.incidents) if self._world else 0,
                    },
                )
            except Exception as exc:
                logger.error(
                    "world_model_build_failed",
                    generation_id=self.generation.generation_id,
                    error=str(exc),
                )
                self.generation.status = "failed"
                self.generation.error_message = f"World model build failed: {exc}"
                self.session.add(self.generation)
                self.session.commit()
                raise

        failures: dict[str, str] = {}
        for artifact_type in requested:
            if artifact_type not in ARTIFACT_TYPES:
                continue
            self._progress(
                "artifact.generating",
                f"Generating {artifact_type}",
                {"artifact_type": artifact_type},
            )
            try:
                count = self._generate_one(artifact_type)
                created[artifact_type] = count
                self._progress(
                    "artifact.saved",
                    f"Saved {artifact_type}",
                    {"artifact_type": artifact_type, "count": count},
                )
            except Exception as exc:
                logger.warning(
                    "artifact_generation_failed",
                    artifact_type=artifact_type,
                    generation_id=self.generation.generation_id,
                    error=str(exc),
                )
                created[artifact_type] = 0
                failures[artifact_type] = str(exc)

        if failures:
            details = "; ".join(f"{name}: {error}" for name, error in failures.items())
            raise RuntimeError(f"Artifact generation failed: {details}")

        if self._world and self._world.incidents:
            if "incidents" in requested:
                self._persist_incidents()
            if "replay" in requested:
                self._persist_replays()

        return created

    def _progress(self, event_type: str, label: str, payload: Any | None = None) -> None:
        if self._progress_callback:
            try:
                self._progress_callback(event_type, label, payload or {})
            except Exception:
                pass

    def _ensure_world(self) -> None:
        if self._world is not None:
            return
        df = self._load_df()
        if df is None or df.empty:
            raise ValueError("No usable dataset found for artifact generation")

        dataset_id = self.dataset.dataset_id if self.dataset else ""
        self._profile = build_dataset_profile(df, dataset_id)
        self._world = build_world_model(
            df,
            self._profile,
            self.project.project_id,
            dataset_id,
            self.generation.generation_id,
        )

    def _load_df(self) -> pd.DataFrame | None:
        if self._df is not None:
            return self._df

        if self.dataset:
            df = self._load_dataset(self.dataset)
            if df is not None:
                self._df = df
                return df

        datasets = self.session.exec(
            select(Dataset).where(
                Dataset.project_id == self.project.project_id,
                Dataset.status == "ready",
            )
        ).all()
        dfs = [self._load_dataset(d) for d in datasets if d.status == "ready"]
        dfs = [d for d in dfs if d is not None]
        if not dfs:
            return None

        self._df = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
        return self._df

    def _load_dataset(self, dataset: Dataset) -> pd.DataFrame | None:
        path = self._resolve_path(dataset)
        if not path:
            return None
        try:
            if dataset.format == "csv":
                return pd.read_csv(path)
            if dataset.format == "jsonl":
                return pd.read_json(path, lines=True)
            if dataset.format == "json":
                return pd.read_json(path)
            if dataset.format == "parquet":
                return pd.read_parquet(path)
        except Exception as exc:
            logger.warning(
                "dataset_load_failed",
                dataset_id=dataset.dataset_id,
                error=str(exc),
            )
        return None

    def _resolve_path(self, dataset: Dataset) -> Path | None:
        src = dataset.source or ""
        path = Path(src) if src else (settings.datasets_dir / f"{dataset.dataset_id}")
        if path.exists():
            return path
        for ext in (".csv", ".json", ".jsonl", ".parquet"):
            candidate = settings.datasets_dir / f"{dataset.dataset_id}{ext}"
            if candidate.exists():
                return candidate
        return None

    def _generate_one(self, artifact_type: str) -> int:
        if artifact_type in {"orbits", "reach", "segments"}:
            return self._generate_graph_artifact(artifact_type)

        if artifact_type == "incidents":
            payload = self._build_incidents_payload()
        elif artifact_type == "trophy_wall":
            payload = self._build_trophy_payload()
        elif artifact_type == "arena":
            payload = self._build_arena_payload()
        elif artifact_type == "ecosystem":
            payload = self._build_ecosystem_payload()
        elif artifact_type == "arbor":
            payload = self._build_arbor_payload()
        elif artifact_type == "impacts":
            payload = self._build_impacts_payload()
        elif artifact_type == "replay":
            payload = self._build_replay_payload()
        elif artifact_type == "ledger":
            payload = self._build_ledger_payload()
        else:
            payload = {
                "artifact_type": artifact_type,
                "dataset_id": self.dataset.dataset_id if self.dataset else "",
                "row_count": len(self._df) if self._df is not None else 0,
            }

        artifact_id = f"{self.generation.generation_id}-{artifact_type}"
        self._save_artifact(artifact_type, artifact_id, payload)
        return 1

    def _build_provenance(self) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        profile = self._profile
        return {
            "dataset_id": self.dataset.dataset_id if self.dataset else "",
            "dataset_fingerprint": profile.fingerprint if profile else "",
            "generation_id": self.generation.generation_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "generator_version": "anvaya-2026.1",
            "schema_version": "1.0",
            "source_artifact_ids": [],
            "events_used": len(world.telemetry) if world else 0,
            "edges_derived": len(world.edges) if world else 0,
            "incidents_derived": len(world.incidents) if world else 0,
            "rows": len(self._df) if self._df is not None else 0,
        }

    def _generate_graph_artifact(self, artifact_type: str) -> int:
        """Generate orbits, reach, or segments from the world model graph."""
        world = self._world
        if not world:
            raise ValueError("World model not built")

        g = nx.DiGraph()
        for edge in world.edges:
            if g.has_edge(edge.source, edge.target):
                g[edge.source][edge.target]["weight"] += edge.weight
            else:
                g.add_edge(edge.source, edge.target, weight=edge.weight)

        scope = f"GEN-{self.generation.generation_id}"

        self.session.exec(
            delete(GraphNode).where(GraphNode.__table__.c.incident_id == scope)
        )
        self.session.exec(
            delete(GraphEdge).where(GraphEdge.__table__.c.incident_id == scope)
        )
        self.session.exec(
            delete(BlastRadiusResult).where(BlastRadiusResult.__table__.c.incident_id == scope)
        )

        node_map: dict[str, GraphNode] = {}
        all_nodes = set()
        for edge in world.edges:
            all_nodes.add(edge.source)
            all_nodes.add(edge.target)

        degrees = dict(g.degree())
        in_degrees = dict(g.in_degree())
        out_degrees = dict(g.out_degree())
        max_degree = max(degrees.values(), default=1)
        origin = max(all_nodes, key=lambda node: degrees.get(node, 0), default=None)

        for node_id in sorted(all_nodes):
            safe_id = f"{scope}-{node_id}"
            deg = degrees.get(node_id, 0)
            impact = round(min(1.0, deg / max(max_degree, 1)), 4)
            try:
                depth = nx.shortest_path_length(g, origin, node_id) if origin else 0
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                depth = 0
            node = GraphNode(
                node_id=safe_id,
                incident_id=scope,
                label=node_id,
                node_type="host",
                state="compromised"
                if any(o.source == node_id and o.risk_score > 0.8 for o in world.orbits)
                else "normal",
                is_compromised=any(
                    o.source == node_id and o.risk_score > 0.8 for o in world.orbits
                ),
                is_critical=impact >= 0.6,
                depth=depth,
                impact_score=impact,
                blast_contribution=impact,
                metadata_json=json.dumps(
                    {
                        "degree": deg,
                        "in_degree": in_degrees.get(node_id, 0),
                        "out_degree": out_degrees.get(node_id, 0),
                    }
                ),
            )
            self.session.add(node)
            node_map[node_id] = node

        for edge in world.edges:
            if edge.source not in node_map or edge.target not in node_map:
                continue
            gedge = GraphEdge(
                incident_id=scope,
                source_node_id=node_map[edge.source].node_id,
                target_node_id=node_map[edge.target].node_id,
                edge_type=edge.kind,
                is_observed=edge.observed,
                is_simulated=False,
                is_possible=False,
                weight=round(min(1.0, edge.weight / 20.0), 4) if edge.weight else 1.0,
                metadata_json=json.dumps(edge.properties),
            )
            self.session.add(gedge)

        paths: list[list[str]] = []
        top_nodes = sorted(all_nodes, key=lambda n: degrees.get(n, 0), reverse=True)[:15]
        for src in top_nodes:
            for dst in top_nodes:
                if src == dst:
                    continue
                try:
                    for p in nx.all_simple_paths(g, src, dst, cutoff=3):
                        paths.append(p)
                        if len(paths) > 200:
                            break
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass
                if len(paths) > 200:
                    break
            if len(paths) > 200:
                break

        blast = BlastRadiusResult(
            incident_id=scope,
            total_reachable=len(all_nodes),
            critical_exposed=len([n for n in node_map.values() if n.impact_score >= 0.6]),
            max_depth=min(3, max((len(p) - 1 for p in paths), default=0)),
            impact_score=round(len(world.edges) / max(len(all_nodes), 1), 4),
            reachable_assets_json=json.dumps(
                [node_map[n].node_id for n in top_nodes if n in node_map]
            ),
            propagation_paths_json=json.dumps(paths),
        )
        self.session.add(blast)

        if artifact_type == "orbits":
            payload = self._build_orbits_payload(node_map, blast)
        elif artifact_type == "reach":
            payload = self._build_reach_payload(node_map, g, blast)
        elif artifact_type == "segments":
            payload = self._build_segments_payload(node_map, blast)
        else:
            payload = {"error": "unknown graph artifact"}

        artifact_id = f"{self.generation.generation_id}-{artifact_type}"
        self._save_artifact(artifact_type, artifact_id, payload)
        self.session.commit()
        return 1

    def _build_orbits_payload(
        self, node_map: dict[str, GraphNode], blast: BlastRadiusResult
    ) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        orbits = []
        for o in world.orbits[:50]:
            orbits.append(
                {
                    "orbit_id": f"ORB-{o.source}-{o.target}",
                    "source": o.source,
                    "target": o.target,
                    "forward_count": o.forward_count,
                    "reverse_count": o.reverse_count,
                    "interaction_strength": o.interaction_strength,
                    "risk_score": o.risk_score,
                    "risk_basis": o.risk_basis,
                    "event_count": o.event_count,
                    "incident_ids": o.incident_ids,
                    "first_seen": o.first_seen,
                    "last_seen": o.last_seen,
                    "dataset_id": world.dataset_id,
                    "generation_id": world.generation_id,
                }
            )

        top_nodes = sorted(
            node_map.values(),
            key=lambda n: n.impact_score,
            reverse=True,
        )[:20]

        return {
            "artifact_type": "orbits",
            "scope": f"GEN-{self.generation.generation_id}",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            "node_count": len(node_map),
            "edge_count": len(world.edges),
            "top_nodes": [
                {
                    "id": n.label,
                    "label": n.label,
                    "impact_score": n.impact_score,
                    "is_compromised": n.is_compromised,
                }
                for n in top_nodes
            ],
            "orbits": orbits,
            "blast_radius": json.loads(blast.model_dump_json()),
            "provenance": self._build_provenance(),
        }

    def _build_reach_payload(
        self, node_map: dict[str, GraphNode], g: nx.DiGraph, blast: BlastRadiusResult
    ) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        items = []
        for node_id, node in node_map.items():
            try:
                reachable = list(nx.descendants(g, node_id))
            except Exception:
                reachable = []
            items.append(
                {
                    "id": node.node_id,
                    "name": node.label,
                    "state": "CRITICAL"
                    if node.is_critical
                    else ("COMPROMISED" if node.is_compromised else "REACHABLE"),
                    "hops": node.depth,
                    "attackScore": node.impact_score,
                    "defenseScore": round(max(0.0, 1.0 - node.impact_score), 2),
                    "adjacent": [node_map[r].node_id for r in reachable if r in node_map][:10],
                    "reachable_count": len(reachable),
                }
            )
        return {
            "artifact_type": "reach",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            "incident_id": blast.incident_id,
            "items": items,
            "provenance": self._build_provenance(),
        }

    def _build_segments_payload(
        self, node_map: dict[str, GraphNode], blast: BlastRadiusResult
    ) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        paths = json.loads(blast.propagation_paths_json or "[]")
        node_by_label = {n.label: n for n in node_map.values()}
        items = []
        rank = 1
        for path in paths:
            for i in range(len(path) - 1):
                src = path[i]
                dst = path[i + 1]
                dst_node = node_by_label.get(dst)
                if dst_node is None:
                    continue
                risk = (
                    "critical"
                    if dst_node.is_compromised
                    else (
                        "high"
                        if dst_node.is_critical
                        else ("medium" if dst_node.impact_score >= 0.4 else "low")
                    )
                )
                items.append(
                    {
                        "id": f"SEG-{rank:03d}",
                        "from": src,
                        "to": dst,
                        "rank": rank,
                        "depth": i + 1,
                        "reach": len(path) - i - 1,
                        "traffic": round(max(0.1, dst_node.impact_score), 2),
                        "risk": risk,
                        "neutralized": dst_node.state == "neutralized",
                    }
                )
                rank += 1
        nodes = [
            {
                "id": node.label,
                "x": 100 + (index % 5) * 150,
                "y": 100 + (index // 5) * 120,
                "kind": node.node_type,
            }
            for index, node in enumerate(node_map.values())
        ]
        return {
            "artifact_type": "segments",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            "incident_id": blast.incident_id,
            "items": items,
            "nodes": nodes,
            "extra_edges": [],
            "provenance": self._build_provenance(),
        }

    def _build_incidents_payload(self) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        return {
            "artifact_type": "incidents",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            "row_count": world.statistics["event_count"],
            "incident_count": len(world.incidents),
            "incidents": [self._incident_to_dict(inc) for inc in world.incidents[:50]],
            "provenance": self._build_provenance(),
            "fallback_used": world.statistics.get("fallback_used", False),
            "fallback_reason": world.statistics.get("fallback_reason"),
        }

    def _incident_to_dict(self, inc: Any) -> dict[str, Any]:
        return {
            "incident_id": inc.incident_id,
            "title": inc.title,
            "description": inc.description,
            "severity": inc.severity,
            "status": inc.status,
            "host": inc.host,
            "user": inc.user,
            "attack_family": inc.attack_family,
            "event_count": len(inc.event_ids),
            "event_ids": inc.event_ids,
            "first_seen": inc.first_seen,
            "last_seen": inc.last_seen,
            "blast_radius_score": inc.blast_radius_score,
            "risk_score": inc.risk_score,
            "severity_basis": inc.severity_basis,
            "risk_basis": inc.risk_basis,
            "blast_basis": inc.blast_basis,
        }

    def _build_trophy_payload(self) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        trophies = []
        for t in world.trophy_wall:
            trophies.append(
                {
                    "trophy_id": t.trophy_id,
                    "incident_id": t.incident_id,
                    "title": t.title,
                    "description": t.description,
                    "rarity": t.rarity,
                    "score": t.score,
                    "evidence": t.evidence,
                    "sealed_at": t.sealed_at,
                }
            )
        return {
            "artifact_type": "trophy_wall",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            "trophy_count": len(trophies),
            "trophies": trophies,
            "provenance": self._build_provenance(),
        }

    def _build_arena_payload(self) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        return {
            "artifact_type": "arena",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            **world.arena,
            "provenance": self._build_provenance(),
        }

    def _build_ecosystem_payload(self) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        compromised = [n["id"] for n in world.ecosystem_nodes if n["compromised"]]
        assets = [n for n in world.ecosystem_nodes if n["kind"] == "asset"]
        attackers = [n for n in world.ecosystem_nodes if n["kind"] == "attacker"]
        defenders = [n for n in world.ecosystem_nodes if n["kind"] == "defender"]
        defended_count = sum(1 for e in world.ecosystem_edges if e["kind"] == "blocked_by")
        health = max(
            0,
            min(
                99,
                round(
                    ((len(assets) - len(compromised)) / max(len(assets), 1)) * 74
                    + defended_count * 3
                ),
            ),
        )

        positioned: list[dict[str, Any]] = []
        for kind, start_x, pool in (
            ("attacker", 80, attackers),
            ("asset", 560, assets),
            ("defender", 1230, defenders),
        ):
            for i, node in enumerate(pool):
                positioned.append(
                    {
                        **node,
                        "x": start_x,
                        "y": 110 + i * 80,
                    }
                )

        mapped_edges = [
            {**e, "attack": e.get("kind") == "attacks"} for e in world.ecosystem_edges
        ]

        return {
            "artifact_type": "ecosystem",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            "health": health,
            "nodes": positioned,
            "edges": mapped_edges,
            "compromised": compromised,
            "provenance": self._build_provenance(),
        }

    def _build_arbor_payload(self) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        return {
            "artifact_type": "arbor",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            **world.arbor,
            "provenance": self._build_provenance(),
        }

    def _build_impacts_payload(self) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        return {
            "artifact_type": "impacts",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            "impacts": world.impacts,
            "provenance": self._build_provenance(),
        }

    def _build_replay_payload(self) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        return {
            "artifact_type": "replay",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            "replays": [
                {
                    "replay_id": r.replay_id,
                    "incident_id": r.incident_id,
                    "host": r.host,
                    "user": r.user,
                    "status": r.status,
                    "verified": r.verified,
                    "start_time": r.start_time,
                    "source_event_ids": r.source_event_ids,
                    "timeline": r.timeline,
                    "pre_note": r.pre_note,
                    "stages": [
                        {
                            "name": s.name,
                            "start": s.start,
                            "duration": s.duration,
                            "events": s.events,
                        }
                        for s in r.stages
                    ],
                    "pre_state": r.pre_state,
                    "post_state": r.post_state,
                    "rule_before": r.rule_before,
                    "rule_after": r.rule_after,
                    "detection_before": r.detection_before,
                    "detection_after": r.detection_after,
                    "ground_truth": r.ground_truth,
                    "risk_delta": r.risk_delta,
                    "duration": r.duration,
                }
                for r in world.replay_scenarios
            ],
            "provenance": self._build_provenance(),
        }

    def _build_ledger_payload(self) -> dict[str, Any]:
        world = self._world
        if not world:
            raise ValueError("World model not built")
        try:
            requested = json.loads(self.generation.requested_artifacts_json or "[]")
        except json.JSONDecodeError:
            requested = []
        records = [dict(record) for record in world.ledger]
        if records and records[0].get("action") == "artifact_generated":
            records[0]["artifact_count"] = len(
                [name for name in requested if name in ARTIFACT_TYPES]
            )
        return {
            "artifact_type": "ledger",
            "dataset_id": world.dataset_id,
            "fingerprint": world.fingerprint,
            "records": records,
            "provenance": self._build_provenance(),
        }

    def _validate_payload(self, artifact_type: str, payload: dict[str, Any]) -> None:
        required: dict[str, tuple[str, ...]] = {
            "incidents": ("incidents", "incident_count"),
            "arbor": ("tree", "columns"),
            "impacts": ("impacts",),
            "reach": ("items", "incident_id"),
            "replay": ("replays",),
            "ecosystem": ("nodes", "edges", "health", "compromised"),
            "arena": ("stages", "engines", "severity", "consensus"),
            "orbits": ("orbits", "node_count", "edge_count", "blast_radius"),
            "segments": ("items", "nodes", "extra_edges"),
            "trophy_wall": ("trophies", "trophy_count"),
            "ledger": ("records",),
        }
        missing = [key for key in required[artifact_type] if key not in payload]
        common_missing = [
            key
            for key in ("artifact_type", "dataset_id", "fingerprint", "provenance")
            if key not in payload
        ]
        if missing or common_missing:
            fields = ", ".join(missing + common_missing)
            raise ValueError(f"Invalid {artifact_type} payload; missing: {fields}")
        if payload["artifact_type"] != artifact_type:
            raise ValueError(f"Invalid artifact_type for {artifact_type}")
        if payload["dataset_id"] != (self.dataset.dataset_id if self.dataset else ""):
            raise ValueError(f"Invalid dataset_id for {artifact_type}")

    def _save_artifact(self, artifact_type: str, artifact_id: str, payload: dict[str, Any]) -> None:
        """Validate and persist the artifact index and payload."""
        self._validate_payload(artifact_type, payload)
        pa = ProjectArtifact(
            project_id=self.project.project_id,
            dataset_id=self.dataset.dataset_id if self.dataset else "",
            generation_id=self.generation.generation_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
        )
        self.session.add(pa)

        pap = ProjectArtifactPayload(
            project_id=self.project.project_id,
            dataset_id=self.dataset.dataset_id if self.dataset else "",
            generation_id=self.generation.generation_id,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            payload_json=json.dumps(payload, default=str),
        )
        self.session.add(pap)

        try:
            created = json.loads(self.generation.created_artifacts_json or "{}")
        except json.JSONDecodeError:
            created = {}
        created[artifact_type] = created.get(artifact_type, 0) + 1
        self.generation.created_artifacts_json = json.dumps(created)
        self.session.add(self.generation)
        self.session.commit()

    def _persist_incidents(self) -> None:
        """Persist derived incidents as first-class Incident rows."""
        world = self._world
        if not world:
            return
        for inc in world.incidents:
            existing = self.session.exec(
                select(Incident).where(Incident.incident_id == inc.incident_id)
            ).first()
            if existing:
                continue
            incident = Incident(
                incident_id=inc.incident_id,
                title=inc.title,
                description=inc.description,
                status=IncidentStatus.DETECTED,
                severity=inc.severity,
                attack_family=inc.attack_family,
                scenario_id=world.dataset_id,
                scenario_seed=0,
                host=inc.host,
                user=inc.user,
                blast_radius_score=inc.blast_radius_score,
                risk_score=inc.risk_score,
                event_count=len(inc.event_ids),
                evidence_summary=f"{len(inc.event_ids)} events",
            )
            incident.transition_to(IncidentStatus.ACTIVE)
            self.session.add(incident)
        self.session.commit()

    def _persist_replays(self) -> None:
        """Persist derived replays for provenance and metrics."""
        world = self._world
        if not world:
            return
        for r in world.replay_scenarios:
            existing = self.session.exec(
                select(ReplayRun).where(ReplayRun.replay_id == r.replay_id)
            ).first()
            if existing:
                continue
            run = ReplayRun(
                replay_id=r.replay_id,
                incident_id=r.incident_id,
                scenario_id=world.dataset_id,
                scenario_seed=0,
                pre_patch_rule_id=r.rule_before or None,
                pre_patch_detected=r.detection_before,
                pre_patch_score=1.0 if r.detection_before else 0.0,
                post_patch_rule_id=r.rule_after or None,
                post_patch_detected=r.detection_after,
                post_patch_score=1.0 if r.detection_after else 0.0,
                is_identical=True,
                timeline_json=json.dumps(r.timeline),
            )
            self.session.add(run)
        self.session.commit()

    def _persist_graph_from_world(self) -> None:
        """Persist the derived graph for project-scoped endpoints."""
        pass


def delete_project_artifacts(
    session: Session,
    project_id: str,
    artifact_types: list[str] | None = None,
    delete_generations: bool = True,
) -> int:
    """Delete project artifacts, payloads, graph data, and optionally generation records.

    Returns the number of ProjectArtifact rows removed.
    """
    if artifact_types is None:
        artifact_types = list(ARTIFACT_TYPES)

    pa = ProjectArtifact.__table__
    rows = session.exec(
        select(ProjectArtifact).where(
            pa.c.project_id == project_id,
            pa.c.artifact_type.in_(artifact_types),
        )
    ).all()
    count = len(rows)
    affected_generation_ids = {row.generation_id for row in rows}
    for row in rows:
        session.delete(row)

    pap = ProjectArtifactPayload.__table__
    session.exec(
        delete(ProjectArtifactPayload).where(
            pap.c.project_id == project_id,
            pap.c.artifact_type.in_(artifact_types),
        )
    )

    session.flush()

    graph_types = {"orbits", "reach", "segments"}
    if graph_types.intersection(artifact_types):
        remaining_graph_generations = set(
            session.exec(
                select(ProjectArtifact.generation_id).where(
                    ProjectArtifact.__table__.c.project_id == project_id,
                    ProjectArtifact.__table__.c.artifact_type.in_(graph_types),
                )
            ).all()
        )
        for generation_id in affected_generation_ids - remaining_graph_generations:
            scope = f"GEN-{generation_id}"
            session.exec(delete(GraphNode).where(GraphNode.__table__.c.incident_id == scope))
            session.exec(delete(GraphEdge).where(GraphEdge.__table__.c.incident_id == scope))
            session.exec(
                delete(BlastRadiusResult).where(
                    BlastRadiusResult.__table__.c.incident_id == scope
                )
            )

    if {"incidents", "replay"}.intersection(artifact_types):
        dataset_ids = session.exec(
            select(Dataset.dataset_id).where(Dataset.__table__.c.project_id == project_id)
        ).all()
        if dataset_ids and "incidents" in artifact_types:
            session.exec(
                delete(Incident).where(Incident.__table__.c.scenario_id.in_(dataset_ids))
            )
        if dataset_ids and "replay" in artifact_types:
            session.exec(
                delete(ReplayRun).where(ReplayRun.__table__.c.scenario_id.in_(dataset_ids))
            )

    if delete_generations and affected_generation_ids:
        remaining_generation_ids = set(
            session.exec(
                select(ProjectArtifact.generation_id).where(
                    ProjectArtifact.__table__.c.project_id == project_id
                )
            ).all()
        )
        orphaned = affected_generation_ids - remaining_generation_ids
        if orphaned:
            session.exec(
                delete(Generation).where(Generation.__table__.c.generation_id.in_(orphaned))
            )

    session.commit()
    return count
