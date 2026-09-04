# ANVAYA — Agentic Multi-Artifact Narration Audit

Workflow: `audit_multi.md`  
Date: 2026-08-29  
Scope: `backend/anvaya/agent/`, `backend/anvaya/generations/`, frontend agent UI

---

## 1. `run_project_plan` in `backend/anvaya/agent/agent_loop.py`

File: `backend/anvaya/agent/agent_loop.py`

### Confirmed trace

- Function span: lines 374–586.
- Plan construction (lines 416–431) builds **exactly one** `manage_artifacts` step whose `inputs.requested_artifacts` is the full list of requested artifact types:

```python
plan = [
    {
        "tool": "manage_artifacts",
        "inputs": {
            "project_id": project_id,
            "dataset_id": "",
            "action": action,
            "requested_artifacts": requested_types,
        },
        ...
    }
]
```

- `requested_types` is derived at lines 410–414 from the `requested` argument, expanding `"all"` to the full `ARTIFACT_TYPES` list.
- The high-level agent narration sequence is emitted **once**, at lines 488–524:
  - `_emit_reasoning` at line 492
  - `_emit_decision_started` at line 493
  - `_emit_tool_requested` at line 494
  - `_execute_tool_step` at line 496 (single call)
  - `agent.observation_created` at lines 500–510
- Final `agent.completed` / `agent.failed` is emitted once at lines 526–578.

### Audit conclusion

The rules-file trace is accurate: `run_project_plan` wraps the entire requested artifact list into one plan step and narrates it once. The low-level build stream (see section 3) still fires per artifact, but the high-level per-page reasoning/decision/navigation loop does not repeat.

---

## 2. `run_investigation` loop shape (reference implementation)

File: `backend/anvaya/agent/agent_loop.py`, lines 62–342.

### Confirmed loop structure

```python
step_index = 0
while step_index < len(context.plan):
    # Refresh context, check cancellation/messages
    self.session.refresh(context)
    if context.status == "cancelled": return execution
    stop, _ = self._check_messages(execution, context)
    if stop: return execution

    step = context.plan[step_index]

    if step.get("status") == "skipped":
        ...
        step_index += 1
        continue

    # Update live context
    step["status"] = "running"
    step["step_index"] = step_index
    context.current_action = {...}
    self._save_context(context)

    previous_result = results[-1] if results else None

    # Narration per step
    self._emit_reasoning(context, step, previous_result, execution_id)
    self._emit_decision_started(execution_id, step, step_index)
    self._emit_tool_requested(execution_id, step, step_index)

    # Execute
    result = self._execute_tool_step(execution_id, step, step_index, profile, messenger)
    results.append(result)

    # Observation
    observation = _build_observation(step["tool"], result, step_index)
    context.observations = list(context.observations) + [observation]
    self.store.emit(..., "agent.observation_created", ...)

    # Update plan / context
    step["status"] = "completed" if result.status == "success" else "failed"
    step["result_summary"] = result.output_summary or result.error_message or ""
    step["artifact_count"] = len(result.artifact_refs)
    context.reasoning_summary = self.reasoning_generator.generate(context, step, result)
    self._save_context(context)

    # Stop-on-failure / optional handling
    if result.status != "success" and not step.get("optional"):
        if step.get("stop_on_failure", False):
            self._fail_execution(...)
            return execution

    step_index += 1
```

### What `run_project_plan` should adopt

The same loop body should be used in `run_project_plan`, but with:
- `context.plan` containing one `manage_artifacts` step **per artifact type** (or one step for a single-artifact objective).
- The `target` of `context.current_action` set to the artifact type / route instead of the project ID.
- Failure handling preserving the current "continue on failure" policy (`stop_on_failure: False`) unless `ScopeConstraints` introduces per-step policy later.

---

## 3. `executor.py` `handle_manage_artifacts` per-artifact loop

File: `backend/anvaya/agent/executor.py`, lines 744–945.

### Confirmed trace

- `artifact_types` is resolved at lines 764–766 by filtering `requested` against `ARTIFACT_TYPES`.
- For `action in ("generate", "regenerate")`, the actual build loop is at lines 867–911:

```python
for atype in artifact_types:
    generation = Generation(..., target_artifact_type=atype, ...)
    ...
    builder = ArtifactBuilder(self.session, generation, execution, project)
    result = builder.run()
    ...
    created[atype] = result.get("total_artifacts", 1)
```

- `ArtifactBuilder.run()` emits the full `generation.*` / `artifact.*` / `element.*` / `navigation.*` stream per artifact type (see section 4).

### Audit conclusion

The rules-file trace is accurate. The executor is correct and should **not** be changed. The per-artifact build stream is already produced for every requested type.

---

## 4. `generations/builder.py` `ArtifactBuilder` single-target design

File: `backend/anvaya/generations/builder.py`, lines 41–517.

### Confirmed trace

- `__init__` (lines 44–68) stores `self.target_type = generation.target_artifact_type` and `self.route = route_for_artifact_type(self.target_type)`.
- `run()` (lines 281–494) builds exactly one artifact type per call and emits:
  - `generation.started` / `generation.analyzing`
  - `navigation.started` / `navigation.completed`
  - `artifact.queued` → `artifact.thinking` → `artifact.creating` → `artifact.created` → `element.thinking` / `element.mounted` → `artifact.attaching` → `artifact.completed` (per manifest row)
  - `generation.finishing` / `generation.completed`

### Audit conclusion

The rules-file trace is accurate. `ArtifactBuilder` is single-target and must remain so. Multi-target orchestration belongs in `agent_loop.py`.

---

## 5. Callers of `run_project_plan` and `run_investigation`

| Function called | Caller | File:line | Notes |
|---|---|---|---|
| `AgentLoop.run_project_plan` | `AgentOrchestrator._run_project_plan` | `backend/anvaya/agent/orchestrator.py:267` | Project-scoped artifact plan |
| `AgentLoop.run_investigation` | `AgentOrchestrator.run` | `backend/anvaya/agent/orchestrator.py:204` | Incident-scoped investigation |
| `AgentOrchestrator._run_project_plan` | `AgentOrchestrator.run` | `backend/anvaya/agent/orchestrator.py:136` | When `project_id` resolves and no incident is found |

No other callers found in `backend/` or `frontend/`.

---

## 6. Objective classification / routing

File: `backend/anvaya/agent/orchestrator.py`, function `AgentOrchestrator.run` (lines 91–206).

### Current decision logic

1. Extract `incident_id` and `project_id` from the objective or execution record (`_extract_incident_id`, `_extract_project_id`).
2. If neither is found, try `_resolve_implicit_project` for artifact-generation language (lines 113–124).
3. `is_project = _is_project_id(incident_id) or _is_project_id(project_id)` (line 128).
4. If `project_id` and the `incident_id` does **not** resolve to a real `Incident` row, clear `execution.incident_id` and call `_run_project_plan` (lines 130–136).
5. Otherwise, set `execution.incident_id` and call `loop.run_investigation(...)` or `loop.run_adaptive(...)` (lines 138–206).

### `_run_project_plan` entry (lines 208–269)

Inside `_run_project_plan`:
1. Validate project exists.
2. Infer `action` (`infer_artifact_action`) and `requested` artifact types (`infer_artifact_types`), default to `["all"]` if no types named.
3. Resolve active model and call `AgentLoop.run_project_plan(execution, project_id, objective, profile, action, requested, active_model)`.

### Implication for `mixed.md`

The current classifier is binary: either project-only (→ `run_project_plan`) or incident-only (→ `run_investigation`). For mixed objectives, `AgentOrchestrator.run` needs a new classification path that detects **both** an incident reference/investigation trigger **and** artifact-generation language, then builds a single ordered plan with investigation steps followed by per-artifact `manage_artifacts` steps. The per-step loop from `fix_perfect.md` should then execute this combined plan.

---

## 7. Frontend state for multi-step reasoning

Files:
- `frontend/components/agent/agent-context.tsx`
- `frontend/components/agent/live-reasoning.tsx`

### Findings

- `AgentState` stores:
  - `reasoning: string` (single live reasoning text)
  - `currentAction: AgentCurrentAction | null` (contains `tool_name`, `label`, `status`, `step_index`)
  - `plan: AgentPlanStep[]`
  - `observations: AgentObservation[]` (each has `step_index` and `source`)
- `processLiveEvent` in `agent-context.tsx`:
  - `agent.reasoning_*` events set the single `reasoning` string and `reasoningSource`.
  - `agent.decision_started` and `agent.tool_requested` set `currentAction` with the event payload's `step_index`.
  - `agent.observation_created` appends observations with `step_index` and `source`; deduplicates by `step_index` + `source`.
  - `agent.plan_created` / `agent.plan_updated` replace the whole `plan` array.
- `LiveReasoningPanel` renders:
  - `ReasoningCard`: the current `reasoning` string.
  - `CurrentActionCard`: shows `step_index + 1` if present.
  - `PlanList`: renders all plan steps.
  - `ObservationList`: renders all observations, including `step_index + 1`.
  - `ReasoningHistory`: collapsible list of the last 10 reasoning/artifact events.

### Conclusion

The frontend already keys `currentAction` and `observations` by `step_index`. The live `reasoning` string is a single field, so it will naturally update to the latest step's reasoning; `ReasoningHistory` preserves earlier reasoning events. The plan list is rebuilt from `agent.plan_created` payloads. **No major frontend restructuring is required** for the multi-artifact fix — the existing components will display each step as long as the backend emits per-step `agent.reasoning_*`, `agent.decision_started`, `agent.tool_requested`, and `agent.observation_created` events with distinct `step_index` values.

A minor note: if the per-step reasoning text is important for each step, the current UI already surfaces it through `ReasoningHistory`; the live `ReasoningCard` will always show the most recent reasoning.

---

## 8. Discrepancies vs. `rules/agent.md`

No material discrepancies found. The rules-file trace is confirmed by current line numbers:

| Claim in `rules/agent.md` | Current code location | Confirmed? |
|---|---|---|
| `run_project_plan` builds a single plan step with full `requested_artifacts` list | `agent_loop.py:416-431` | Yes |
| Emits `agent.plan_created`, `_emit_reasoning`, `_emit_decision_started`, `_emit_tool_requested` once | `agent_loop.py:472-494` | Yes |
| `_execute_tool_step` called once for the whole batch | `agent_loop.py:496` | Yes |
| `handle_manage_artifacts` loops `for atype in artifact_types` and runs `ArtifactBuilder(...).run()` | `executor.py:867-891` | Yes |
| `ArtifactBuilder` is single-target (`self.target_type`) | `builder.py:56, 281-494` | Yes |
| `run_investigation` loops per step with full reasoning/decision/tool/observation cycle | `agent_loop.py:152-258` | Yes |
| `parse_scope` is correct and should not be touched | `scope.py:84-122` | Yes (not touched) |

### Minor implementation notes for the fix

- `requested_artifacts` expansion happens in three places:
  1. `run_project_plan` lines 410–414
  2. `_execute_tool_step` lines 798–801
  3. `handle_manage_artifacts` lines 759–760
  This is harmless but means that after `fix_perfect.md` builds one-element lists, all three expansion points become no-ops for the per-artifact loop. No change needed in `executor.py` or `builder.py`.
- `route_for_artifact_type` is the correct helper for mapping an artifact type to a frontend route (`routes.py:26-28`) and is already used by `ArtifactBuilder`.

---

## Exit criteria check

- [x] `docs/AGENTIC_AUDIT_MULTI_ARTIFACT.md` exists.
- [x] Every step in `audit_multi.md` has a corresponding entry in this document.
- [x] No contradiction with `rules/agent.md` was found.

This audit is complete. Proceeding to `fix_perfect.md`.

---

## 9. Mixed objective handling (`mixed.md`)

Implemented in `backend/anvaya/agent/orchestrator.py` (`AgentOrchestrator.run`) and `backend/anvaya/agent/agent_loop.py`.

- Detection: an objective is treated as **mixed** when it contains both a real incident reference (e.g. `INC-XXXX`) and artifact-generation language parsed by `infer_artifact_types` (`scope.py` alias table).
- Ordering default: when the objective does not explicitly order the two halves, the agent runs **investigation steps first**, then artifact-generation steps. This default is encoded in `AgentOrchestrator._run_mixed_plan`.
- Plan shape: `_build_plan(session, incident_id, profile)` produces the investigation steps; `_build_artifact_steps(...)` from `agent_loop.py` produces one `manage_artifacts` step per requested artifact type. The two lists are concatenated into a single ordered plan.
- Execution: `AgentLoop.run_investigation` executes the combined plan through the same per-step reasoning → decision → tool-requested → observation loop it already uses for pure investigations. The loop is tool-agnostic: each `manage_artifacts` step is narrated like any other step, including the per-artifact route from `route_for_artifact_type`.
- Routing regression: pure investigation objectives still call `run_investigation` with only investigation steps; pure multi-artifact objectives still call `AgentLoop.run_project_plan` through `AgentOrchestrator._run_project_plan`.
