# ANVAYA — AI and Detection

## Feature engineering

`ml/anvaya/features.py` defines the 12-column feature vector:

```python
FEATURE_COLUMNS = [
    "is_off_hours", "is_new_device", "is_privilege_escalation",
    "is_anomalous_process", "is_unusual_network", "is_lateral_movement",
    "hour_of_day", "is_weekend", "process_is_shell", "process_is_remote_tool",
    "has_lateral_flag", "event_type_code",
]
```

`extract_features` maps a `TelemetryEvent` or dict to numeric values:
- timestamp → `hour_of_day`, `is_weekend`
- `process` string → `process_is_shell` / `process_is_remote_tool`
- `event_type` → `EVENT_TYPE_CODES`
- booleans copied directly

## Alertness — Isolation Forest

`ml/anvaya/alertness/__init__.py` `AlertnessEngine`.

### Train

1. `X = events_to_matrix(events)`
2. `labels = get_labels(events)`
3. Compute contamination from attack prevalence, clamped `[0.01, 0.5]`.
4. Fit `StandardScaler` + `IsolationForest(n_estimators=100, random_state=42)`.
5. Predict on training data, compute precision, recall, F1, FPR, FNR, latency.
6. Persist model/scaler with `joblib` and create `ModelVersion` record.

### Predict

```python
result = engine.predict_single(event)
# {detected, score, model_id}
```

- Load latest active model if not loaded.
- `score_samples` gives continuous score.
- `predict` returns `-1` for anomaly → converted to `detected=True`.
- Threshold from `settings.detection_threshold`.

### Live scoring entry

`backend/anvaya/live/__init__.py` `score_and_maybe_flag`:
- persist event
- load latest `AlertnessEngine`
- if no model, return `scored: False`
- `predict_single`
- if detected: create/incident, audit, `on_incident_event`

## What-If Watcher — Logistic Regression

`backend/anvaya/whatif/__init__.py` `WhatIfEngine`.

### Train

1. `X = events_to_matrix(events)`
2. `y = get_labels(events)`
3. Fit `StandardScaler` + `LogisticRegression(random_state=42, max_iter=1000, class_weight="balanced")`.
4. Compute metrics.
5. Persist model/scaler and create `ModelVersion`.

### Counterfactual analysis

`WhatIfEngine.analyze(incident_id, changes)`:
1. Load incident and telemetry.
2. Pick attack event (or first event).
3. Compute original `predict_proba`.
4. Mutate features per `changes` dict.
5. Compute new score and `score_delta`.
6. Persist `CounterfactualAnalysis` and update `incident.risk_score`.

Default `changes`:
```python
{"is_off_hours": 0.0, "is_new_device": 0.0}
```

## SentinelBacktracker

`backend/anvaya/sentinel/__init__.py` `SentinelEngine`.

### Steps

1. `backtrack(incident_id)`
   - Load incident + telemetry.
   - Reverse walk attack events, extract non-zero, non-temporal suspicious features.
   - Transition to `EVIDENCE_IDENTIFIED`, store evidence summary.

2. `propose_rule(incident_id)`
   - Count feature occurrences in attack events.
   - Build deterministic `OR` rule with `eq(1.0)` conditions.
   - Optionally call `_llm_propose_rule` for human-readable name.
   - Create `DetectionRule` with status `PROPOSED`.
   - Transition to `RULE_PROPOSED`.

3. `validate_rule(incident_id)`
   - Evaluate rule on telemetry.
   - Compute TP/FP/TN/FN, precision, recall, F1.
   - Update rule to `VALIDATED`, incident to `RULE_VALIDATED`.
   - Call `on_incident_event(RULE_VALIDATED)`.

4. `replay_attack(incident_id)`
   - Load latest validated rule.
   - Re-evaluate attack events.
   - Create `ReplayRun` with `pre_patch_detected` and `post_patch_detected`.
   - Transition to `CAUGHT` or `STILL_MISSED`.
   - Call `on_incident_event(REPLAY_RUN)`.

## BlastScope

`backend/anvaya/blastscope/__init__.py` `BlastScopeEngine`.

### Graph building

- `build_graph` creates a `networkx.DiGraph` from `Asset` and `AssetRelationship`.
- Node attributes: `label`, `node_type`, `is_critical`, `is_compromised`, etc.
- Edge attributes: `relationship_type`, `is_observed`, `is_simulated`, `weight`.

### Blast-radius run

`BlastScopeEngine.run(incident_id)`:
1. Find origin node matching `incident.host`.
2. If not found, create synthetic `ORIGIN-{incident_id}`.
3. Mark origin compromised.
4. Compute `reachable = descendants(G, origin) | {origin}`.
5. For each reachable target, shortest path from origin, track `max_depth`.
6. Compute `critical_exposed`, `critical_ratio`, `reach_ratio`.
7. `impact_score = 0.6 * reach_ratio + 0.3 * critical_ratio + 0.1 * (depth_bonus)`.
8. Persist graph to `GraphNode`/`GraphEdge` and save `BlastRadiusResult`.

## Model provider catalog

`backend/anvaya/llm/providers.py` + catalog files.

| Provider | Config key | Base URL | Protocol |
|----------|------------|----------|----------|
| anvaya (local) | none | n/a | deterministic safe fallback |
| agentrouter | `AGENTROUTER_API_KEY` | `https://agentrouter.org` | anthropic/openai-compatible |
| nvidia | `NVIDIA_API_KEY` | `https://integrate.api.nvidia.com/v1` | openai-compatible |
| opencode | `OPENCODE_API_KEY` | `https://opencode.ai/zen/v1` | openai-compatible |
| openrouter | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1` | openai-compatible |
| seekai | `SEEKAI_API_KEY` | `https://seekai.cc/v1` | openai-compatible |
| gmicloud | `GMICLOUD_API_KEY` | `https://api.gmi-serving.com/v1` | openai-compatible |
| empero | `EMPERO_API_KEY` | `https://free.empero.org/v1` | openai-compatible (public) |

## Active recall

- What are the 12 `FEATURE_COLUMNS`?
- How does `AlertnessEngine` choose `contamination`?
- What does `WhatIfEngine.analyze` mutate to compute counterfactuals?
- What are the four Sentinel steps in order?
- How is `BlastScopeEngine.impact_score` weighted?
- Which model providers are openai-compatible?

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/ml/anvaya/features.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/ml/anvaya/alertness/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/whatif/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/sentinel/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/blastscope/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/llm/providers.py" />
