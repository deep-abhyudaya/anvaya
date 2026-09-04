# Workflow: Fix per-artifact agent narration for multi-target builds

Requires workflow 01 complete (`docs/AGENTIC_AUDIT_MULTI_ARTIFACT.md` exists
and is accurate). Do not start this workflow otherwise.

Goal: for an objective that expands to N artifact types (via `parse_scope` /
the existing "all" expansion), the agent emits one full
reasoning→decision→tool-requested→[build stream]→observation-created cycle
PER artifact, in order — not one cycle for the whole batch.

## Steps

1. In `agent_loop.py`, change plan construction inside `run_project_plan` so
   `context.plan` contains one entry per requested artifact type, not one
   entry whose `inputs.requested_artifacts` is the full array. Each entry:
   - `tool`: `"manage_artifacts"`
   - `inputs.requested_artifacts`: single-element list `[atype]`
   - `inputs.project_id`, `inputs.dataset_id`, `inputs.action`: same as today
   - `label` / `progress` / `completed`: derive per-artifact text, e.g.
     `f"Generating {atype.title()}"`, reusing whatever title-casing/labeling
     helper already exists for artifact type names (check `routes.py` or
     `models/project.py` for one before writing a new one).

2. Replace the current single-step block (emit reasoning → emit decision →
   emit tool-requested → `_execute_tool_step` → build observation → emit
   observation-created) with a loop over `context.plan`, modeled directly on
   `run_investigation`'s existing loop (from workflow 01 step 2's findings).
   Reuse the same private helpers (`_emit_reasoning`, `_emit_decision_started`,
   `_emit_tool_requested`, `_build_observation`) — do not duplicate their
   logic.

3. Inside the loop, before calling `_execute_tool_step` for step i, include
   the target route in the reasoning/decision payload:
   `anvaya.routes.route_for_artifact_type(atype)`. Narration text should read
   like "Next: generating {Type} — navigating to {route}". This event is
   distinct from and precedes the `navigation.started`/`navigation.completed`
   pair that `ArtifactBuilder` already emits once the build actually starts —
   do not remove or duplicate those.

4. Update `step["status"]`, `step["result_summary"]`, `context.current_action`,
   and `context.reasoning_summary` inside the loop, per iteration — so
   mid-run polling of execution state reflects "currently on step i of N"
   correctly, not just the final state.

5. Keep `agent.plan_created` emission exactly where it is (once, up front),
   but make its payload enumerate all N planned steps with their artifact
   type and target route, so the frontend's plan view still shows the full
   picture before execution starts.

6. Keep the final `agent.completed` / `agent.failed` emission exactly where
   it is (once, at the end), summarizing all N steps' results.

7. Failure handling per step: if step i fails, follow the existing
   `tool.failed` → fallback-selection → `tool.fallback` pattern already
   documented in `AGENT_EXECUTION_EVENTS.md` and already used elsewhere in
   this file. Preserve whatever the current single-step failure policy does
   (does it abort the whole execution, or continue?) — apply that same
   policy per-step rather than to the batch. If `ScopeConstraints` or an
   explicit `stop_on_failure` flag governs this, respect it per-step.

8. If workflow 01 found the frontend already keys reasoning/decision UI state
   by `step_index`/`step_id`, no frontend change is needed — verify by
   running a real multi-artifact objective through the dev server and
   confirming N distinct narrated steps render in the timeline.
   If workflow 01 found the frontend assumes one reasoning stream per
   execution, update `agent-context.tsx` / `live-reasoning.tsx` minimally to
   key off `step_index` the same way build events already do — do not
   restructure these components beyond what's needed for this.

9. Do NOT touch `executor.py`'s `for atype in artifact_types:` loop or
   `generations/builder.py`. Those remain exactly as they are — this
   workflow only changes the layer that decides how many times to narrate
   and dispatch, not the build execution itself. (Note: after step 1-2, each
   `manage_artifacts` call from the loop will carry only one artifact type in
   `requested_artifacts`, so `executor.py`'s loop will naturally execute once
   per call instead of looping internally — that's fine and expected; it's
   still the same code path, just invoked N times with a 1-element list
   instead of once with an N-element list.)

## Tests to add

- `tests/agent/test_run_project_plan.py` (or wherever `agent_loop.py` tests
  live): assert that for a 3-artifact objective, the execution event log
  contains exactly one `agent.plan_created` (payload lists 3 steps), then 3
  full reasoning/decision/tool-requested/observation-created cycles in order,
  each correctly interleaved with that step's `generation.*`/`artifact.*`
  sub-stream, then exactly one `agent.completed`.
- Same assertion shape for an 11-type "generate all" objective.
- Regression test: single-artifact objective ("generate orbits") produces the
  exact same event shape as before this change (one step, one cycle).

## Exit criteria

Do not report this workflow complete until:
- All new tests pass.
- All pre-existing tests for `agent_loop.py`, `executor.py`,
  `generations/builder.py` still pass unmodified.
- A manual run of "generate orbits then incidents then impact tree gallery"
  against a project with a ready dataset visibly narrates and navigates
  through all three pages in the running app, not just the first.