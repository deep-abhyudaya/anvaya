# DATA FACTORY — Autonomous Synthetic Dataset Workflow

## Goal
Continuously create deterministic, realistic-enough, labeled telemetry for ANVAYA evaluation and replay without relying on proprietary or sensitive logs.

## Scenario design
Each scenario is a declarative object containing:
- `scenario_id`
- `generator_version`
- `seed`
- `attack_family`
- `entities`
- `timeline_template`
- `ground_truth_events`
- `expected_detection_behavior`
- `difficulty`

## Generation strategy
Generate benign baseline windows first. Then overlay controlled anomalies and attack sequences.

Support configurable:
- number of users
- number of hosts
- time horizon
- event rate
- anomaly percentage
- attack prevalence
- noise
- missing fields
- repeated patterns
- unseen entity IDs

## Anti-leakage rules
Do not let attack labels leak directly into model features.
Split by time and/or entity where appropriate.
Fit scalers/encoders only on training data.
Keep replay traces separate from evaluation labels used for model tuning.

## Dataset checks
Automatically verify:
- schema compliance
- unique event IDs
- timestamp ordering
- null policy
- class distribution
- scenario coverage
- duplicate rate
- leakage indicators
- train/validation/test contamination

## Regeneration
A generated dataset must be reproducible with:
`dataset_version + generator_version + seed + config_hash`

Store metadata, not giant generated artifacts, in Git. Large datasets should be generated on demand or stored in external artifact storage.
