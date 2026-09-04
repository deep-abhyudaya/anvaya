# ANVAYA — Agent Execution Event Contract

## Purpose

Provide a realtime, observable execution trace similar in UX to modern agentic products without exposing hidden chain-of-thought.

## Event envelope

```json
{
  "execution_id": "exec_...",
  "sequence": 1,
  "type": "tool.started",
  "timestamp": "2026-01-01T00:00:00Z",
  "tool_call_id": "call_...",
  "tool_name": "create_replay",
  "provider": "anvaya",
  "status": "running",
  "label": "Creating deterministic replay"
}
```

## Event types

### agent.started
Agent execution has begun.

### agent.plan_created
Optional high-level plan summary.
Do not include private chain-of-thought.

Example:
`Investigate incident → validate detection → assess impact → simulate risk → seal audit`

### tool.started
A tool is about to execute.

### tool.progress
Safe progress update.

Examples:
- `Loading 37 telemetry events`
- `Traversing 14 graph nodes`
- `Validating replay result`

### tool.completed
Tool completed successfully.

### tool.failed
Tool failed.

### tool.fallback
A provider was unavailable and another implementation was selected.

### artifact.created
A user-visible artifact exists.

Examples:
- replay
- ecosystem snapshot
- orbit analysis
- BlastScope result
- What-If result
- threat-intelligence evidence
- audit record

### generation.started
A staged artifact build session has begun.

### generation.analyzing
The builder is analyzing the request and planning the manifest.

### navigation.started / navigation.completed
The builder is navigating the user to the target artifact page and has completed the handoff.

### artifact.queued / artifact.thinking / artifact.creating / artifact.created / artifact.attaching / artifact.completed / artifact.failed / artifact.retrying
Individual product-artifact steps within a staged build. Each step exposes a user-safe name, purpose, and implementation note.

### element.thinking / element.mounted
Per-element construction within an artifact step. `element.thinking` explains why the element is being added; `element.mounted` carries the element data so the UI can render it incrementally.

### generation.finishing / generation.completed / generation.failed
The staged build is finishing or has reached a final state.

## Build event payload conventions

Staged build events carry a common payload shape so the UI can render the
progress UI, deep-link to artifact pages, and anchor to individual steps:

- `index`: step index within the manifest.
- `artifact_type`: the step's product artifact type (e.g. `nodes`, `edges`).
- `target_artifact_type`: the top-level artifact being built (e.g. `orbits`, `incidents`).
- `name`: human step name (e.g. "Orbit Nodes").
- `purpose`: user-safe reason for the step.
- `building`: user-safe implementation note.
- `step_id`: stable step identifier `"{target}-{artifact_type}-{index}"`.
- `route`: frontend route for the target artifact type, from `anvaya.routes`.
- `link`: (only on `artifact.created`) a deep-link to the target page with the
current `?build=` query and a `#build-el-{target}-{index}` fragment.

`element.thinking` and `element.mounted` add:
- `step_index` / `step_id`: parent manifest step.
- `element_id`: stable id of the element within the collection.
- `index` / `total`: position in the emitted stream.
- `reason`: element-specific why this row/node/record is being mounted.
- `display`: a human label for the element.
- `data`: the element payload itself.

### incident.updated
Incident state changed.

### agent.completed
The objective completed.

### agent.failed
The objective could not safely complete.

## UI states

RUNNING:
- animated activity indicator
- elapsed time
- current operation

COMPLETED:
- checkmark
- duration
- result summary
- artifact link

FAILED:
- error summary
- retry/fallback state

FALLBACK:
- explicit provider substitution
- reason
- actual provider used

## Safe output policy

The frontend can receive:
- tool name;
- safe input summary;
- provider;
- timestamps;
- duration;
- status;
- counts;
- IDs;
- links to application artifacts;
- sanitized result summaries.

The frontend must not receive:
- API keys;
- provider credentials;
- private chain-of-thought;
- internal stack traces;
- unnecessary raw third-party content.

## Example complete execution

```text
agent.started
  ↓
tool.started: get_incident
  ↓
tool.completed: get_incident
  ↓
tool.started: get_telemetry
  ↓
tool.completed: get_telemetry
  ↓
tool.started: run_sentinel_trace
  ↓
tool.completed: run_sentinel_trace
  ↓
tool.started: create_replay
  ↓
artifact.created: replay
  ↓
tool.completed: create_replay
  ↓
tool.started: run_replay
  ↓
tool.completed: run_replay
  ↓
tool.started: run_blastscope
  ↓
artifact.created: blastscope
  ↓
tool.completed: run_blastscope
  ↓
tool.started: run_orbit_analysis
  ↓
artifact.created: orbit
  ↓
tool.completed: run_orbit_analysis
  ↓
tool.started: run_what_if
  ↓
artifact.created: what_if
  ↓
tool.completed: run_what_if
  ↓
tool.started: append_audit_record
  ↓
tool.completed: append_audit_record
  ↓
agent.completed
```

## Transport

Preferred:
- SSE from FastAPI to Next.js.

Fallback:
- React Query polling against an execution-events endpoint.

Do not add a message broker merely to support the visual trace unless the existing workload proves it necessary.
