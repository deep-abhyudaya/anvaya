"""Canonical world model derived from a dataset profile.

A WorldModel is a single, deterministic, dataset-grounded representation of a
project's security universe. All project artifacts are projections of this
world model, not independent fabrications.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import networkx as nx
import pandas as pd

from anvaya.dataset_profile import DatasetProfile


@dataclass
class Entity:
    id: str
    name: str
    kind: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Relationship:
    source: str
    target: str
    kind: str
    weight: float = 1.0
    observed: bool = True
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorldEvent:
    event_id: str
    timestamp: str | None
    source: str
    destination: str
    host: str
    user: str
    process: str
    command: str
    action: str
    event_type: str
    severity: str
    attack_family: str
    label: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorldIncident:
    incident_id: str
    title: str
    description: str
    severity: str
    status: str
    host: str
    user: str
    attack_family: str
    event_ids: list[str] = field(default_factory=list)
    first_seen: str | None = None
    last_seen: str | None = None
    blast_radius_score: float = 0.0
    risk_score: float = 0.0
    severity_basis: dict[str, Any] = field(default_factory=dict)
    risk_basis: dict[str, Any] = field(default_factory=dict)
    blast_basis: dict[str, Any] = field(default_factory=dict)


@dataclass
class Orbit:
    source: str
    target: str
    forward_count: int = 0
    reverse_count: int = 0
    interaction_strength: float = 0.0
    risk_score: float = 0.0
    event_count: int = 0
    incident_ids: list[str] = field(default_factory=list)
    first_seen: str | None = None
    last_seen: str | None = None
    risk_basis: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReplayStage:
    name: str
    start: float
    duration: float
    events: list[str] = field(default_factory=list)


@dataclass
class WorldReplay:
    replay_id: str
    incident_id: str
    host: str = "unknown"
    user: str = "unknown"
    status: str = "pending"
    verified: bool = False
    start_time: str = "14:00:00"
    source_event_ids: list[str] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    stages: list[ReplayStage] = field(default_factory=list)
    pre_state: dict[str, Any] = field(default_factory=dict)
    pre_note: dict[str, Any] = field(default_factory=dict)
    post_state: dict[str, Any] = field(default_factory=dict)
    rule_before: str = ""
    rule_after: str = ""
    detection_before: bool = False
    detection_after: bool = False
    ground_truth: str = ""
    risk_delta: float = 0.0
    duration: float = 0.0


@dataclass
class WorldTrophy:
    trophy_id: str
    incident_id: str
    title: str
    description: str
    rarity: str
    score: float
    evidence: dict[str, Any] = field(default_factory=dict)
    sealed_at: str | None = None


@dataclass
class WorldModel:
    project_id: str
    dataset_id: str
    fingerprint: str
    generation_id: str
    entities: list[Entity] = field(default_factory=list)
    assets: list[Entity] = field(default_factory=list)
    users: list[Entity] = field(default_factory=list)
    hosts: list[Entity] = field(default_factory=list)
    services: list[Entity] = field(default_factory=list)
    telemetry: list[WorldEvent] = field(default_factory=list)
    incidents: list[WorldIncident] = field(default_factory=list)
    detections: list[dict[str, Any]] = field(default_factory=list)
    edges: list[Relationship] = field(default_factory=list)
    attack_paths: list[list[str]] = field(default_factory=list)
    risk_relationships: list[Relationship] = field(default_factory=list)
    orbits: list[Orbit] = field(default_factory=list)
    replay_scenarios: list[WorldReplay] = field(default_factory=list)
    ecosystem_nodes: list[dict[str, Any]] = field(default_factory=list)
    ecosystem_edges: list[dict[str, Any]] = field(default_factory=list)
    segments: list[dict[str, Any]] = field(default_factory=list)
    reach: list[dict[str, Any]] = field(default_factory=list)
    impacts: list[dict[str, Any]] = field(default_factory=list)
    arbor: dict[str, Any] = field(default_factory=dict)
    arena: dict[str, Any] = field(default_factory=dict)
    trophy_wall: list[WorldTrophy] = field(default_factory=list)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    controls: list[dict[str, Any]] = field(default_factory=list)
    audit_records: list[dict[str, Any]] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the world model for provenance/debugging."""
        return {
            "project_id": self.project_id,
            "dataset_id": self.dataset_id,
            "fingerprint": self.fingerprint,
            "generation_id": self.generation_id,
            "entity_count": len(self.entities),
            "event_count": len(self.telemetry),
            "incident_count": len(self.incidents),
            "edge_count": len(self.edges),
            "orbit_count": len(self.orbits),
            "replay_count": len(self.replay_scenarios),
            "trophy_count": len(self.trophy_wall),
            "provenance": self.provenance,
            "statistics": self.statistics,
        }


def _canonical_column(df: pd.DataFrame, profile: DatasetProfile, name: str) -> str | None:
    return (
        f"__anvaya_{name}" if f"__anvaya_{name}" in df.columns else profile.canonical_map.get(name)
    )


def _get(
    df: pd.DataFrame, profile: DatasetProfile, row: pd.Series, name: str, default: str = ""
) -> str:
    col = _canonical_column(df, profile, name)
    if col and col in row:
        v = row[col]
        if pd.isna(v):
            return default
        return str(v)
    return default


def _safe_time(value: Any) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat()
    try:
        return pd.to_datetime(value, utc=True).tz_localize(None).isoformat()
    except Exception:
        if isinstance(value, str):
            return value
        return None


def _to_clock(value: Any) -> str | None:
    """Extract an HH:MM:SS clock string from an ISO timestamp or datetime."""
    if pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    try:
        dt = pd.to_datetime(value)
        if pd.isna(dt):
            return None
        return dt.strftime("%H:%M:%S")
    except Exception:
        if isinstance(value, str) and ":" in value:
            if "T" in value:
                return value.split("T")[1].split(".")[0].split("+")[0].split("Z")[0]
            parts = value.split(":")
            if len(parts) >= 3:
                return ":".join(parts[:3])
            return f"{parts[0] or '00'}:{parts[1] or '00'}:00"
        return None


def _severity_rank(severity: str) -> int:
    ranks = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    return ranks.get(severity.lower(), 2)


def _is_ipv4(value: str | None) -> bool:
    """Return True if value is a dotted IPv4 address."""
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def _ip_bucket(value: str, prefix_octets: int = 3) -> str:
    """Bucket an IPv4 address by prefix length, e.g. /24 -> '10.0.0.*'.

    Non-IP values are returned unchanged so hostnames and other identifiers
    keep their exact identity.
    """
    if not _is_ipv4(value):
        return value
    parts = value.split(".")
    if prefix_octets >= 4:
        return value
    prefix = parts[:prefix_octets]
    suffix = ["*"] * (4 - prefix_octets)
    return ".".join(prefix + suffix)


def _pair_bucket(
    src: str | None, dst: str | None, prefix_octets: int = 3
) -> tuple[str, str] | None:
    """Return the bucketed (source, destination) key used for orbit aggregation.

    IPv4 addresses are coarsened to the requested prefix on both sides. When
    both endpoints fall in the same prefix (same /24), we keep the exact pair
    so intra-subnet host-to-host relationships are not collapsed into a single
    self-pair.

    Non-IP values (hostnames, asset IDs, etc.) are kept exact.
    """
    if not src or not dst:
        return None
    if _is_ipv4(src) and _is_ipv4(dst):
        bs = _ip_bucket(src, prefix_octets)
        bd = _ip_bucket(dst, prefix_octets)
        if bs == bd:
            return (src, dst)
        return (bs, bd)
    return (src, dst)


def _compute_blast_basis(
    g: nx.DiGraph,
    origin: str,
) -> tuple[float, dict[str, Any]]:
    """Compute a blast-radius impact score and its causal basis from the observed graph."""
    if g.number_of_nodes() == 0 or not origin:
        return 0.0, {
            "origin_node": origin,
            "total_reachable": 0,
            "total_nodes": 0,
            "critical_exposed": 0,
            "total_critical": 0,
            "critical_ratio": 0.0,
            "reach_ratio": 0.0,
            "max_depth": 0,
            "depth_weight": 0.0,
            "weights": [0.6, 0.3, 0.1],
        }

    degrees = dict(g.degree())
    max_degree = max(degrees.values(), default=0)
    for node in g.nodes:
        g.nodes[node]["is_critical"] = (
            (degrees.get(node, 0) / max_degree) >= 0.6 if max_degree > 0 else False
        )

    total_nodes = g.number_of_nodes()
    total_critical = sum(1 for n in g.nodes if g.nodes[n].get("is_critical", False))

    if origin not in g:
        return 0.0, {
            "origin_node": origin,
            "total_reachable": 0,
            "total_nodes": total_nodes,
            "critical_exposed": 0,
            "total_critical": total_critical,
            "critical_ratio": 0.0,
            "reach_ratio": 0.0,
            "max_depth": 0,
            "depth_weight": 0.0,
            "weights": [0.6, 0.3, 0.1],
        }

    reachable = set(nx.descendants(g, origin))
    reachable.add(origin)
    critical_exposed = sum(1 for n in reachable if g.nodes[n].get("is_critical", False))
    critical_ratio = critical_exposed / total_critical if total_critical > 0 else 0.0
    reach_ratio = len(reachable) / total_nodes if total_nodes > 0 else 0.0

    max_depth = 0
    for target in reachable:
        if target == origin:
            continue
        try:
            path = nx.shortest_path(g, origin, target)
            max_depth = max(max_depth, len(path) - 1)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            pass

    depth_weight = min(max_depth / 5, 1.0)
    impact_score = critical_ratio * 0.6 + reach_ratio * 0.3 + depth_weight * 0.1

    return round(impact_score, 4), {
        "origin_node": origin,
        "total_reachable": len(reachable),
        "total_nodes": total_nodes,
        "critical_exposed": critical_exposed,
        "total_critical": total_critical,
        "critical_ratio": round(critical_ratio, 4),
        "reach_ratio": round(reach_ratio, 4),
        "max_depth": max_depth,
        "depth_weight": round(depth_weight, 4),
        "weights": [0.6, 0.3, 0.1],
    }


def build_world_model(
    df: pd.DataFrame,
    profile: DatasetProfile,
    project_id: str,
    dataset_id: str,
    generation_id: str,
    config: dict[str, Any] | None = None,
) -> WorldModel:
    """Build a canonical world model from a normalized DataFrame and its profile."""
    config = config or {}
    prefix_octets = max(1, min(4, int(config.get("orbit_prefix_octets", 3))))
    from anvaya.dataset_profile import normalize_dataframe

    df = normalize_dataframe(df, profile)
    world = WorldModel(
        project_id=project_id,
        dataset_id=dataset_id,
        fingerprint=profile.fingerprint,
        generation_id=generation_id,
        provenance={
            "dataset_id": dataset_id,
            "fingerprint": profile.fingerprint,
            "rows": len(df),
            "columns": len(df.columns),
            "canonical_map": profile.canonical_map,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    for idx, row in df.iterrows():
        event_id = f"EVT-{dataset_id}-{int(idx)}"
        event = WorldEvent(
            event_id=event_id,
            timestamp=_safe_time(_get(df, profile, row, "timestamp") or None),
            source=_get(df, profile, row, "source_ip"),
            destination=_get(df, profile, row, "destination_ip"),
            host=_get(df, profile, row, "host"),
            user=_get(df, profile, row, "user"),
            process=_get(df, profile, row, "process"),
            command=_get(df, profile, row, "command"),
            action=_get(df, profile, row, "action"),
            event_type=_get(df, profile, row, "event_type"),
            severity=_get(df, profile, row, "severity", "medium").lower() or "medium",
            attack_family=_get(df, profile, row, "attack_family"),
            label=_get(df, profile, row, "label"),
            raw=row.to_dict(),
        )
        world.telemetry.append(event)

        for kind, value in [
            ("host", event.host),
            ("user", event.user),
            ("process", event.process),
            ("source_ip", event.source),
            ("destination_ip", event.destination),
            ("service", _get(df, profile, row, "service")),
            ("asset", _get(df, profile, row, "asset")),
            ("domain", _get(df, profile, row, "domain")),
        ]:
            if value and not any(e.id == f"{kind}:{value}" for e in world.entities):
                world.entities.append(
                    Entity(
                        id=f"{kind}:{value}",
                        name=value,
                        kind=kind,
                        properties={"first_seen": event.timestamp},
                    )
                )

    world.hosts = [e for e in world.entities if e.kind == "host"]
    world.users = [e for e in world.entities if e.kind == "user"]
    world.services = [e for e in world.entities if e.kind == "service"]
    world.assets = [e for e in world.entities if e.kind in ("host", "asset", "service")]

    pair_counts: dict[tuple[str, str], dict[str, Any]] = {}
    for event in world.telemetry:
        if event.source and event.destination and event.source != event.destination:
            ordered_pair = _pair_bucket(event.source, event.destination, prefix_octets)
            if not ordered_pair or ordered_pair[0] == ordered_pair[1]:
                continue
            pair_counts.setdefault(
                ordered_pair,
                {"count": 0, "first": event.timestamp, "last": event.timestamp, "types": set()},
            )
            pair_counts[ordered_pair]["count"] += 1
            pair_counts[ordered_pair]["types"].add(event.event_type or "network")
            if event.timestamp and (
                pair_counts[ordered_pair]["first"] is None
                or event.timestamp < pair_counts[ordered_pair]["first"]
            ):
                pair_counts[ordered_pair]["first"] = event.timestamp
            if event.timestamp and (
                pair_counts[ordered_pair]["last"] is None
                or event.timestamp > pair_counts[ordered_pair]["last"]
            ):
                pair_counts[ordered_pair]["last"] = event.timestamp

    for (src, dst), meta in pair_counts.items():
        world.edges.append(
            Relationship(
                source=src,
                target=dst,
                kind="communicates_with",
                weight=meta["count"],
                observed=True,
                properties={
                    "event_count": meta["count"],
                    "first_seen": meta["first"],
                    "last_seen": meta["last"],
                    "event_types": sorted(meta["types"]),
                },
            )
        )

    for event in world.telemetry:
        if event.user and event.host:
            if any(
                r.source == event.user and r.target == event.host and r.kind == "authenticates_to"
                for r in world.edges
            ):
                continue
            world.edges.append(
                Relationship(
                    source=event.user,
                    target=event.host,
                    kind="authenticates_to",
                    observed=True,
                    properties={},
                )
            )

    g = nx.DiGraph()
    for event in world.telemetry:
        if event.source and event.destination:
            pair = _pair_bucket(event.source, event.destination, prefix_octets)
            if not pair or pair[0] == pair[1]:
                continue
            if g.has_edge(pair[0], pair[1]):
                g[pair[0]][pair[1]]["weight"] += 1
            else:
                g.add_edge(pair[0], pair[1], weight=1)

    incident_groups: dict[tuple[str, str, str], list[WorldEvent]] = {}
    fallback_used = False
    for event in world.telemetry:
        is_incident = (
            event.label.lower() in ("attack", "true", "malicious", "suspicious")
            if event.label
            else False
        ) or _severity_rank(event.severity) >= 1
        if not is_incident:
            continue

        group_key = (
            event.host or event.source or "*",
            event.user or event.destination or "*",
            event.attack_family or event.event_type or "unknown",
        )
        incident_groups.setdefault(group_key, []).append(event)

    if not incident_groups and len(world.telemetry) > 0:
        fallback_used = True
        group_size = max(
            1, len(world.telemetry) // max(1, config.get("fallback_incident_count", 5))
        )
        for i in range(0, len(world.telemetry), group_size):
            chunk = world.telemetry[i : i + group_size]
            if not chunk:
                continue
            key = (
                chunk[0].source or "*",
                chunk[0].destination or "*",
                f"cluster_{i // group_size}",
            )
            incident_groups[key] = chunk

    for (group_host, group_user, family), events in incident_groups.items():
        inc_id = f"INC-{dataset_id[-4:]}-{len(world.incidents) + 1:03d}"
        sev_counts: dict[str, int] = {}
        if events:
            for e in events:
                sev_counts[e.severity] = sev_counts.get(e.severity, 0) + 1
        sev = (
            max(sev_counts, key=lambda k: (sev_counts[k], _severity_rank(k)))
            if sev_counts
            else "medium"
        )

        timestamps = [e.timestamp for e in events if e.timestamp]
        first = min(timestamps) if timestamps else None
        last = max(timestamps) if timestamps else None

        hosts = list({e.host for e in events if e.host})
        users = list({e.user for e in events if e.user})

        severity_rank = _severity_rank(sev)
        severity_factor = severity_rank / 4.0
        event_factor = min(len(events) / 20.0, 1.0)
        calculated_risk = round(severity_factor * 0.6 + event_factor * 0.4, 4)

        primary_source = events[0].source if events else ""
        primary_destination = events[0].destination if events else ""

        severity_basis = {
            "severity_counts": sev_counts,
            "chosen": sev,
            "event_count": len(events),
            "host": group_host,
            "user": group_user,
        }
        risk_basis = {
            "severity_factor": severity_factor,
            "event_factor": event_factor,
            "weights": [0.6, 0.4],
            "event_count": len(events),
            "risk_score": calculated_risk,
            "host": group_host,
            "user": group_user,
        }

        primary_source_bucket = _ip_bucket(primary_source, prefix_octets)
        primary_destination_bucket = _ip_bucket(primary_destination, prefix_octets)
        origin = hosts[0] if hosts and hosts[0] in g else primary_source_bucket
        if origin not in g and primary_destination_bucket in g:
            origin = primary_destination_bucket
        blast_radius_score, blast_basis = _compute_blast_basis(g, origin)

        title_host = hosts[0] if hosts else (group_host if group_host != "*" else primary_source)
        title_user = users[0] if users else (group_user if group_user != "*" else primary_destination)

        incident = WorldIncident(
            incident_id=inc_id,
            title=f"{family.replace('_', ' ').title()} — {title_host} / {title_user}",
            description=f"Dataset-derived incident from {len(events)} events",
            severity=sev,
            status="active",
            host=title_host,
            user=title_user,
            attack_family=family,
            event_ids=[e.event_id for e in events],
            first_seen=first,
            last_seen=last,
            blast_radius_score=blast_radius_score,
            risk_score=calculated_risk,
            severity_basis=severity_basis,
            risk_basis=risk_basis,
            blast_basis=blast_basis,
        )
        world.incidents.append(incident)

    orbit_map: dict[frozenset[str], dict[str, Any]] = {}
    for (src, dst), meta in pair_counts.items():
        if src == dst:
            continue
        pair_key = frozenset([src, dst])
        if pair_key not in orbit_map:
            orbit_map[pair_key] = {
                "a": src,
                "b": dst,
                "ab": 0,
                "ba": 0,
                "first": meta["first"],
                "last": meta["last"],
            }
        if (src, dst) in pair_counts:
            if orbit_map[pair_key]["a"] == src:
                orbit_map[pair_key]["ab"] = meta["count"]
            else:
                orbit_map[pair_key]["ba"] = meta["count"]

    for (src, dst), meta in pair_counts.items():
        pair_key = frozenset([src, dst])
        om = orbit_map[pair_key]
        if om["a"] == src and om["b"] == dst:
            om["ab"] = meta["count"]
        elif om["a"] == dst and om["b"] == src:
            om["ba"] = meta["count"]

    incident_pairs: dict[str, set[frozenset[str]]] = {}
    for inc in world.incidents:
        pairs: set[frozenset[str]] = set()
        for eid in inc.event_ids:
            ev = next((e for e in world.telemetry if e.event_id == eid), None)
            if ev and ev.source and ev.destination:
                pair = _pair_bucket(ev.source, ev.destination, prefix_octets)
                if pair:
                    pairs.add(frozenset(pair))
        incident_pairs[inc.incident_id] = pairs

    # Derive a scaling constant from the data so the 95th-percentile orbit
    # interaction total maps to a 0.0-0.9 strength band, leaving headroom for
    # the incident-count multiplier.
    event_count = max(len(world.telemetry), 1)
    orbit_totals = [om["ab"] + om["ba"] for om in orbit_map.values() if om["ab"] + om["ba"] > 0]
    reference_total = 1
    if orbit_totals:
        sorted_totals = sorted(orbit_totals)
        p95_index = min(len(sorted_totals) - 1, int(len(sorted_totals) * 0.95))
        reference_total = max(1, sorted_totals[p95_index])
    scale = round(0.9 * event_count / reference_total, 4)

    for om in orbit_map.values():
        total = om["ab"] + om["ba"]
        if total <= 0:
            continue
        strength = round(min(1.0, total / event_count * scale), 4)
        incident_pair_key = frozenset([om["a"], om["b"]])
        related_incidents = [
            inc_id for inc_id, pairs in incident_pairs.items() if incident_pair_key in pairs
        ]
        orbit_risk = round(min(1.0, strength * (1 + len(related_incidents) * 0.1)), 4)
        risk_basis = {
            "interaction_strength": strength,
            "related_incident_count": len(related_incidents),
            "incident_weight": 0.1,
            "risk_score": orbit_risk,
            "scaling_constant": scale,
            "reference_total": reference_total,
        }
        world.orbits.append(
            Orbit(
                source=om["a"],
                target=om["b"],
                forward_count=om["ab"],
                reverse_count=om["ba"],
                interaction_strength=strength,
                risk_score=orbit_risk,
                event_count=total,
                incident_ids=related_incidents,
                first_seen=om["first"],
                last_seen=om["last"],
                risk_basis=risk_basis,
            )
        )

    world.orbits.sort(key=lambda o: o.interaction_strength, reverse=True)

    top_nodes = sorted(g.nodes, key=lambda n: g.degree(n), reverse=True)[:20]
    for i, src in enumerate(top_nodes):
        for dst in top_nodes:
            if src == dst:
                continue
            try:
                for p in nx.all_simple_paths(g, src, dst, cutoff=3):
                    world.attack_paths.append(p)
                    if len(world.attack_paths) > 200:
                        break
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                pass
            if len(world.attack_paths) > 200:
                break
        if len(world.attack_paths) > 200:
            break

    for node in sorted(g.nodes):
        try:
            reachable = list(nx.descendants(g, node))
        except Exception:
            reachable = []
        degree = g.degree(node) or 1
        world.reach.append(
            {
                "id": node,
                "name": node,
                "state": "CRITICAL"
                if degree > 15
                else ("COMPROMISED" if degree > 8 else "REACHABLE"),
                "hops": min(3, len(reachable) // 5 + 1),
                "attackScore": round(min(1.0, degree / 20), 2),
                "defenseScore": round(max(0.0, 1.0 - degree / 20), 2),
                "adjacent": reachable[:10],
                "reachable_count": len(reachable),
            }
        )

    for rank, path in enumerate(world.attack_paths[:20]):
        for i in range(len(path) - 1):
            world.segments.append(
                {
                    "id": f"SEG-{rank + 1:03d}-{i + 1}",
                    "from": path[i],
                    "to": path[i + 1],
                    "rank": rank + 1,
                    "depth": i + 1,
                    "reach": len(path) - i - 1,
                    "traffic": round(0.9 - (rank * 0.04), 2),
                    "risk": "critical" if i == 0 else ("high" if i < 2 else "medium"),
                }
            )

    eco_node_map: dict[str, dict[str, Any]] = {}
    for entity in world.entities:
        kind = "asset"
        if entity.kind in ("source_ip", "destination_ip"):
            kind = (
                "asset"
                if entity.name.startswith("SRV-")
                or entity.name.startswith("HOST-")
                or "." in entity.name
                else "attacker"
            )
        elif entity.kind == "user":
            kind = "defender" if entity.name in ("admin", "ops", "analyst") else "attacker"
        eco_node_map[entity.id] = {
            "id": entity.id,
            "kind": kind,
            "name": entity.name,
            "compromised": False,
        }

    for inc in world.incidents:
        for eid in [f"host:{inc.host}", f"user:{inc.user}", f"source_ip:{inc.attack_family}"]:
            if eid in eco_node_map:
                eco_node_map[eid]["compromised"] = True

    for event in world.telemetry:
        if event.label.lower() in ("attack", "malicious") and event.source:
            sid = f"source_ip:{event.source}"
            if sid in eco_node_map:
                eco_node_map[sid]["kind"] = "attacker"
                eco_node_map[sid]["compromised"] = True

    world.ecosystem_nodes = list(eco_node_map.values())

    for edge in world.edges:
        source_id = next(
            (entity_id for entity_id in eco_node_map if entity_id.endswith(f":{edge.source}")),
            edge.source,
        )
        target_id = next(
            (entity_id for entity_id in eco_node_map if entity_id.endswith(f":{edge.target}")),
            edge.target,
        )
        src_kind = eco_node_map.get(source_id, {}).get("kind", "asset")
        dst_kind = eco_node_map.get(target_id, {}).get("kind", "asset")
        kind = "attacks" if src_kind == "attacker" and dst_kind == "asset" else "connects_to"
        if edge.kind == "authenticates_to":
            kind = "authenticates_to"
        world.ecosystem_edges.append(
            {
                "from": source_id,
                "to": target_id,
                "kind": kind,
                "weight": edge.weight,
            }
        )

    for idx, inc in enumerate(world.incidents[:5]):
        events = [e for e in world.telemetry if e.event_id in inc.event_ids]
        events = sorted(events, key=lambda e: e.timestamp or "")
        duration = max(1.0, 60.0 + len(events) * 5)
        stages = [
            ReplayStage(
                name="SOURCE EVENTS",
                start=0.0,
                duration=duration,
                events=[e.event_id for e in events],
            ),
            ReplayStage(
                name="REPLAY READY",
                start=duration,
                duration=0.0,
                events=[],
            ),
        ]

        step = duration / max(len(events), 1)
        timeline = []
        for i, e in enumerate(events):
            timeline.append(
                {
                    "t": round(i * step, 2),
                    "label": e.event_type or e.action or "event",
                    "tone": "amber" if _severity_rank(e.severity) >= 3 else "muted",
                    "lane": "both",
                }
            )

        first_seen = inc.first_seen or "14:00:00"
        start_time = _to_clock(first_seen) or "14:00:00"

        world.replay_scenarios.append(
            WorldReplay(
                replay_id=f"RPL-{dataset_id[-4:]}-{idx + 1:03d}",
                incident_id=inc.incident_id,
                host=inc.host,
                user=inc.user,
                status="pending",
                verified=False,
                start_time=start_time,
                source_event_ids=inc.event_ids,
                timeline=timeline,
                stages=stages,
                pre_state={"detected": None, "rule": None},
                post_state={"detected": None, "rule": None},
                pre_note={"at": 0, "text": "Replay has not been executed"},
                rule_before="",
                rule_after="",
                detection_before=False,
                detection_after=False,
                ground_truth=inc.attack_family,
                risk_delta=0.0,
                duration=duration,
            )
        )

    # Real per-dataset engine signals, derived from what this build actually
    # produced. These replace the former hardcoded arena constants so the
    # scores vary with the data instead of repeating fixed values.
    total_incidents = max(len(world.incidents), 1)
    total_events = max(len(world.telemetry), 1)

    # SENTINEL — detection-layer coverage: share of the event stream that was
    # attributed to a detected incident.
    attributed_events = sum(len(i.event_ids) for i in world.incidents)
    detection_coverage = round(min(1.0, attributed_events / total_events), 2)

    # Backtrack — attribution rate: incidents whose attack family came from
    # real data signals rather than temporal-clustering fallback.
    attributed_incidents = sum(
        1
        for i in world.incidents
        if i.attack_family and not i.attack_family.startswith("cluster_")
    )
    attribution_rate = round(attributed_incidents / total_incidents, 2)

    # Rule Validation — evidence completeness: incidents whose classification
    # is backed by a full causal basis (severity + risk + non-zero blast).
    validated_incidents = sum(
        1
        for i in world.incidents
        if i.severity_basis and i.risk_basis and i.blast_radius_score > 0
    )
    rule_validation_rate = round(validated_incidents / total_incidents, 2)

    # BLASTSCOPE — mean blast radius actually computed per incident origin.
    blast_scores = [i.blast_radius_score for i in world.incidents]
    mean_blast = round(sum(blast_scores) / len(blast_scores), 2) if blast_scores else 0.0

    # WHATIF — mean counterfactual risk already computed per incident.
    risk_scores = [i.risk_score for i in world.incidents]
    mean_risk = round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0.0

    # LEDGER — audit-chain completeness: share of telemetry records carrying
    # every field a complete audit chain requires (id, timestamp, subject, action).
    complete_records = sum(
        1
        for e in world.telemetry
        if e.event_id and e.timestamp and (e.host or e.user) and (e.event_type or e.action)
    )
    ledger_completeness = round(complete_records / total_events, 2)

    for idx, inc in enumerate(world.incidents):
        if inc.severity not in ("high", "critical"):
            continue
        engines_fired = sum(
            [
                len(inc.event_ids) > 0,
                inc.blast_radius_score > 0,
                inc.risk_score > 0,
            ]
        )
        blast = inc.blast_radius_score or 1.0
        score = engines_fired * blast
        if score >= 20:
            rarity = "MYTHIC"
        elif score >= 12:
            rarity = "RARE"
        else:
            rarity = "COMMON"
        engines = {
            "sentinel": 1.0 if len(inc.event_ids) > 0 else 0.0,
            "blastscope": inc.blast_radius_score,
            "whatif": inc.risk_score,
            "ledger": ledger_completeness,
        }
        hops = 1 if inc.severity == "high" else (2 if inc.severity == "critical" else 0)
        world.trophy_wall.append(
            WorldTrophy(
                trophy_id=f"TRP-{dataset_id[-4:]}-{idx + 1:03d}",
                incident_id=inc.incident_id,
                title=f"Sealed {inc.attack_family.replace('_', ' ')}".title(),
                description=f"Outcome for {inc.title}",
                rarity=rarity,
                score=round(score, 2),
                evidence={
                    "incident_id": inc.incident_id,
                    "event_count": len(inc.event_ids),
                    "hops": hops,
                    "counterfactual_count": 0,
                    "blast_radius": inc.blast_radius_score,
                    "severity": inc.severity,
                    "host": inc.host,
                    "user": inc.user,
                    "status": inc.status,
                    "started": inc.first_seen or "",
                    "engines": engines,
                },
                sealed_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    total = max(len(world.incidents), 1)
    caught = sum(1 for r in world.replay_scenarios if r.detection_after)
    world.arena = {
        "stages": [
            {
                "id": "STG-01",
                "name": "Initial Detection",
                "events": len(world.telemetry) // 4,
                "detection_rate": detection_coverage,
            },
            {
                "id": "STG-02",
                "name": "Backtrack",
                "events": len(world.telemetry) // 4,
                "detection_rate": attribution_rate,
            },
            {
                "id": "STG-03",
                "name": "Rule Validation",
                "events": len(world.telemetry) // 4,
                "detection_rate": rule_validation_rate,
            },
            {
                "id": "STG-04",
                "name": "Replay Catch",
                "events": len(world.telemetry) // 4,
                "detection_rate": round(caught / total, 2),
            },
        ],
        "engines": {
            "SENTINEL": detection_coverage,
            "BLASTSCOPE": mean_blast,
            "LEDGER": ledger_completeness,
            "WHATIF": mean_risk,
        },
        "severity": round(sum(_severity_rank(i.severity) for i in world.incidents) / (4 * total), 2)
        if total
        else 0.0,
        "consensus": round(caught / total, 2),
    }

    families: dict[str, list[str]] = {}
    for inc in world.incidents:
        families.setdefault(inc.attack_family, []).append(inc.incident_id)

    children = [
        {"name": family or "unknown", "count": len(ids), "incidents": ids}
        for family, ids in families.items()
    ]
    world.arbor = {
        "root": "dataset",
        "tree": {
            "root": "dataset",
            "children": children,
        },
        "columns": [
            {"name": c.canonical or c.name, "count": c.unique} for c in profile.columns[:8]
        ],
    }

    for inc in world.incidents[:10]:
        world.impacts.append(
            {
                "id": f"IMP-{dataset_id[-4:]}-{len(world.impacts) + 1:03d}",
                "incident_id": inc.incident_id,
                "category": inc.attack_family,
                "affected_assets": list({e for e in inc.event_ids}),
                "affected_count": len(inc.event_ids),
                "severity": inc.severity,
            }
        )

    world.ledger = [
        {
            "record_id": f"AUD-{dataset_id[-4:]}-GEN",
            "action": "artifact_generated",
            "subject": generation_id,
            "dataset_id": dataset_id,
            "fingerprint": profile.fingerprint,
            "artifact_count": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        {
            "record_id": f"AUD-{dataset_id[-4:]}-WRLD",
            "action": "world_model_built",
            "subject": dataset_id,
            "rows": len(world.telemetry),
            "entities": len(world.entities),
            "incidents": len(world.incidents),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    ]

    world.statistics = {
        "entity_count": len(world.entities),
        "host_count": len(world.hosts),
        "user_count": len(world.users),
        "event_count": len(world.telemetry),
        "incident_count": len(world.incidents),
        "edge_count": len(world.edges),
        "orbit_count": len(world.orbits),
        "attack_path_count": len(world.attack_paths),
        "replay_count": len(world.replay_scenarios),
        "trophy_count": len(world.trophy_wall),
        "fallback_used": fallback_used,
        "fallback_reason": (
            "Dataset lacked explicit attack/severity signals; "
            "used temporal clustering fallback"
            if fallback_used
            else None
        ),
    }

    return world
