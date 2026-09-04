# PHASE 1 — ADAPTIVE AGENT LOOP + MISSION SEMANTICS

Integrate a real adaptive agent loop into the existing `AgentOrchestrator` / `ModelPlanner` / `EventStore` path.

## Hard constraints

- Do NOT create a second orchestrator.
- Do NOT create a separate agent database.
- Keep `Execution` as the canonical execution identity.
- Keep `LocalToolExecutor` as the authoritative local tool execution layer.
- Keep `ToolRegistry` authoritative.
- Preserve deterministic fallback behavior.

## First inspect

Trace:

- `AgentOrchestrator.start/run/_run_project_plan`
- `resolve_planner`
- `ModelPlanner.build_plan`
- deterministic planner
- `EventStore.create_execution/emit/complete_execution`
- `/agent/execute`
- frontend `start()` and event consumption

## Target behavior

Replace the semantic assumption of:

`one objective → one precomputed plan → execute all steps`

with:

`objective → observation → next decision → tool → result → observation → next decision → ...`

The initial plan may still exist as a planning artifact, but it must not be the immutable script for the entire mission.

## Decision contract

Integrate a typed decision shape using existing schemas or the smallest extension:

```text
kind: tool | ask_user | complete | replan
selected_tool
inputs
purpose_summary
expected_result
continue_after_result
```

Do not expose hidden reasoning.

## Mission state

Reuse `Execution` fields plus event payloads unless persistent fields are genuinely required.

Track:

- objective
- current iteration
- current stage
- current tool
- completed actions
- failed actions
- success condition
- stop reason
- latest observation

## Adaptive behavior requirement

A tool result must be able to change the next action.

Example test:

1. user asks for biggest threat
2. tool A returns DNS anomaly
3. model chooses DNS-specific investigation tool
4. tool B returns benign scanner evidence
5. model changes candidate ranking
6. model chooses another candidate
7. final finding reflects the revised evidence

Do not hardcode that sequence; hardcode only the deterministic fixtures needed for the test.

## Long-running objective

Support:

“Keep investigating until confidence >= configured threshold OR evidence is exhausted.”

Implement bounded:

- max iterations
- max tool calls
- max duration

## Failure handling

A failed tool must become an observation, not necessarily a terminal state.

Classify:

- retryable
- alternate-tool possible
- dependency missing
- authorization failure
- terminal

Then replan accordingly.

## Acceptance gate

A passing implementation must demonstrate at least 3 decision cycles in one backend test without relying on sleep calls.
