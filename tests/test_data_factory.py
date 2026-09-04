"""Tests for synthetic data generation."""

from anvaya.simulator.generator import TelemetryGenerator
from anvaya.simulator.scenarios import (
    ATTACK_SCENARIOS,
    NORMAL_SCENARIOS,
    get_all_scenarios,
    get_attack_scenarios,
    get_self_correction_scenario,
)


class TestScenarios:
    def test_scenarios_exist(self):
        scenarios = get_all_scenarios()
        assert len(scenarios) >= 7

    def test_normal_scenarios_have_no_attacks(self):
        for s in NORMAL_SCENARIOS:
            assert s.attack_family == "normal"
            assert len(s.ground_truth_events) == 0

    def test_attack_scenarios_have_ground_truth(self):
        for s in ATTACK_SCENARIOS:
            assert s.attack_family != "normal"
            assert len(s.ground_truth_events) > 0

    def test_self_correction_scenario_exists(self):
        sc = get_self_correction_scenario()
        assert sc.expected_detection == "miss"
        assert sc.scenario_id == "ATK-MISS-001"

    def test_scenario_seeds_are_deterministic(self):
        scenarios = get_all_scenarios()
        seeds = [s.seed for s in scenarios]
        assert len(seeds) == len(set(seeds))


class TestTelemetryGenerator:
    def test_generate_for_scenario_is_deterministic(self):
        gen = TelemetryGenerator(seed=42)
        scenario = get_attack_scenarios()[0]
        events1 = gen.generate_for_scenario(scenario)
        events2 = gen.generate_for_scenario(scenario)
        assert len(events1) == len(events2)
        for e1, e2 in zip(events1, events2):
            assert e1["event_id"] == e2["event_id"]
            assert e1["actor"] == e2["actor"]

    def test_generated_events_have_ground_truth(self):
        gen = TelemetryGenerator(seed=42)
        scenario = get_attack_scenarios()[0]
        events = gen.generate_for_scenario(scenario)
        attack_events = [e for e in events if e["is_attack"]]
        assert len(attack_events) > 0
        for e in attack_events:
            assert e["ground_truth_label"] != "normal"

    def test_normal_events_not_flagged_as_attack(self):
        gen = TelemetryGenerator(seed=42)
        scenario = NORMAL_SCENARIOS[0]
        events = gen.generate_for_scenario(scenario)
        for e in events:
            assert not e["is_attack"]
            assert e["ground_truth_label"] == "normal"

    def test_dataset_generation_has_all_splits(self):
        gen = TelemetryGenerator(seed=42)
        dataset = gen.generate_dataset()
        assert "train" in dataset["events"]
        assert "validation" in dataset["events"]
        assert "test" in dataset["events"]
        assert "replay" in dataset["events"]
        meta = dataset["metadata"]
        assert meta["train_count"] > 0
        assert meta["attack_count"] > 0
        assert meta["normal_count"] > 0

    def test_replay_events_are_identical(self):
        gen = TelemetryGenerator(seed=42)
        dataset = gen.generate_dataset(include_self_correction=True)
        replay_events = dataset["events"]["replay"]
        assert len(replay_events) >= 2
        for e in replay_events:
            assert e["is_replay"]
            assert e["replay_id"] != ""

    def test_config_hash_is_deterministic(self):
        gen = TelemetryGenerator(seed=42)
        d1 = gen.generate_dataset()
        gen2 = TelemetryGenerator(seed=42)
        d2 = gen2.generate_dataset()
        assert d1["metadata"]["config_hash"] == d2["metadata"]["config_hash"]

    def test_different_seeds_produce_different_hashes(self):
        gen1 = TelemetryGenerator(seed=42)
        gen2 = TelemetryGenerator(seed=99)
        d1 = gen1.generate_dataset()
        d2 = gen2.generate_dataset()
        assert d1["metadata"]["config_hash"] != d2["metadata"]["config_hash"]
