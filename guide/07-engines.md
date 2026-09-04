# 07 — The Four Engines

ANVAYA has five subsystems, but four "engines" that the judge demo explicitly exercises. They map to the four columns of the Nerve Arena view:

1. **SentinelBacktracker** — Alertness / Self-Enhancement
2. **BlastScope** — Counter-Attack / Reach
3. **What-If Watcher** — Defense / Counterfactual
4. **ControlLedger** — Response / Audit

## 1. SentinelBacktracker (self-correction)

File: `backend/anvaya/sentinel/__init__.py`

This is ANVAYA's main differentiator. It takes a missed attack and turns it into a caught attack.

States:

`MISS → GROUND_TRUTH_CONFIRMED → BACKTRACKING → EVIDENCE_IDENTIFIED → RULE_PROPOSED → RULE_VALIDATED → REPLAYING → CAUGHT`

How it works:

1. **Backtrack** — Reads the attack events, extracts features, and collects the non-zero suspicious ones into an evidence list.
2. **Propose rule** — Builds an `OR` rule from the most common suspicious features. If an OpenAI API key is set, it asks GPT-4o mini for a nice name and description; otherwise it uses a deterministic name.
3. **Validate rule** — Runs the rule against the telemetry for that incident and computes precision, recall, and F1.
4. **Replay attack** — Re-runs the same scenario events with the new rule and records whether the attack was caught.

The rule evaluation is safe: only allowed operators (`eq`, `ne`, `gt`, `lt`, etc.) are used. There is no Python `eval()` or code execution.

## 2. BlastScope (blast-radius simulation)

File: `backend/anvaya/blastscope/__init__.py`

BlastScope answers: *"If the attacker got into this machine, what else could they reach?"*

It uses **NetworkX** to build a directed graph of assets and relationships. From the compromised host it calculates:

- `total_reachable` — number of nodes the attacker can reach.
- `critical_exposed` — how many of those are critical assets (databases, domain controllers, etc.).
- `max_depth` — longest shortest path from the origin.
- `impact_score` — a weighted number between 0 and 1 combining critical exposure, reach, and depth.
- `propagation_paths` — the actual paths through the network.

The graph nodes and edges are persisted to `graph_nodes` and `graph_edges` so the frontend can render them.

## 3. What-If Watcher (counterfactual defense)

File: `backend/anvaya/whatif/__init__.py`

What-If answers: *"What if we had changed one feature? Would the risk go down?"*

It trains a Logistic Regression model on all telemetry, then for a chosen attack event it:

1. Scores the original features.
2. Applies the requested counterfactual changes (e.g. set `is_off_hours` to 0).
3. Scores the changed features.
4. Computes `score_delta = original_score - counterfactual_score`.
5. Generates a human-readable explanation of which changes mattered.

The result is saved to `counterfactual_analyses`.

## 4. ControlLedger (audit and compliance)

File: `backend/anvaya/models/audit.py`

ControlLedger is an append-only, hash-linked audit trail. Every state transition and engine action creates an `AuditRecord`.

Each record has:
- `record_id` and `incident_id`
- `actor`, `action`, `previous_state`, `new_state`
- `model_version`, `rule_version`, `simulation_id`, `replay_id` (links)
- `control_mapping` (compliance tag, e.g. `NIST.DETECT.ANOMALY`)
- `payload_hash` and `record_hash`
- `previous_hash` — the hash of the previous record in the chain

`verify_chain(records)` recomputes the expected hash for each record and checks that the `previous_hash` links are intact. If one bit is changed, the chain fails verification.
