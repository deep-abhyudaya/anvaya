# 08 — Synthetic Data Simulator

## Why synthetic data?

ANVAYA cannot use real attack data in a hackathon. Instead it generates fake telemetry that is:
- **Deterministic** — same seed gives same events.
- **Labelled** — every event knows whether it is an attack or normal.
- **Replayable** — the same scenario can be run again unchanged.
- **Safe** — no real credentials, hosts, or malware are involved.

## Scenario templates

File: `simulator/anvaya/scenarios.py`

A `ScenarioTemplate` is a blueprint for one story. It contains:
- `scenario_id` — unique name like `ATK-001`.
- `attack_family` — what kind of attack (credential abuse, privilege escalation, etc.).
- `difficulty` — easy, medium, or hard.
- `seed` — a fixed random seed for the generator.
- `entities` — users, hosts, and processes involved.
- `timeline_template` — the ordered list of events.
- `ground_truth_events` — which event indices are malicious and why.
- `expected_detection` — whether the initial model should detect, miss, or see it as suspicious.

There are four categories:

| Category | Examples | Purpose |
|---|---|---|
| `NORMAL_SCENARIOS` | `NORMAL-001` | Train the model on benign activity |
| `SUSPICIOUS_SCENARIOS` | `SUSP-001`, `SUSP-002` | Edge cases that look odd but may not be attacks |
| `ATTACK_SCENARIOS` | `ATK-001`, `ATK-002`, `ATK-003` | Attacks the first model should detect |
| `ATK-MISS-001` | The self-correction scenario | An attack intentionally crafted to be missed |

## Telemetry generator

File: `simulator/anvaya/generator.py`

The `TelemetryGenerator` turns a `ScenarioTemplate` into a list of `TelemetryEvent`-ready dictionaries.

For each event it:
1. Picks a timestamp based on the template hour and random offsets.
2. Sets `is_attack` and `attack_family` from the template.
3. Picks the correct `ground_truth_label` from `ground_truth_events`.
4. Adds `event_id`, `scenario_id`, `seed`, `replay_id`, `is_replay`, and `generator_version`.

The seed is respected so the same `scenario_id` always produces the same sequence of random offsets.

## Dataset factory

`generate_dataset()` produces a full ML dataset:
- 60% train
- 20% validation
- 20% test
- separate replay split for `ATK-MISS-001`

The splits are by event count, and replay events are kept separate from the main split to prevent data leakage.

## Anti-leakage

- The self-correction scenario is not in the training set.
- Replay events are generated separately and not mixed with train/validation/test.
- Model versions and dataset versions are tracked.

This is important because a fair demo must show the model learning *after* the miss, not seeing the attack before.
