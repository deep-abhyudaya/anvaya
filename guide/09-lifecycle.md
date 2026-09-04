# 09 — Incident and Self-Correction Lifecycles

## Unified incident lifecycle

Every incident follows this main flow:

```
DETECTED → ANALYZED → SIMULATED → EXPLAINED → SEALED
```

- `DETECTED` — A detection run flagged something, or an incident was created manually.
- `ANALYZED` — The engine has extracted evidence and features.
- `SIMULATED` — BlastScope has computed the blast radius.
- `EXPLAINED` — What-If counterfactual analysis has explained the risk.
- `SEALED` — The incident is closed and an audit record is written.

The `Incident` model in `backend/anvaya/models/incident.py` defines `LIFECYCLE_TRANSITIONS`. Invalid transitions raise a `ValueError` and return a `400 Bad Request` from the API.

## Self-correction lifecycle

This is the ANVAYA demo loop:

```
NONE → MISS → GROUND_TRUTH_CONFIRMED → BACKTRACKING → EVIDENCE_IDENTIFIED
     → RULE_PROPOSED → RULE_VALIDATED → REPLAYING → CAUGHT
```

Or, if the replay still fails:

```
REPLAYING → STILL_MISSED → BACKTRACKING (try again)
```

Each state change is also audited.

## What happens in each state

| State | Meaning |
|---|---|
| `NONE` | New incident, no self-correction yet |
| `MISS` | The first detector failed to catch the attack |
| `GROUND_TRUTH_CONFIRMED` | We have confirmed the attack was real (from scenario labels) |
| `BACKTRACKING` | The engine is walking back through events |
| `EVIDENCE_IDENTIFIED` | Suspicious features have been extracted |
| `RULE_PROPOSED` | A candidate detection rule has been created |
| `RULE_VALIDATED` | The rule has been tested against historical data |
| `REPLAYING` | The same attack is being replayed with the new rule |
| `CAUGHT` | The new rule successfully detected the attack |
| `STILL_MISSED` | The new rule still failed; loop back |

## Judge-observable proof

Run `anvaya demo` and you will see the incident move through every state. At the end:
- `self_correction_status = CAUGHT`
- `status = EXPLAINED` or `SEALED`
- `blast_radius_score` is set
- `whatif_risk_delta` is set
- Multiple `AuditRecord` rows are written with `record_hash` chains

This is the proof the system actually learns, not just talks about learning.
