# 06 — Machine Learning Pipeline

## What the ML does

ANVAYA uses two classical machine learning models:

1. **Isolation Forest** for anomaly detection — the "Alertness" engine.
2. **Logistic Regression** for risk scoring — the "What-If" engine.

Both are from scikit-learn. No GPU or deep neural network is needed, which keeps the project lightweight and easy to explain.

## Feature extraction

`ml/anvaya/features.py` turns a raw telemetry event into a 12-number feature vector.

The feature columns are:

| Feature | Meaning |
|---|---|
| `is_off_hours` | Did the event happen outside working hours? |
| `is_new_device` | Is the device new or unknown? |
| `is_privilege_escalation` | Did the user's privileges increase? |
| `is_anomalous_process` | Is the process unusual? |
| `is_unusual_network` | Is the network connection unusual? |
| `is_lateral_movement` | Did the attacker move to another machine? |
| `hour_of_day` | Numeric hour (0–23) |
| `is_weekend` | Saturday or Sunday? |
| `process_is_shell` | Process is `cmd.exe`, `bash`, `powershell.exe`, etc. |
| `process_is_remote_tool` | Process is `ssh`, `scp`, `mimikatz.exe`, `psexec.exe`, etc. |
| `has_lateral_flag` | Event is tagged as lateral movement |
| `event_type_code` | Numeric code for the event type (login, network, etc.) |

`extract_features(event)` returns a dictionary. `events_to_matrix(events)` returns a NumPy matrix that scikit-learn can eat directly.

## Alertness: Isolation Forest

File: `ml/anvaya/alertness/__init__.py`

An **Isolation Forest** is an algorithm that finds outliers by randomly splitting the data. The fewer splits needed to isolate a point, the more suspicious it is.

The `AlertnessEngine` class:

1. `train(events)` — builds a `StandardScaler`, fits the forest, evaluates precision/recall/F1/FPR/FNR, and persists the model to `ml/artifacts/` with a SHA-256 hash.
2. `load(model_id)` / `load_latest()` — loads a saved model.
3. `predict(events)` — returns predictions, anomaly scores, and whether anything was detected.

The model stores a `ModelVersion` record in the database with metrics and the artifact path.

## What-If: Logistic Regression

File: `backend/anvaya/whatif/__init__.py`

A **Logistic Regression** model estimates the probability that an event is an attack. It is a weighted sum of features passed through a sigmoid function.

The `WhatIfEngine` class:

1. `train(events)` — fits a `StandardScaler` and a `LogisticRegression` classifier, saves a `ModelVersion`.
2. `score_event(event)` — returns the probability of attack (0.0 to 1.0).
3. `analyze(incident_id, changes)` — creates a counterfactual: it takes the original features, applies the requested changes, and scores again. The difference between the original and the new score is the `risk_delta`.

Example counterfactual: *"What if this login had happened during working hours instead of 2 AM?"* If the score drops, the system explains that off-hours timing was a major risk factor.

## Model versions

Every trained model is registered in the `model_versions` table with:
- `model_id` and `model_type`
- `artifact_path` and `artifact_hash`
- `precision`, `recall`, `f1_score`, `false_positive_rate`, `false_negative_rate`
- `inference_latency_ms`
- `training_samples`

This makes the ML reproducible and auditable.

## Why not a neural network?

- The dataset is intentionally small and synthetic.
- Classical models train in milliseconds.
- Feature importance is easy to explain to a judge.
- No GPU is required.
