# ANVAYA — Incident Response

## Incident lifecycle

```text
detected → analyzed → simulated → explained → sealed
```

Enforced by `LIFECYCLE_TRANSITIONS` in `models/incident.py`.

```python
LIFECYCLE_TRANSITIONS: dict[IncidentStatus, list[IncidentStatus]] = {
    IncidentStatus.DETECTED: [IncidentStatus.ANALYZED],
    IncidentStatus.ANALYZED: [IncidentStatus.SIMULATED],
    IncidentStatus.SIMULATED: [IncidentStatus.EXPLAINED],
    IncidentStatus.EXPLAINED: [IncidentStatus.SEALED],
    IncidentStatus.SEALED: [],
}
```

`transition_to` raises `ValueError` for invalid transitions and sets `sealed_at` on `SEALED`.

## Self-correction lifecycle

```text
none → miss → ground_truth_confirmed → backtracking → evidence_identified → rule_proposed → rule_validated → replaying → caught | still_missed
```

If `STILL_MISSED`, it can return to `BACKTRACKING`.

## The judge-observable proof lifecycle

```text
miss → ground truth → backtrack → rule proposal → validation → identical replay → catch → blast simulation → what-if → sealed audit
```

This is the demo path ANVAYA is optimized for. It is implemented by `SentinelEngine` + `BlastScopeEngine` + `WhatIfEngine` + `ControlLedger`.

## State transitions in code

| Transition | Code location | Trigger |
|------------|---------------|---------|
| `DETECTED` | `live/__init__.py` | live scoring flag |
| `ANALYZED` | `demo/orchestrator.py`, `agent/executor.py`, `world_architect.py` | demo/agent analysis |
| `SIMULATED` | same | blast/what-if |
| `EXPLAINED` | same | reasoning/audit |
| `SEALED` | same + `world_architect.py` | final seal action |
| `MISS` | `agent/executor.py` `handle_confirm_ground_truth` | user confirms a miss |
| `GROUND_TRUTH_CONFIRMED` | same | confirm ground truth |
| `BACKTRACKING` | `sentinel/__init__.py` `backtrack` | Sentinel starts |
| `EVIDENCE_IDENTIFIED` | `sentinel/__init__.py` `backtrack` | evidence collected |
| `RULE_PROPOSED` | `sentinel/__init__.py` `propose_rule` | rule built |
| `RULE_VALIDATED` | `sentinel/__init__.py` `validate_rule` | rule passes |
| `REPLAYING` | `sentinel/__init__.py` `replay_attack` | replay started |
| `CAUGHT` / `STILL_MISSED` | `sentinel/__init__.py` `replay_attack` | replay result |

## Detection rule model

`backend/anvaya/models/rule.py` `DetectionRule`:
- `rule_id`, `incident_id`
- `name`, `description`
- `conditions_json` (OR group of conditions)
- `status`: `PROPOSED`, `VALIDATED`, `DEPRECATED`
- `precision`, `recall`, `f1`
- `model_version_id`

Conditions are evaluated by `SentinelEngine._evaluate_rule`.

## Replay model

`backend/anvaya/models/replay.py` `ReplayRun`:
- `replay_id`, `incident_id`
- `pre_patch_rule_id`, `post_patch_rule_id`
- `pre_patch_detected`, `post_patch_detected`
- `events_replayed`

## What happens when an incident is sealed

1. `Incident.transition_to(SEALED)` sets `sealed_at`.
2. `handle_seal_incident` appends a final `AuditRecord`.
3. `on_incident_event(incident, SEALED, session)`:
   - n8n notification
   - Signal API event
   - Gmail notification (if enabled)

## Active recall

- What are the allowed lifecycle transitions?
- How does `self_correction_status` differ from `status`?
- Which engine advances from `RULE_PROPOSED` to `RULE_VALIDATED`?
- What happens if a replay still misses?
- What external integrations fire on `SEALED`?

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/models/incident.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/models/rule.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/models/replay.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/sentinel/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/executor.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/live/dispatch.py" />
