# PHASE 2 — TOOL-FIRST INVESTIGATION CAPABILITIES

Make the existing ToolRegistry expose genuine investigation capabilities without turning it into a giant list of UI actions.

## Existing tools are the starting point

Reuse the current registered handlers including:

- get_incident
- get_telemetry
- inspect_detection
- run_sentinel_trace
- confirm_ground_truth
- propose_rule
- validate_rule
- run_replay
- run_blastscope
- build_or_update_ecosystem
- generate_artifacts
- manage_artifacts
- run_orbit_analysis
- run_reachability
- run_segment_analysis
- run_what_if
- get_metrics
- append_audit_record
- verify_audit_chain
- seal_incident
- threat_intelligence_lookup
- trigger_automation
- spawn_subagent
- run_tests

## Capability taxonomy

Add or expose capabilities only where a real existing backend operation can support them.

### Observation

`observe_project`
`observe_dataset`
`observe_world_state`
`search_entities`
`search_events`
`inspect_case_or_investigation`

### Analysis

`detect_anomalies`
`correlate_entities`
`compare_baseline`
`rank_candidates`
`trace_attack_path`
`reconstruct_timeline`
`calculate_blast_radius`

Prefer adapters over existing engines rather than duplicate implementations.

For example:

- `trace_attack_path` should reuse BlastScope/graph services.
- `reconstruct_timeline` should reuse replay/telemetry logic.
- `calculate_blast_radius` should reuse BlastScope.
- `correlate_entities` should reuse graph/telemetry data access.

## Tool contracts

Every tool must define:

- typed parameters
- output schema
- risk level
- confirmation requirement
- idempotence
- timeout
- streaming support where applicable
- safe output summary

## Result contract

Reuse `ToolResult`.

Make results rich enough for the agent loop to observe:

- status
- summary
- structured findings
- evidence references
- artifact references
- metrics
- warnings
- fallback state

Do not dump arbitrary dataframe contents into the model.

## Important design principle

The agent should be able to solve:

> “Investigate HOST-17.”

without needing to manually request:

- orbit
- ecosystem
- replay
- trophy

The agent should discover which capabilities are necessary.

## Acceptance test

Create a deterministic fixture where the optimal tool sequence depends on the first observation.

If the first observation says “high reciprocal network activity,” the model/policy should choose graph analysis.

If it says “no network evidence but unusual authentication,” it should choose authentication/identity correlation.

Do not hardcode the final answer.
