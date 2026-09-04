"""Artifact manifests for the product-builder experience.

Each manifest describes the product artifacts that make up a given
high-level ANVAYA artifact type. The builder walks this list, persists
per-artifact state, and emits events so the UI can render the assembly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ArtifactManifestStep:
    """A single product artifact to build and reveal."""

    artifact_type: str
    name: str
    purpose: str
    building: str
    selector: Callable[[dict[str, Any], int], dict[str, Any]] | None = None
    dependencies: list[str] = field(default_factory=list)
    elements_from: str | None = None
    element_id_field: str = "id"


ArtifactManifest = list[ArtifactManifestStep]


def _pick_keys(payload: dict[str, Any], keys: list[str], index: int) -> dict[str, Any]:
    """Return a partial payload containing only the requested top-level keys."""
    return {k: payload.get(k) for k in keys if k in payload}


def _head(payload: dict[str, Any], key: str, count: int) -> Any:
    value = payload.get(key)
    if isinstance(value, list):
        return value[:count]
    return value


def _edge_list(edges: Any) -> list[dict[str, Any]]:
    """Return edge records augmented with a stable synthetic `id` for element events."""
    if not isinstance(edges, list):
        return []
    result: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        e = dict(edge)
        if "id" not in e:
            e["id"] = f"{edge.get('from', '')}->{edge.get('to', '')}"
        result.append(e)
    return result


def _pluck_first_list(payload: dict[str, Any], target_key: str = "elements") -> dict[str, Any]:
    """If the payload has a top-level list of dicts, copy it under `target_key`."""
    for value in payload.values():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            return {target_key: value}
    return {}


ORBITS_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Orbit Foundation",
        purpose="Provide the workspace foundation: scope, identity, scale, and provenance.",
        building="Resolving the dataset scope, node count, and provenance for this orbit view.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "scope", "dataset_id", "fingerprint", "node_count", "edge_count"],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="grid",
        name="Orbit Grid",
        purpose="Create the visual reference system: risk rings and asset sectors.",
        building="Laying out the concentric risk rings and asset sectors.",
        dependencies=["foundation"],
    ),
    ArtifactManifestStep(
        artifact_type="nucleus",
        name="Safe Nucleus",
        purpose="Anchor the visualization with the central safe zone.",
        building="Positioning the safe nucleus at the center of the orbit canvas.",
        dependencies=["grid"],
    ),
    ArtifactManifestStep(
        artifact_type="nodes",
        name="Orbit Nodes",
        purpose="Render the interactive nodes that represent assets and incidents.",
        building="Mapping the top nodes by impact score and compromise state.",
        dependencies=["nucleus"],
        selector=lambda payload, idx: _pick_keys(payload, ["top_nodes"], idx),
        elements_from="top_nodes",
        element_id_field="id",
    ),
    ArtifactManifestStep(
        artifact_type="edges",
        name="Counterfactual Orbits",
        purpose="Draw the bidirectional orbit edges that show mutual risk flow.",
        building="Connecting nodes with their counterfactual bidirectional flows.",
        dependencies=["nodes"],
        selector=lambda payload, idx: _pick_keys(payload, ["orbits"], idx),
        elements_from="orbits",
        element_id_field="orbit_id",
    ),
    ArtifactManifestStep(
        artifact_type="blast",
        name="Blast Radius",
        purpose="Show the reach and propagation potential from critical nodes.",
        building="Computing the blast radius and propagation paths.",
        dependencies=["edges"],
        selector=lambda payload, idx: _pick_keys(payload, ["blast_radius"], idx),
    ),
    ArtifactManifestStep(
        artifact_type="stats",
        name="Orbit Statistics",
        purpose="Surface the active, sealed, and critical counts.",
        building="Aggregating node state into active, sealed, and critical totals.",
        dependencies=["nodes"],
    ),
    ArtifactManifestStep(
        artifact_type="side_panel",
        name="Strongest Orbits",
        purpose="List the strongest bidirectional interactions for quick reference.",
        building="Ranking and listing the strongest mutual orbits.",
        dependencies=["edges", "stats"],
    ),
    ArtifactManifestStep(
        artifact_type="legend",
        name="Legend & Context",
        purpose="Explain the visual language of the orbit canvas.",
        building="Adding the legend so the canvas is immediately readable.",
        dependencies=["stats"],
    ),
    ArtifactManifestStep(
        artifact_type="interactions",
        name="Interactions",
        purpose="Enable hover, selection, and exploration of the orbit canvas.",
        building="Wiring hover states and tooltips to the nodes and orbits.",
        dependencies=["edges", "legend"],
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect every artifact into the finished Orbits experience.",
        building="Assembling the complete Orbits workspace.",
        dependencies=["interactions", "side_panel", "blast"],
    ),
]


INCIDENTS_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Incident Foundation",
        purpose="Provide the workspace foundation: scope, dataset, and scale.",
        building="Resolving the dataset, fingerprint, and incident count.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            [
                "artifact_type",
                "dataset_id",
                "fingerprint",
                "row_count",
                "incident_count",
                "provenance",
            ],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="severity_model",
        name="Severity Model",
        purpose="Establish how incident severity is classified.",
        building="Building the severity distribution for the incident set.",
        dependencies=["foundation"],
        selector=lambda payload, idx: {
            "severity_distribution": {
                sev: sum(
                    1
                    for inc in payload.get("incidents", [])
                    if inc.get("severity") == sev
                )
                for sev in ("critical", "high", "medium", "low")
            }
        }
        if "incidents" in payload
        else {},
    ),
    ArtifactManifestStep(
        artifact_type="attack_families",
        name="Attack Family Map",
        purpose="Map the attack families that generated these incidents.",
        building="Grouping incidents by attack family and tactic.",
        dependencies=["foundation"],
        selector=lambda payload, idx: {
            "family_counts": {
                (family or "unknown"): sum(
                    1
                    for inc in payload.get("incidents", [])
                    if (inc.get("attack_family") or "unknown") == (family or "unknown")
                )
                for family in sorted(
                    {inc.get("attack_family") or "unknown" for inc in payload.get("incidents", [])}
                )
            }
        }
        if "incidents" in payload
        else {},
    ),
    ArtifactManifestStep(
        artifact_type="hosts",
        name="Host Index",
        purpose="Index the affected hosts so the table can show where each incident happened.",
        building="Collecting the affected host list from each incident.",
        dependencies=["foundation"],
        selector=lambda payload, idx: {
            "host_count": len(
                {
                    (inc.get("host") or "unknown")
                    for inc in payload.get("incidents", [])
                }
            ),
            "top_hosts": sorted(
                {
                    (inc.get("host") or "unknown")
                    for inc in payload.get("incidents", [])
                },
                key=lambda h: sum(
                    1
                    for inc in payload.get("incidents", [])
                    if (inc.get("host") or "unknown") == h
                ),
                reverse=True,
            )[:5],
        }
        if "incidents" in payload
        else {},
    ),
    ArtifactManifestStep(
        artifact_type="users",
        name="User Index",
        purpose="Index the user identities involved in the incidents.",
        building="Collecting the involved user list from each incident.",
        dependencies=["foundation"],
        selector=lambda payload, idx: {
            "user_count": len(
                {
                    (inc.get("user") or "unknown")
                    for inc in payload.get("incidents", [])
                }
            ),
            "top_users": sorted(
                {
                    (inc.get("user") or "unknown")
                    for inc in payload.get("incidents", [])
                },
                key=lambda u: sum(
                    1
                    for inc in payload.get("incidents", [])
                    if (inc.get("user") or "unknown") == u
                ),
                reverse=True,
            )[:5],
        }
        if "incidents" in payload
        else {},
    ),
    ArtifactManifestStep(
        artifact_type="timeline",
        name="Incident Timeline",
        purpose="Order the first incidents by first and last seen time.",
        building="Sorting incidents by first and last seen timestamps.",
        dependencies=["foundation"],
        selector=lambda payload, idx: {
            "incidents_preview": _head(payload, "incidents", 5),
        }
        if "incidents" in payload
        else {},
    ),
    ArtifactManifestStep(
        artifact_type="blast",
        name="Blast Radius",
        purpose="Show which incidents have the widest propagation potential.",
        building="Calculating blast-radius scores for each incident.",
        dependencies=["timeline"],
        selector=lambda payload, idx: {
            "incidents_by_blast": sorted(
                payload.get("incidents", []),
                key=lambda inc: inc.get("blast_radius_score", 0),
                reverse=True,
            )[:5],
        }
        if "incidents" in payload
        else {},
    ),
    ArtifactManifestStep(
        artifact_type="risk",
        name="Risk Ranking",
        purpose="Rank the highest-risk incidents for triage.",
        building="Sorting incidents by risk score for the risk column.",
        dependencies=["blast"],
        selector=lambda payload, idx: {
            "incidents_by_risk": sorted(
                payload.get("incidents", []),
                key=lambda inc: inc.get("risk_score", 0),
                reverse=True,
            )[:5],
        }
        if "incidents" in payload
        else {},
    ),
    ArtifactManifestStep(
        artifact_type="stats",
        name="Incident Statistics",
        purpose="Surface status counts and the overall incident summary.",
        building="Aggregating status and severity counts.",
        dependencies=["risk"],
    ),
    ArtifactManifestStep(
        artifact_type="incidents",
        name="Full Incident List",
        purpose="Render the complete incident table.",
        building="Loading the full incident list into the workspace.",
        dependencies=["stats"],
        selector=lambda payload, idx: _pick_keys(payload, ["incidents"], idx),
        elements_from="incidents",
        element_id_field="incident_id",
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect every artifact into the finished Incidents experience.",
        building="Assembling the complete Incidents workspace.",
        dependencies=["incidents", "stats"],
    ),
]


ARBOR_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Arbor Foundation",
        purpose="Provide the workspace foundation: dataset, fingerprint, root, and provenance.",
        building="Resolving the dataset identity and attack-family root for the arbor hierarchy.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "dataset_id", "fingerprint", "root", "provenance"],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="branches",
        name="Attack-Family Branches",
        purpose="Grow the attack-family branches under the arbor root.",
        building="Grouping incidents into attack-family categories and assigning branch metadata.",
        dependencies=["foundation"],
        selector=lambda payload, idx: {
            "branches": payload.get("tree", {}).get("children", [])
        }
        if isinstance(payload.get("tree"), dict)
        else {},
        elements_from="branches",
        element_id_field="name",
    ),
    ArtifactManifestStep(
        artifact_type="columns",
        name="Dataset Columns",
        purpose="Index the dataset columns that feed the arbor view.",
        building="Mapping canonical columns to their unique value counts.",
        dependencies=["foundation"],
        selector=lambda payload, idx: _pick_keys(payload, ["columns"], idx),
        elements_from="columns",
        element_id_field="name",
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect the branches and columns into the finished Arbor experience.",
        building="Assembling the complete Nerve Arbor workspace.",
        dependencies=["branches", "columns"],
        selector=lambda payload, idx: _pick_keys(
            payload,
            [
                "artifact_type",
                "dataset_id",
                "fingerprint",
                "root",
                "tree",
                "columns",
                "provenance",
            ],
            idx,
        ),
    ),
]


IMPACTS_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Impact Foundation",
        purpose="Provide the workspace foundation: dataset, fingerprint, and provenance.",
        building="Resolving the dataset and provenance for the impact gallery.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "dataset_id", "fingerprint", "provenance"],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="impacts",
        name="Impact Records",
        purpose="Render the impact records that map incidents to affected assets.",
        building="Loading the impact records into the workspace.",
        dependencies=["foundation"],
        selector=lambda payload, idx: _pick_keys(payload, ["impacts"], idx),
        elements_from="impacts",
        element_id_field="id",
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect every artifact into the finished Impact Gallery experience.",
        building="Assembling the complete Impact Gallery workspace.",
        dependencies=["impacts"],
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "dataset_id", "fingerprint", "impacts", "provenance"],
            idx,
        ),
    ),
]


REACH_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Reach Foundation",
        purpose="Provide the workspace foundation: dataset, incident scope, and provenance.",
        building="Resolving the dataset and incident scope for the reach board.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "dataset_id", "fingerprint", "incident_id", "provenance"],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="items",
        name="Reachable Assets",
        purpose="Render the ranked list of reachable and neutralized assets.",
        building="Loading the reach items with attack and defense scores.",
        dependencies=["foundation"],
        selector=lambda payload, idx: _pick_keys(payload, ["items"], idx),
        elements_from="items",
        element_id_field="id",
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect every artifact into the finished Reach Board experience.",
        building="Assembling the complete Reach Board workspace.",
        dependencies=["items"],
        selector=lambda payload, idx: _pick_keys(
            payload,
            [
                "artifact_type",
                "dataset_id",
                "fingerprint",
                "incident_id",
                "items",
                "provenance",
            ],
            idx,
        ),
    ),
]


REPLAY_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Replay Foundation",
        purpose="Provide the workspace foundation: dataset, fingerprint, and provenance.",
        building="Resolving the dataset and provenance for the replay track.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "dataset_id", "fingerprint", "provenance"],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="replays",
        name="Replay Scenarios",
        purpose="Render the self-healing replay scenarios for the selected incidents.",
        building="Loading the replay scenarios with their timelines and stage results.",
        dependencies=["foundation"],
        selector=lambda payload, idx: _pick_keys(payload, ["replays"], idx),
        elements_from="replays",
        element_id_field="replay_id",
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect every artifact into the finished Miss Replay experience.",
        building="Assembling the complete Miss Replay workspace.",
        dependencies=["replays"],
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "dataset_id", "fingerprint", "replays", "provenance"],
            idx,
        ),
    ),
]


ECOSYSTEM_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Ecosystem Foundation",
        purpose=(
            "Provide the workspace foundation: dataset, health, "
            "compromised summary, and provenance."
        ),
        building="Resolving the dataset and ecosystem health baseline.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            [
                "artifact_type",
                "dataset_id",
                "fingerprint",
                "health",
                "compromised",
                "provenance",
            ],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="nodes",
        name="Ecosystem Nodes",
        purpose="Render the predator, prey, and defender nodes of the ecosystem.",
        building="Positioning attacker, asset, and defender nodes on the ecosystem graph.",
        dependencies=["foundation"],
        selector=lambda payload, idx: _pick_keys(payload, ["nodes"], idx),
        elements_from="nodes",
        element_id_field="id",
    ),
    ArtifactManifestStep(
        artifact_type="edges",
        name="Ecosystem Edges",
        purpose="Draw the attack and connection edges between ecosystem nodes.",
        building="Mapping attacker-to-asset and asset-to-asset flows.",
        dependencies=["nodes"],
        selector=lambda payload, idx: {"edges": _edge_list(payload.get("edges", []))},
        elements_from="edges",
        element_id_field="id",
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect nodes, edges, and health into the finished Threat Ecosystem experience.",
        building="Assembling the complete Threat Ecosystem workspace.",
        dependencies=["edges"],
        selector=lambda payload, idx: _pick_keys(
            payload,
            [
                "artifact_type",
                "dataset_id",
                "fingerprint",
                "health",
                "nodes",
                "edges",
                "compromised",
                "provenance",
            ],
            idx,
        ),
    ),
]


ARENA_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Arena Foundation",
        purpose="Provide the workspace foundation: dataset, severity, consensus, and provenance.",
        building="Resolving the dataset and engine consensus baseline.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            [
                "artifact_type",
                "dataset_id",
                "fingerprint",
                "severity",
                "consensus",
                "provenance",
            ],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="stages",
        name="Arena Stages",
        purpose="Render the detection stages that the engine ring evaluates.",
        building="Loading the recorded detection stages.",
        dependencies=["foundation"],
        selector=lambda payload, idx: _pick_keys(payload, ["stages"], idx),
        elements_from="stages",
        element_id_field="id",
    ),
    ArtifactManifestStep(
        artifact_type="engines",
        name="Engine Consensus",
        purpose="Surface the engine voting scores that drive the arena ring.",
        building="Aggregating sentinel, blastscope, ledger, and what-if engine scores.",
        dependencies=["stages"],
        selector=lambda payload, idx: _pick_keys(payload, ["engines"], idx),
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect stages and engines into the finished Nerve Arena experience.",
        building="Assembling the complete Nerve Arena workspace.",
        dependencies=["engines"],
        selector=lambda payload, idx: _pick_keys(
            payload,
            [
                "artifact_type",
                "dataset_id",
                "fingerprint",
                "stages",
                "engines",
                "severity",
                "consensus",
                "provenance",
            ],
            idx,
        ),
    ),
]


SEGMENTS_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Segments Foundation",
        purpose="Provide the workspace foundation: dataset, incident scope, and provenance.",
        building="Resolving the dataset and incident scope for the segment tracker.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "dataset_id", "fingerprint", "incident_id", "provenance"],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="items",
        name="Tracked Segments",
        purpose="Render the ranked network segments and their risk posture.",
        building="Loading segment records with traffic, depth, and reach values.",
        dependencies=["foundation"],
        selector=lambda payload, idx: _pick_keys(payload, ["items"], idx),
        elements_from="items",
        element_id_field="id",
    ),
    ArtifactManifestStep(
        artifact_type="nodes",
        name="Segment Nodes",
        purpose="Place the nodes that anchor the segment topology.",
        building="Positioning the segment graph nodes.",
        dependencies=["items"],
        selector=lambda payload, idx: _pick_keys(payload, ["nodes"], idx),
        elements_from="nodes",
        element_id_field="id",
    ),
    ArtifactManifestStep(
        artifact_type="edges",
        name="Segment Edges",
        purpose="Draw any additional edges that complete the segment topology.",
        building="Loading the extra segment edges.",
        dependencies=["nodes"],
        selector=lambda payload, idx: {
            "extra_edges": _edge_list(payload.get("extra_edges", []))
        },
        elements_from="extra_edges",
        element_id_field="id",
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect every artifact into the finished Segments experience.",
        building="Assembling the complete Segments workspace.",
        dependencies=["edges"],
        selector=lambda payload, idx: _pick_keys(
            payload,
            [
                "artifact_type",
                "dataset_id",
                "fingerprint",
                "incident_id",
                "items",
                "nodes",
                "extra_edges",
                "provenance",
            ],
            idx,
        ),
    ),
]


TROPHY_WALL_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Trophy Wall Foundation",
        purpose="Provide the workspace foundation: dataset, trophy count, and provenance.",
        building="Resolving the dataset and trophy count for the trophy wall.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "dataset_id", "fingerprint", "trophy_count", "provenance"],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="trophies",
        name="Sealed Trophies",
        purpose="Render the sealed trophies with rarity, score, and evidence.",
        building="Loading the trophy records into the workspace.",
        dependencies=["foundation"],
        selector=lambda payload, idx: _pick_keys(payload, ["trophies"], idx),
        elements_from="trophies",
        element_id_field="trophy_id",
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect every artifact into the finished Trophy Wall experience.",
        building="Assembling the complete Trophy Wall workspace.",
        dependencies=["trophies"],
        selector=lambda payload, idx: _pick_keys(
            payload,
            [
                "artifact_type",
                "dataset_id",
                "fingerprint",
                "trophy_count",
                "trophies",
                "provenance",
            ],
            idx,
        ),
    ),
]


LEDGER_MANIFEST: ArtifactManifest = [
    ArtifactManifestStep(
        artifact_type="foundation",
        name="Ledger Foundation",
        purpose="Provide the workspace foundation: dataset, fingerprint, and provenance.",
        building="Resolving the dataset and provenance for the audit ledger.",
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "dataset_id", "fingerprint", "provenance"],
            idx,
        ),
    ),
    ArtifactManifestStep(
        artifact_type="records",
        name="Audit Records",
        purpose="Render the audit records that document generation and world-model events.",
        building="Loading the ledger records into the workspace.",
        dependencies=["foundation"],
        selector=lambda payload, idx: _pick_keys(payload, ["records"], idx),
        elements_from="records",
        element_id_field="record_id",
    ),
    ArtifactManifestStep(
        artifact_type="final",
        name="Final Assembly",
        purpose="Connect every artifact into the finished Ledger experience.",
        building="Assembling the complete Ledger workspace.",
        dependencies=["records"],
        selector=lambda payload, idx: _pick_keys(
            payload,
            ["artifact_type", "dataset_id", "fingerprint", "records", "provenance"],
            idx,
        ),
    ),
]


def get_artifact_manifest(artifact_type: str) -> ArtifactManifest:
    """Return the manifest for a high-level artifact type."""
    if artifact_type == "orbits":
        return ORBITS_MANIFEST
    if artifact_type == "incidents":
        return INCIDENTS_MANIFEST
    if artifact_type == "arbor":
        return ARBOR_MANIFEST
    if artifact_type == "impacts":
        return IMPACTS_MANIFEST
    if artifact_type == "reach":
        return REACH_MANIFEST
    if artifact_type == "replay":
        return REPLAY_MANIFEST
    if artifact_type == "ecosystem":
        return ECOSYSTEM_MANIFEST
    if artifact_type == "arena":
        return ARENA_MANIFEST
    if artifact_type == "segments":
        return SEGMENTS_MANIFEST
    if artifact_type == "trophy_wall":
        return TROPHY_WALL_MANIFEST
    if artifact_type == "ledger":
        return LEDGER_MANIFEST
    return [
        ArtifactManifestStep(
            artifact_type="foundation",
            name=f"{artifact_type.title()} Foundation",
            purpose=f"Establish the workspace for {artifact_type}.",
            building=f"Resolving the dataset and provenance for {artifact_type}.",
        ),
        ArtifactManifestStep(
            artifact_type="content",
            name=f"{artifact_type.title()} Content",
            purpose=f"Create the main {artifact_type} data and visual elements.",
            building=f"Generating the core {artifact_type} content.",
            dependencies=["foundation"],
        ),
        ArtifactManifestStep(
            artifact_type="elements",
            name=f"{artifact_type.title()} Elements",
            purpose=f"Emit the main {artifact_type} records as individual elements when available.",
            building=f"Loading the first list of {artifact_type} records into the workspace.",
            dependencies=["content"],
            selector=lambda payload, idx: _pluck_first_list(payload),
            elements_from="elements",
            element_id_field="id",
        ),
        ArtifactManifestStep(
            artifact_type="final",
            name="Final Assembly",
            purpose="Connect the pieces into a complete experience.",
            building="Assembling the finished workspace.",
            dependencies=["elements"],
        ),
    ]
