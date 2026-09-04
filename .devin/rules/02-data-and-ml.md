# Rule 02 — Dataset + ML Discipline

## Dataset factory
The project must be able to generate suitable synthetic datasets automatically from a declarative scenario catalog.

Required properties:
- deterministic seeds
- versioned schema
- explicit train/validation/test split
- ground-truth labels
- attack-family labels where applicable
- host/user/entity identifiers
- timestamps
- causal ordering metadata where needed for replay
- scenario ID and generator version
- no train/test contamination
- configurable class balance
- configurable anomaly rates
- configurable noise rates
- configurable missingness
- configurable benign/attack ratio

## Minimum scenario catalog
Create enough deterministic scenarios to exercise every product pillar, including:
- normal behavior
- suspicious login
- novel device / off-hours login
- suspicious process execution
- privilege escalation sequence
- lateral movement sequence
- suspicious network connection
- an intentionally missed attack
- a patched-and-caught replay of the same attack

## ML honesty
- Never optimize only for aggregate accuracy.
- Report precision, recall, F1, confusion matrix, false-positive rate, false-negative rate, and latency where appropriate.
- Prevent temporal and entity leakage.
- Fit preprocessing only on training data.
- Persist model metadata and feature schema.
- Version every trained artifact.
- Validate inference inputs.
- Store evaluation reports in `docs/evaluation/`.

## Self-correction proof
A self-correction success is valid only if:
1. the pre-patch replay genuinely misses;
2. a candidate rule is generated;
3. the rule is independently validated;
4. the same scenario is replayed with the same relevant seed/trace;
5. the post-patch detector genuinely fires;
6. the result is persisted and auditable.
