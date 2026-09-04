# Live-Build (System B) Removal Audit

## Scope

This audit documents the complete removal of the **Live-Build code-scaffolding feature** (System B) while preserving the **artifact manifest build panel** (System A).

## Disambiguation

- **System A — KEEP**: The artifact generation flow driven by `manage_artifacts`, `ArtifactBuilder`, `generations/manifests.py`, `lib/build.ts`, and `components/build/build-timeline.tsx`. It emits `generation.*` / `artifact.*` / `element.*` / `navigation.*` events and is the wanted “BUILDING / Artifact / 10 / 11 artifacts complete” panel.
- **System B — REMOVE**: The `Discover → Plan → Build → Run → Observe` live code-scaffolding mode that writes files into the frontend codebase, runs shell commands, and previews the result. This is the `LIVE-BUILD` tab, the `/live-build/[executionId]` page, the `backend/anvaya/agent/live_build/` package, and all associated state/reducer wiring.

## Full reference inventory

Searched the repo for `live_build`, `liveBuild`, `LiveBuild`, `live-build`, `LIVE_BUILD`, and `livebuild` (case-insensitive). Only non-venv hits are listed below.

### System B files — to be removed

| File | Classification | Action |
|------|----------------|--------|
| `backend/anvaya/agent/live_build/__init__.py` | System B package entry | Delete with package |
| `backend/anvaya/agent/live_build/engine.py` | System B (`LiveBuildEngine`) | Delete with package |
| `backend/anvaya/agent/live_build/planner.py` | System B (`is_live_build_objective`, `plan_build`, `BUILD_KEYWORDS`) | Delete with package |
| `backend/anvaya/agent/live_build/runner.py` | System B (`LiveBuildRunner`, file/command/preview ops) | Delete with package |
| `backend/anvaya/agent/live_build/state.py` | System B (`LiveBuildState`, `BuildAction`, `LIVE_BUILD_PHASES`) | Delete with package |
| `backend/anvaya/agent/live_build/templates.py` | System B (dashboard templates) | Delete with package |
| `backend/anvaya/agent/live_build/__pycache__/*` | Compiled System B cache | Delete with package |
| `backend/anvaya/agent/orchestrator.py` | System B gate + `_run_live_build` | Edit: remove import, gate, method |
| `backend/anvaya/agent/executor.py` | System B tool handler | Edit: remove import and `handle_live_build` |
| `backend/anvaya/agent/registry.py` | System B tool registration | Edit: remove `live_build` tool definition |
| `frontend/components/agent/live-build-panel.tsx` | System B UI panel | Delete |
| `frontend/app/live-build/[executionId]/page.tsx` | System B full-page view | Delete (no remaining links) |
| `frontend/components/agent/agent-console.tsx` | System B tab wiring | Edit: remove import, tab, auto-switch, render branch |
| `frontend/components/agent/agent-context.tsx` | System B state & reducer | Edit: remove `LiveBuildState`, `liveBuild` field, live-build actions, live-build reducer cases, live-build event handlers |

### System A files — confirmed untouched

| File | Live-build hits? | Verdict |
|------|------------------|---------|
| `frontend/lib/build.ts` | None | System A; do not touch |
| `frontend/components/build/build-timeline.tsx` | None | System A; do not touch |
| `backend/anvaya/generations/builder.py` | None | System A; do not touch |
| `backend/anvaya/generations/manifests.py` | None | System A; do not touch |

### Documentation — stale reference to be updated

| File | Hit | Action |
|------|-----|--------|
| `docs/AGENTIC_AUDIT_MULTI_ARTIFACT.md` | Line 191 references `is_live_build_objective(objective)` → `_run_live_build` | Update to remove the live-build step and renumber the `_run_project_plan` flow |
| `.devin/workflow/audit_multi.md` | Line 45 lists `live-build-panel.tsx` as a file to check | This is a workflow file; not modified because it is part of the multi-artifact narration sequencing work and is not a runtime dependency |

## Backend routing root cause

In `backend/anvaya/agent/orchestrator.py`, `_run_project_plan` currently checks `is_live_build_objective(objective)` before inferring artifact actions. The `is_live_build_objective` keyword scoring in `planner.py` gives `+2` for words like `create`, so an objective like **“create NERVE ARBOR”** can cross the `score >= 3` threshold and route into `LiveBuildEngine` instead of the artifact manifest builder.

The fix is to delete the gate and `_run_live_build`, so `_run_project_plan` goes directly from project validation to `infer_artifact_action` / `infer_artifact_types` and `AgentLoop.run_project_plan`.

## Live-build event types (System B only)

Emission and handling for the following event types will be removed. None of these are used by System A:

- `livebuild.started`
- `livebuild.phase.started`
- `livebuild.planning`
- `livebuild.plan.ready`
- `livebuild.action.started`
- `livebuild.action.completed`
- `livebuild.action.failed`
- `livebuild.discovered`
- `file.create.started` / `file.create.completed` / `file.create.failed`
- `file.edit.started` / `file.edit.completed` / `file.edit.failed`
- `route.create.started` / `route.create.completed`
- `component.create.started` / `component.create.completed`
- `style.create.started` / `style.create.completed`
- `command.started` / `command.completed` / `command.failed`
- `test.started` / `test.passed` / `test.failed`
- `server.starting` / `server.started`
- `terminal.output`
- `browser.refreshing` / `browser.updated`

`agent.observation` is a generic event used by the adaptive/frontier loops. In `agent-context.tsx` it is currently co-handled with `livebuild.discovered` and routed to live-build state; it will be converted to a generic `appendObservation` call.

`agent.completed` and `agent.failed` are generic events already handled elsewhere in the same switch. The live-build-specific duplicate `case` branches with `if (p.live_build) { ... }` will be removed.

## Front-end routing

No remaining call sites to `/live-build/${executionId}` were found outside `agent-console.tsx` (which is being edited) and `app/live-build/[executionId]/page.tsx` (which is being deleted). Therefore the route file can be safely deleted rather than redirected.

## Verification results

1. **TypeScript build**: `bunx tsc --noEmit` and `bun run build` both pass with no `liveBuild`/`LiveBuild`/`live-build` references. The `/live-build/[executionId]` route is gone from the build manifest.
2. **Python tests — targeted**:
   - `tests/test_run_project_plan.py` — 8 passed (includes new `test_create_nerve_arbor_routes_to_artifact_builder`).
   - `tests/test_artifact_generation.py`, `tests/test_builder_streaming.py`, `tests/test_golden_artifact_flow.py`, `tests/test_agent_live_loop.py`, `tests/test_agent.py`, `tests/test_agentrouter.py` — 39 passed.
   - `tests/test_regression_fixes.py`, `tests/test_subagents.py`, `tests/test_api.py` — 30 passed.
3. **Regression test for `create NERVE ARBOR`**: Added `test_create_nerve_arbor_routes_to_artifact_builder` in `tests/test_run_project_plan.py`. It asserts the plan contains exactly one `manage_artifacts` step for `arbor`, no `live_build` tool call, and completes successfully.
4. **Full Python test suite**: `pytest tests/` — 273 passed. The 16 failures are in unrelated files (`test_catalog_intelligence.py`, `test_cli_validation.py`, `test_llm_providers.py`, `test_subagents.py::test_background_subagent_and_list`) and contain no `live_build` references; these are pre-existing / environment / network / test-isolation issues outside the scope of this removal.
5. **System A untouched**: `lib/build.ts`, `components/build/build-timeline.tsx`, `generations/builder.py`, and `generations/manifests.py` were not modified.
