# Workflow: Audit multi-artifact agent narration

Run this FIRST, before workflow 02 or 03. Do not skip it even though the rules
file already contains a confirmed trace — line numbers drift, and this
workflow's job is to re-verify against current code and catch anything the
trace missed.

## Steps

1. Open `backend/anvaya/agent/agent_loop.py` and locate `run_project_plan`.
   Confirm:
   - It builds a single plan `step` whose `inputs.requested_artifacts` is the
     full list of requested artifact types.
   - It emits `agent.plan_created`, `_emit_reasoning`, `_emit_decision_started`,
     `_emit_tool_requested` exactly once, before `_execute_tool_step` runs.
   - `_execute_tool_step` is called exactly once for the whole batch.
   Note the current line numbers for each of these in your findings doc.

2. Open `backend/anvaya/agent/agent_loop.py::run_investigation`. Confirm it
   already loops per-step with its own reasoning/decision/tool/observation
   cycle. Extract the loop's shape (helper calls, ordering, what updates
   `context.plan[i]` vs `context` itself) — this is the pattern
   `run_project_plan` needs to adopt.

3. Open `backend/anvaya/agent/executor.py`, find `handle_manage_artifacts` (or
   equivalent), confirm the `for atype in artifact_types:` loop around
   `ArtifactBuilder(...).run()`. Confirm this is correct and per-artifact
   already (build stream events fire correctly per type). Do not plan any
   change here.

4. Open `backend/anvaya/generations/builder.py`, confirm `ArtifactBuilder` is
   single-target (`self.target_type`, not a list). Confirm no change is
   needed here.

5. Find every caller of `run_project_plan` and every caller of
   `run_investigation` (grep across `orchestrator.py`, `routers/`,
   `frontier_decision.py`, `frontier_loop.py`). List them with file:line.

6. Determine how objectives get classified/routed to `run_project_plan` vs
   `run_investigation` vs anything else. Identify the exact function and
   decision point — this is what workflow 03 (mixed objectives) will need to
   extend.

7. Check the frontend: `components/agent/agent-context.tsx`,
   `components/agent/live-reasoning.tsx`, `components/agent/live-build-panel.tsx`.
   Determine whether reasoning/decision UI state is already keyed by
   `step_index` / `step_id` (like build events already are per
   `AGENT_EXECUTION_EVENTS.md`), or whether it currently assumes one
   reasoning stream per execution. Note which case applies — this determines
   whether workflow 02 needs a frontend sub-step or not.

8. Write findings to `docs/AGENTIC_AUDIT_MULTI_ARTIFACT.md`:
   - Confirmed/corrected trace with current line numbers.
   - Caller list from step 5.
   - Objective-routing function/location from step 6.
   - Frontend finding from step 7.
   - Any discrepancy between this workflow's findings and the rules file —
     flag explicitly if something doesn't match what was expected.

## Exit criteria

Do not proceed to workflow 02 until `docs/AGENTIC_AUDIT_MULTI_ARTIFACT.md`
exists and every step above has a corresponding entry in it. If the trace in
the rules file turns out to be wrong in some material way, stop and surface
that before writing any fix code — the fix workflows assume this trace is
accurate.