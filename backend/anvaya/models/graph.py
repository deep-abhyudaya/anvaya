"""Graph models for BlastScope visualization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class GraphNode(SQLModel, table=True):
    __tablename__ = "graph_nodes"

    id: Optional[int] = Field(default=None, primary_key=True)
    node_id: str = Field(unique=True, index=True, max_length=64)
    incident_id: str = Field(default="", index=True, max_length=64)
    label: str = Field(max_length=128)
    node_type: str = Field(max_length=64)
    state: str = Field(
        default="normal", max_length=32
    )
    is_compromised: bool = False
    is_critical: bool = False
    depth: int = 0
    impact_score: float = 0.0
    blast_contribution: float = 0.0
    metadata_json: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GraphEdge(SQLModel, table=True):
    __tablename__ = "graph_edges"

    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: str = Field(default="", index=True, max_length=64)
    source_node_id: str = Field(index=True, max_length=64)
    target_node_id: str = Field(index=True, max_length=64)
    edge_type: str = Field(max_length=64)
    is_observed: bool = False
    is_simulated: bool = False
    is_possible: bool = False
    weight: float = 1.0
    metadata_json: str = ""


class BlastRadiusResult(SQLModel, table=True):
    __tablename__ = "blast_radius_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: str = Field(unique=True, index=True, max_length=64)
    total_reachable: int = 0
    critical_exposed: int = 0
    max_depth: int = 0
    impact_score: float = 0.0
    reachable_assets_json: str = ""
    propagation_paths_json: str = ""
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
