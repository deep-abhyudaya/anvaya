"""Deterministic synthetic telemetry generator."""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from anvaya.simulator.scenarios import (
    BACKBONE_HOSTS,
    HOSTS,
    SEVERITY_BY_FAMILY,
    USERS,
    ScenarioTemplate,
    get_all_scenarios,
    get_attack_scenarios,
    get_self_correction_scenario,
)


class TelemetryGenerator:
    """Generates deterministic synthetic telemetry events from scenario templates."""

    GENERATOR_VERSION = "1.0.0"

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_for_scenario(
        self,
        scenario: ScenarioTemplate,
        base_time: datetime | None = None,
        replay_id: str = "",
        is_replay: bool = False,
        scenario_seed: int | None = None,
        actor: str | None = None,
        host: str | None = None,
        namespace_seed: str | None = None,
    ) -> list[dict[str, Any]]:
        """Generate telemetry events for a single scenario.

        Optional overrides let the caller vary the apparent actor, initial host,
        base timestamp, and per-generation seed.  This is used by the batch demo
        to produce many distinct-looking incidents from a small set of base
        attack templates while still preserving the ground-truth behavioral
        pattern of each scenario.

        ``namespace_seed`` remaps the scenario's canonical hosts/users onto a
        deterministic, seed-derived slice of the expanded HOSTS/USERS pools so
        different dataset instances populate different parts of the network
        topology. The remap is consistent within one call (lateral-movement
        paths are preserved) and stable for a given namespace_seed. When
        omitted, no remap happens and output is byte-identical to before.
        """
        if base_time is None:
            base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        seed = scenario_seed if scenario_seed is not None else scenario.seed
        rng = random.Random(seed)

        # Identify the original primary actor and host from the template so that
        # overrides can be applied consistently without guessing.
        original_actor = ""
        original_host = ""
        for tmpl in scenario.timeline_template:
            if not original_actor and tmpl.get("actor"):
                original_actor = tmpl["actor"]
            if not original_host and tmpl.get("host"):
                original_host = tmpl["host"]
            if original_actor and original_host:
                break

        def _maybe_override(value: Any, override: str | None, match: str) -> Any:
            if override is None or not match or value != match:
                return value
            return override

        # Deterministic topology namespace: map each canonical host/user used by
        # this scenario's timeline onto a distinct pool entry, offset by a hash
        # of the namespace seed. Values outside the pools (services, IPs) and
        # calls without a namespace_seed are left untouched.
        host_map: dict[str, str] = {}
        user_map: dict[str, str] = {}
        if namespace_seed:
            ns_digest = int(hashlib.sha256(namespace_seed.encode("utf-8")).hexdigest(), 16)
            # Instances of the same scenario pass "scenario_id:N" — spacing the
            # offset by the instance index (with a stride coprime to the pool
            # size) keeps repeat instances on disjoint host/user slices instead
            # of colliding at random hash offsets.
            instance_index = 0
            tail = namespace_seed.rsplit(":", 1)[-1]
            if tail.isdigit():
                instance_index = int(tail)
            host_offset = (ns_digest + instance_index * 7) % len(HOSTS)
            user_offset = (ns_digest // len(HOSTS) + instance_index * 5) % len(USERS)
            seen_hosts: list[str] = []
            seen_users: list[str] = []
            for tmpl in scenario.timeline_template:
                for value in (tmpl.get("host"), tmpl.get("source"), tmpl.get("destination")):
                    if value in HOSTS and value not in BACKBONE_HOSTS and value not in seen_hosts:
                        seen_hosts.append(value)
                if tmpl.get("actor") in USERS and tmpl["actor"] not in seen_users:
                    seen_users.append(tmpl["actor"])
            host_map = {
                h: HOSTS[(host_offset + i) % len(HOSTS)] for i, h in enumerate(seen_hosts)
            }
            user_map = {
                u: USERS[(user_offset + i) % len(USERS)] for i, u in enumerate(seen_users)
            }

        events: list[dict[str, Any]] = []
        current_time = base_time + timedelta(seconds=rng.randint(0, 3600))

        for idx, tmpl in enumerate(scenario.timeline_template):
            event_id = self._make_event_id(scenario.scenario_id, idx, replay_id, rng)
            event_time = current_time + timedelta(minutes=idx * rng.randint(5, 30))

            ground_truth_label = "normal"
            if scenario.attack_family != "normal":
                for gt in scenario.ground_truth_events:
                    if gt["event_index"] == idx:
                        ground_truth_label = gt["label"]
                        break

            # Suspicious scenarios are expected to be flagged as suspicious, not as
            # full attacks.  Normalize their per-event label to "suspicious" so that
            # world_architect.py and the dataset summary can count them in the
            # suspicious bucket while still treating them as attack-like for training
            # and downstream filtering.
            if scenario.expected_detection == "suspicious" and ground_truth_label != "normal":
                ground_truth_label = "suspicious"

            # Any event with an explicit non-normal per-event label is treated as
            # attack-like for training and downstream filtering.  This matches the
            # existing split in world_architect.py / world.py where "suspicious"
            # events are counted as a subset of attack-like telemetry, not as normal.
            is_attack = ground_truth_label not in ("normal",)

            # Per-event severity so downstream scoring (world.py severity/risk)
            # sees real variance instead of a single defaulted value. Attack-like
            # rows carry their family's severity; benign rows stay low.
            if is_attack:
                event_severity = SEVERITY_BY_FAMILY.get(scenario.attack_family, "medium")
            else:
                event_severity = "low"

            # Apply actor/host overrides.  Only replace values that exactly match
            # the original primary actor/initial host so that lateral-movement
            # destinations and other hosts in the timeline are preserved.
            event_host = _maybe_override(tmpl.get("host", ""), host, original_host)
            event_host = host_map.get(event_host, event_host)
            event_source = _maybe_override(tmpl.get("source", ""), host, original_host)
            event_source = host_map.get(event_source, event_source)
            event_actor = _maybe_override(tmpl.get("actor", ""), actor, original_actor)
            event_actor = user_map.get(event_actor, event_actor)
            raw_destination = tmpl.get("destination", "")

            event = {
                # event_type MUST precede event_id: dataset profiling maps the
                # canonical "event_type" to the first matching column, and
                # "event_id" is itself listed as an event_type alias. With
                # event_id first, every benign row's family resolved to its
                # unique EVT-* id, fragmenting benign telemetry into one
                # pseudo-incident per row.
                "event_type": tmpl["event_type"],
                "event_id": event_id,
                "scenario_id": scenario.scenario_id,
                "timestamp": event_time.isoformat(),
                "actor": event_actor,
                "host": event_host,
                "process": tmpl.get("process", ""),
                "source": event_source,
                "destination": host_map.get(raw_destination, raw_destination),
                "command": tmpl.get("command", ""),
                "severity": event_severity,
                "is_off_hours": tmpl.get("is_off_hours", False),
                "is_new_device": tmpl.get("is_new_device", False),
                "is_privilege_escalation": tmpl.get("is_privilege_escalation", False),
                "is_anomalous_process": tmpl.get("is_anomalous_process", False),
                "is_unusual_network": tmpl.get("is_unusual_network", False),
                "is_lateral_movement": tmpl.get("is_lateral_movement", False),
                "is_attack": is_attack,
                "attack_family": scenario.attack_family if is_attack else "",
                "ground_truth_label": ground_truth_label,
                "seed": seed,
                "replay_id": replay_id,
                "is_replay": is_replay,
                "generator_version": self.GENERATOR_VERSION,
            }
            events.append(event)

        # Ambient benign topology traffic (namespace-seeded dataset generation
        # only). Real enterprise telemetry is mostly benign mesh traffic; without
        # it the world graph is a union of disjoint per-instance paths and every
        # degree-derived score (reach, blast, orbits) collapses to 1-2 values.
        # All ambient rows of an instance share one (host, user, event_type)
        # identity so they form exactly ONE benign incident group per instance
        # instead of flooding the incident list, and each instance targets a
        # different backbone slice so blast radius varies per incident.
        # Ground-truth template events above are untouched.
        if namespace_seed and host_map:
            primary_host = host_map.get(original_host, original_host)
            primary_user = user_map.get(original_actor, original_actor)
            src_pool = sorted(set(host_map.values()))
            dst_pool = sorted(set(host_map.values()) | BACKBONE_HOSTS)
            dst_start = ns_digest % max(len(dst_pool), 1)
            ambient_count = max(3, len(scenario.timeline_template) // 2)
            for a_idx in range(ambient_count):
                idx = len(scenario.timeline_template) + a_idx
                event_id = self._make_event_id(scenario.scenario_id, idx, replay_id, rng)
                event_time = current_time + timedelta(minutes=idx * rng.randint(5, 30))
                dst = dst_pool[(dst_start + a_idx) % len(dst_pool)]
                if dst == primary_host:
                    dst = dst_pool[(dst_start + a_idx + 1) % len(dst_pool)]
                events.append(
                    {
                        "event_type": "network_connect",
                        "event_id": event_id,
                        "scenario_id": scenario.scenario_id,
                        "timestamp": event_time.isoformat(),
                        "actor": primary_user,
                        "host": primary_host,
                        "process": "",
                        "source": src_pool[a_idx % len(src_pool)],
                        "destination": dst,
                        "command": "",
                        "severity": "low",
                        "is_off_hours": False,
                        "is_new_device": False,
                        "is_privilege_escalation": False,
                        "is_anomalous_process": False,
                        "is_unusual_network": False,
                        "is_lateral_movement": False,
                        "is_attack": False,
                        "attack_family": "",
                        "ground_truth_label": "normal",
                        "seed": seed,
                        "replay_id": replay_id,
                        "is_replay": is_replay,
                        "generator_version": self.GENERATOR_VERSION,
                    }
                )

        return events

    def generate_dataset(
        self,
        normal_count: int = 3,
        suspicious_count: int = 2,
        attack_count: int = 4,
        include_self_correction: bool = True,
    ) -> dict[str, Any]:
        """Generate a full dataset with train/validation/test split."""
        all_events: list[dict[str, Any]] = []
        scenarios_used: list[str] = []

        normal_scenarios = [
            s for s in get_all_scenarios() if s.attack_family == "normal"
        ]
        suspicious_scenarios = [
            s
            for s in get_all_scenarios()
            if s.attack_family != "normal" and s.expected_detection == "suspicious"
        ]
        attack_scenarios = [
            s for s in get_attack_scenarios() if s.expected_detection == "detect"
        ]

        normal_base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(normal_count):
            scenario = normal_scenarios[i % len(normal_scenarios)]
            events = self.generate_for_scenario(
                scenario,
                base_time=normal_base,
                namespace_seed=f"{self.seed}:{scenario.scenario_id}:{i}",
            )
            all_events.extend(events)
            scenarios_used.append(scenario.scenario_id)

        suspicious_base = datetime(2026, 1, 2, tzinfo=timezone.utc)
        for i in range(suspicious_count):
            scenario = suspicious_scenarios[i % len(suspicious_scenarios)]
            events = self.generate_for_scenario(
                scenario,
                base_time=suspicious_base,
                namespace_seed=f"{self.seed}:{scenario.scenario_id}:{i}",
            )
            all_events.extend(events)
            scenarios_used.append(scenario.scenario_id)

        attack_base = datetime(2026, 1, 3, tzinfo=timezone.utc)
        for i in range(attack_count):
            scenario = attack_scenarios[i % len(attack_scenarios)]
            events = self.generate_for_scenario(
                scenario,
                base_time=attack_base,
                namespace_seed=f"{self.seed}:{scenario.scenario_id}:{i}",
            )
            all_events.extend(events)
            scenarios_used.append(scenario.scenario_id)

        replay_events: list[dict[str, Any]] = []
        if include_self_correction:
            sc_scenario = get_self_correction_scenario()
            # PRE and POST replay MUST share one namespace so both legs land on
            # the same hosts/users and the replay comparison stays valid.
            sc_namespace = f"{self.seed}:{sc_scenario.scenario_id}:self-correction"
            pre_events = self.generate_for_scenario(
                sc_scenario,
                base_time=datetime(2026, 1, 4, tzinfo=timezone.utc),
                replay_id=f"REPLAY-{sc_scenario.scenario_id}-PRE",
                is_replay=True,
                namespace_seed=sc_namespace,
            )
            post_events = self.generate_for_scenario(
                sc_scenario,
                base_time=datetime(2026, 1, 4, tzinfo=timezone.utc),
                replay_id=f"REPLAY-{sc_scenario.scenario_id}-POST",
                is_replay=True,
                namespace_seed=sc_namespace,
            )
            replay_events = pre_events + post_events
            scenarios_used.append(sc_scenario.scenario_id)

        total = len(all_events)
        train_end = int(total * 0.6)
        val_end = int(total * 0.8)

        train = all_events[:train_end]
        validation = all_events[train_end:val_end]
        test = all_events[val_end:]

        normal_evt = sum(1 for e in all_events if not e["is_attack"])
        attack_evt = sum(
            1
            for e in all_events
            if e["is_attack"] and e["ground_truth_label"] != "suspicious"
        )
        suspicious_evt = sum(
            1
            for e in all_events
            if e["is_attack"] and e["ground_truth_label"] == "suspicious"
        )

        config_str = (
            f"{self.GENERATOR_VERSION}:{self.seed}:"
            f"{normal_count}:{suspicious_count}:{attack_count}:"
            f"{include_self_correction}"
        )
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]

        return {
            "events": {
                "train": train,
                "validation": validation,
                "test": test,
                "replay": replay_events,
            },
            "metadata": {
                "generator_version": self.GENERATOR_VERSION,
                "seed": self.seed,
                "config_hash": config_hash,
                "train_count": len(train),
                "validation_count": len(validation),
                "test_count": len(test),
                "replay_count": len(replay_events),
                "normal_count": normal_evt,
                "attack_count": attack_evt,
                "suspicious_count": suspicious_evt,
                "scenario_count": len(scenarios_used),
                "scenarios": scenarios_used,
            },
        }

    def _make_event_id(self, scenario_id: str, idx: int, replay_id: str, rng: random.Random) -> str:
        base = f"{scenario_id}:{idx}:{replay_id}:{rng.randint(0, 999999)}"
        h = hashlib.sha256(base.encode()).hexdigest()[:8].upper()
        return f"EVT-{h}"
