# SELF-CORRECTION — Autonomous Proof Workflow

This workflow is the project's highest-priority technical proof.

## State machine
`MISS → GROUND_TRUTH_CONFIRMED → BACKTRACKING → RULE_PROPOSED → RULE_VALIDATED → REPLAYING → CAUGHT`

Failure branch:
`REPLAYING → STILL_MISSED`

## Required invariants
- pre-patch and post-patch runs reference the same scenario lineage;
- timestamps and relevant telemetry are retained;
- the candidate rule is versioned;
- LLM output is stored as a proposal, not truth;
- deterministic validation precedes success;
- replay result is independently observed;
- every state change is logged/audited.

## Automatic repair loop
If replay is still missed:
1. analyze the failure;
2. identify whether the problem is data, feature extraction, rule semantics, thresholding, or orchestration;
3. make one bounded repair;
4. run targeted tests;
5. rerun the replay;
6. stop after a configured maximum number of iterations;
7. write a diagnostic report if still unsuccessful.

Do not create an infinite self-modifying loop.
