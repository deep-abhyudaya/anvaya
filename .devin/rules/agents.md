---
trigger: always_on
---
# ANVAYA — Agent Narration Rules

These rules apply to ALL sessions touching `backend/anvaya/agent/`,
`backend/anvaya/generations/`, or the frontend agent components
(`components/agent/*`). Read in full before editing anything in those paths.

## Repo orientation (do not re-derive from scratch — this is already known)

- FastAPI backend at `backend/anvaya/`, Next.js frontend at repo root
  (`app/`, `components/`, `lib/`).
- `agent/executor.py` (`LocalToolExecutor`) dispatches individual tool calls,
  including `manage_artifacts`, which — for a `generate`/`regenerate` action —
  loops `for atype in artifact_types:` and runs one `ArtifactBuilder(...).run()`
  per artifact type. This loop is CORRECT and already produces a full,
  per-artifact build stream (`generation.*` / `artifact.*` / `element.*` /
  `navigation.*` events) for every requested type. Do not rewrite it.
- `generations/builder.py` (`ArtifactBuilder`) builds exactly one artifact type
  per instance (`self.target_type`), stepping through its manifest and emitting
  `artifact.queued → artifact.thinking → artifact.creating → artifact.created →
  element.thinking/element.mounted (per row) → artifact.attaching →
  artifact.completed`, then `generation.completed`. This is CORRECT. Do not
  change its single-target design — it's meant to be instantiated once per
  artifact type, not to accept a list itself.
- `agent/scope.py` (`parse_scope`) correctly parses a compound objective like
  "generate orbits then incidents then impact tree gallery" into an ordered
  `["orbits", "incidents", "impacts"]`. This is CORRECT. Do not touch it.
- `agent/agent_loop.py::AgentLoop.run_project_plan` is the entry point for
  project-artifact objectives. THIS IS WHERE THE BUG LIVES: it wraps the
  entire requested-artifact array into ONE plan step, and emits
  `agent.plan_created` / reasoning / decision / tool-requested /
  observation-created exactly ONCE for the whole batch — before calling
  `manage_artifacts` a single time. The result: the low-level per-artifact
  build stream is real and fires for every type, but the high-level agent
  narration ("I need to generate orbits, so navigating to /orbits... now
  incidents...") never repeats per artifact. That's the reported symptom:
  full thinking/build detail on one artifact, silent looping through the rest.
- `agent/agent_loop.py::AgentLoop.run_investigation` already loops over a
  multi-step plan correctly (one reasoning/decision/tool/observation cycle per
  step, in order). Treat this as the reference implementation for what
  `run_project_plan` should become — check its loop structure before writing
  anything new.
- Event contract lives in `AGENT_EXECUTION_EVENTS.md` at repo root — treat it
  as authoritative for event names/shapes. Any new event must fit this
  contract or extend it explicitly with a documented reason.
- `models/project.py::ARTIFACT_TYPES` is the canonical list of the 11 project
  artifact types (incidents, arbor, impacts, reach, replay, ecosystem, arena,
  orbits, segments, trophy_wall, ledger).
- `anvaya.routes.route_for_artifact_type` maps an artifact type to its
  frontend route — use this, never hardcode a route string.

## Hard constraints (never violate these)

- NEVER change `ArtifactBuilder`'s single-target design. NEVER make it accept
  a list of target types. Multi-target orchestration belongs one layer up, in
  `agent_loop.py`.
- NEVER change the `generation.*` / `artifact.*` / `element.*` /
  `navigation.*` event contract in `AGENT_EXECUTION_EVENTS.md`. That layer is
  correct and untouched by this work.
- NEVER touch `agent/scope.py`'s parsing logic. It's correct.
- NEVER expose hidden chain-of-thought in any narration event. Reasoning text
  must stay in the same safe, observable register already used elsewhere:
  tool name, why this step, what's next — never raw model scratch-space.
- NEVER fabricate a navigation, tool call, or build step that didn't actually
  happen. If a step is skipped or fails, say so via the existing
  `tool.failed` / `tool.fallback` pattern — don't silently omit it.
- NEVER let a fix to multi-artifact objectives change the event shape for a
  single-artifact objective ("generate orbits" alone). Single-target behavior
  must remain byte-identical before and after this work — treat it as a
  regression gate on every change.
- NEVER merge `manage_artifacts` and the individual investigation tools
  (`create_replay`, `run_blastscope`, `run_what_if`, etc.) into one mega-tool
  when handling mixed objectives. Keep them as distinct, independently-typed
  steps in one ordered plan.

## Definition of done for this problem family

Do not report a task in this problem family complete until:
- A compound objective ("generate orbits then incidents then impact tree
  gallery") produces, in the execution event log: one `agent.plan_created`
  listing all N steps, then for each step (in order) a full
  reasoning→decision→tool-requested→[build stream]→observation-created cycle,
  then one final `agent.completed`.
- The same holds for "generate all" (11 types) and for mixed
  investigation+generation objectives.
- Single-artifact objectives still produce exactly the pre-existing one-step
  event shape.
- Existing tests for `agent_loop.py`, `executor.py`, `generations/builder.py`
  pass unmodified.
- New tests assert the per-step event ordering described above.