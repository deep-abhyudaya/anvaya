# ANVAYA — CURRENT CODEBASE INTEGRATION MAP FOR DEVIN

This file is a reference anchor so the implementation prompt stays grounded in the actual uploaded codebase.

## Backend agent core

### `backend/backend/anvaya/agent/orchestrator.py`

Current behavior:

- `start()` creates an `Execution` through `EventStore`.
- `run()` resolves incident/project context.
- profile is selected.
- planner builds a plan once.
- plan steps are executed sequentially.
- `LocalToolExecutor.execute()` runs each step.
- events emitted include `agent.message`, `agent.plan_created`, `tool.started`, `tool.progress`, `artifact.created`, `tool.completed`, `tool.failed`, `incident.updated`, `agent.completed`, `agent.failed`.
- project-scoped requests can route through `_run_project_plan()` and artifact actions.

Integration target:

- retain orchestration ownership here.
- make the plan mutable/iterative.
- feed tool results back into the next decision.
- add objective/memory/verification semantics around this existing loop.

### `backend/backend/anvaya/agent/planner.py`

Current behavior:

- `ModelPlanner` builds a JSON `plan` array.
- deterministic planner is fallback.
- `resolve_planner()` selects model-backed provider where compatible, otherwise deterministic.

Integration target:

- preserve model/provider fallback.
- add next-action decision semantics.
- do not allow raw model text to mutate state.

### `backend/backend/anvaya/agent/registry.py`

Current authoritative tools include:

- `get_incident`
- `get_telemetry`
- `inspect_detection`
- `run_sentinel_trace`
- `confirm_ground_truth`
- `propose_rule`
- `validate_rule`
- `run_replay`
- `run_blastscope`
- `build_or_update_ecosystem`
- `generate_artifacts`
- `manage_artifacts`
- `run_orbit_analysis`
- `run_reachability`
- `run_segment_analysis`
- `run_what_if`
- `get_metrics`
- `append_audit_record`
- `verify_audit_chain`
- `seal_incident`
- `threat_intelligence_lookup`
- `trigger_automation`
- `spawn_subagent`
- `run_tests`

Integration target:

- preserve this registry.
- extend with real observation/investigation capabilities by wrapping existing services where needed.
- avoid UI-specific tools.

### `backend/backend/anvaya/agent/executor.py`

This is the real local tool execution boundary.
It already wraps major ANVAYA engines and artifact operations.

Integration target:

- add observability/progress callbacks only where actual work exists.
- return structured `ToolResult` data sufficient for the next agent decision.
- keep defensive-security boundaries.

### `backend/backend/anvaya/agent/events.py`

Current EventStore:

- persists `ExecutionEvent`
- maintains in-memory cache
- retrieves by sequence
- supports event replay
- complete execution state persists in `Execution`

Integration target:

- make events authoritative for live execution observation.
- preserve ordered sequence semantics.
- add only minimal new event types.

### `backend/backend/anvaya/models/execution.py`

`Execution` currently tracks:

- execution_id
- objective
- incident_id
- status
- provider
- fallback
- timestamps/duration
- result/error

`ExecutionEvent` tracks:

- execution_id
- sequence
- type
- timestamp
- tool metadata
- status
- payload_json
- artifact references
- errors/fallback

Integration target:

- extend carefully if persistent mission state cannot fit in event-derived state.
- avoid duplicating state across multiple models.

### `backend/backend/anvaya/agent/subagents.py`

Existing subagent support:

- parent/child execution IDs
- profile-driven allowed tools
- foreground/background modes
- nesting limits
- cancellation/resume
- parent event propagation

Integration target:

- let the main adaptive agent decide when delegation is beneficial.
- return structured child results.

## Dataset/world/artifact layer

### `backend/backend/anvaya/models/project.py`

Current artifact types:

1. incidents
2. arbor
3. impacts
4. reach
5. replay
6. ecosystem
7. arena
8. orbits
9. segments
10. trophy_wall
11. ledger

Project/dataset/generation/artifact models are project + organization scoped.

### `backend/backend/anvaya/generation.py`

`ArtifactGenerator` loads the selected project dataset, derives graph/artifact payloads, persists `ProjectArtifact` and payload data, and writes graph/reachability records.

Integration target:

- artifacts become optional instruments in an investigation.
- preserve dataset provenance.
- do not mass-generate all artifacts on every objective.

## Existing domain engines to reuse

- SentinelBacktracker
- BlastScope
- What-If
- replay
- graph/telemetry/detections
- audit ledger
- dataset profiling/generation

Do not duplicate these algorithms in agent code.

## Router layer

### `backend/backend/anvaya/routers/agent.py`

Current routes include:

- agent execute
- agent chat
- agent chat stream
- profiles
- models
- providers
- tools
- tool validation
- executions
- execution events
- execution event stream
- seed
- subagent profiles
- spawn/list/get/cancel/resume/list-by-execution

Important current gap:

`/agent/execute` currently invokes the orchestrator synchronously before returning its response.

The prompts require moving long-running execution into a server-side execution path that returns the execution ID and streams events while preserving the existing EventStore/SSE contracts.

## Project router

### `backend/backend/anvaya/routers/projects.py`

Handles:

- projects
- project-scoped datasets
- dataset profiling
- generations
- project artifact listing/latest/inspection/regeneration/deletion behavior

Use its existing authorization helpers.

## Frontend

### `frontend/components/agent/agent-context.tsx`

Current client state includes:

- profiles/models
- execution ID
- events
- status
- project/incident context
- chat streaming message
- execution history
- subagents

Current event behavior:

- 1-second polling for execution events
- query invalidation after terminal event

Integration target:

- add SSE-first behavior with polling fallback.
- represent iterative decision/observation/hypothesis/verification states.
- keep one state authority.

### `frontend/components/agent/agent-console.tsx`

Already renders:

- agent mode
- profile
- model
- execution tabs
- console/subagent tabs
- event cards
- composer
- streaming chat message

Integration target:

- deepen existing event cards rather than create a new console.

### `frontend/lib/api.ts`

Already contains agent execution/event/chat/subagent APIs and project artifact hooks.

Integration target:

- add minimal typed APIs for new execution/mission controls and event transport.

## Product principle

The frontend must visualize state created by the backend.
The backend agent must be capable of useful work without the frontend.
The existing artifacts remain valuable, but they are instruments selected by the agent when they help solve an objective.
