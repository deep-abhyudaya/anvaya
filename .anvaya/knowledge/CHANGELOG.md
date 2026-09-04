# ANVAYA — Knowledge Changelog

## 2026-09-04 — Automatic Startuped behavioral signal instrumentation

### Architecture impact review

**WHAT CHANGED**
- Added a non-blocking Startuped behavioral signal adapter for backend, CLI, and frontend.
- Added automatic frontend tracking for route views, interactive clicks, form submissions, client errors, visibility/page-hide flushes, agent-panel open/close, mode changes, model/profile/incident selection, chat start/completion/failure, follow-ups, execution selection/cancellation, and new conversations.
- Added automatic backend middleware tracking for state-changing API requests.
- Added automatic agent `EventStore` mapping for reasoning, decision, tool, observation, generation, navigation, verification, and completion events.
- Added CLI shell signal coverage for every slash command and `/train` lifecycle stages.

**WHY**
- Track real ANVAYA user, agent, and CLI behavior as Startuped signals automatically after each interaction, without manual steps or frontend delay.

**BEFORE**
- Startuped integration was limited to explicit signal creation and SDK verification; product behavior was not automatically instrumented.

**AFTER**
- Real UI, auth, project, dataset, artifact, incident, agent, audit, and CLI interactions emit Startuped signals through a queued, non-blocking path.

**DEPENDENCIES**
- `STARTUPED_API_KEY`, `STARTUPED_SIGNALS_ENABLED`, Node runtime for the frontend BFF, and outbound HTTPS access.

**AFFECTED FLOWS**
- Browser → same-origin BFF → Startuped.
- Backend/CLI → queue worker → Startuped.
- Agent `EventStore` → queued Startuped signal.

**SECURITY IMPACT**
- The Startuped API key remains server-side only. Signal metadata is reduced to safe scalar values and never includes raw payloads, credentials, or hidden reasoning.

**FAILURE IMPACT**
- Startuped unavailability, rate limits, or network failures do not block UI, backend requests, CLI commands, or agent execution.

**MIGRATION/COMPATIBILITY IMPACT**
- Additive instrumentation only. No ANVAYA API contract, database schema, agent event contract, or artifact builder behavior was changed.

**DOCUMENTATION UPDATED**
- `04_INTEGRATION_GRAPH.md`, `13_API_AND_EXTERNAL_INTEGRATIONS.md`, `14_SECURITY_MODEL.md`, `24_ACTIVE_RECALL.md`, and this changelog.

## 2026-09-04 — Startuped XP product and SDK checklist actions

### Architecture impact review

**WHAT CHANGED**
- Added `@startuped-ai/sdk@1.0.4` to the frontend package and verified a real authenticated SDK request with explicit `X-Startuped-Client: sdk-js` attribution.
- Created organization-scoped Startuped CRM/marketing records for ANVAYA: one lead, one account, one project, and one campaign; the campaign was verified active.
- Confirmed the converted Anvaya Launchpad idea and existing Google Drive integration; Launchpad cached XP advanced from 76 to 80 during the workflow.

**WHY**
- Complete real Startuped hackathon product/developer actions with honest ANVAYA content and observable API receipts.

**BEFORE**
- Startuped MCP signal creation was verified, but product checklist resources and SDK-client attribution were not established by this repository workflow.

**AFTER**
- Live Startuped resources exist under organization `6a889189bc3a93adec557eac`; SDK auth validation and campaign activation are independently verified.
- Official skill-pack installation remains blocked because the documented GitHub repository is not visible even to the authenticated account; no skill-use success is claimed.

**DEPENDENCIES**
- `@startuped-ai/sdk@1.0.4`, Node/npm, Startuped REST/MCP services, API key, organization membership, and OAuth-backed Google Drive integration.

**AFFECTED FLOWS**
- Local server-side SDK/REST client → Startuped auth/product APIs → Anvaya organization resources → Launchpad XP/checklist.

**SECURITY IMPACT**
- SDK remains server-side only; credential is read at runtime from ignored local configuration; canonical HTTPS host prevents authorization loss on redirects.

**FAILURE IMPACT**
- Startuped API or network failures affect XP/resource synchronization only and do not alter ANVAYA runtime behavior.

**MIGRATION/COMPATIBILITY IMPACT**
- Frontend installs one additional production dependency. No ANVAYA API contract or runtime call path was changed.

**DOCUMENTATION UPDATED**
- `04_INTEGRATION_GRAPH.md`, `13_API_AND_EXTERNAL_INTEGRATIONS.md`, `14_SECURITY_MODEL.md`, `24_ACTIVE_RECALL.md`, `25_UNKNOWN_QUESTIONS.md`, and this changelog.

## 2026-09-04 — Startuped XP MCP integration configured and verified

### Architecture impact review

**WHAT CHANGED**
- Added project-scoped Startuped MCP configuration, a gitignored local Bearer credential overlay, narrowly scoped `create_signal` auto-approval, and the `startuped-xp` skill.
- Added the Startuped XP usage rule to `AGENTS.md` and documented the integration/security model.

**WHY**
- Enable truthful, one-per-shipped-unit Startuped XP signals after meaningful ANVAYA work, while preventing unrelated CRM/social MCP actions from being silently approved.

**BEFORE**
- Devin had no project Startuped MCP server, credential overlay, permission rule, or signal-quality skill.

**AFTER**
- Devin CLI 3000.4.25 loads `.devin/mcp_config.json`; `.devin/mcp_config.local.json` supplies `AUTH_HEADER`; only `mcp__startuped-ai__create_signal` is auto-approved.
- A live verification created test signal ID `6a9a067bb1c4733bfcfed03b` with strength 15.

**DEPENDENCIES**
- Devin CLI 3000.3+, Node/npx, `mcp-remote`, outbound HTTPS, Startuped API key and MCP service.

**AFFECTED FLOWS**
- Completed verified work → `startuped-xp` skill → MCP `create_signal` → Startuped marketing signal/XP system.

**SECURITY IMPACT**
- Introduces an external network/credential boundary. The real key is isolated in ignored local config; no wildcard MCP approval is granted; signaling loops are prohibited.

**FAILURE IMPACT**
- MCP, npm, network, or Startuped failures only skip XP logging and must not block product work.

**MIGRATION/COMPATIBILITY IMPACT**
- Dedicated MCP config paths require Devin 3000.3+; verified on 3000.4.25. Older clients would require `mcpServers` inside main config files.

**DOCUMENTATION UPDATED**
- `AGENTS.md`, `04_INTEGRATION_GRAPH.md`, `13_API_AND_EXTERNAL_INTEGRATIONS.md`, `14_SECURITY_MODEL.md`, `24_ACTIVE_RECALL.md`, `25_UNKNOWN_QUESTIONS.md`, and this changelog.

## 2026-09-03 — Fix `anvaya watch` synthetic feed: identical score on every event

### Root cause
`cli/watch.py::_synthetic_event` generated the full scenario timeline but
always returned `events[0]` — the first row of every attack scenario template,
which is the same benign-looking `auth_login` (empty process, no anomaly
flags). Every tick therefore produced an identical feature vector, and the
Alertness model scored them all identically (e.g. -0.5731).

### Changed
- `_synthetic_event` now draws a random timeline position (`rng.choice(events)`)
  and picks from the full scenario catalog (normal + suspicious + attack)
  instead of attacks only — a pure-attack feed could never emit `[normal]`,
  so the demo could not show the detector discriminating.

### Verification
- 16-tick feed through `score_and_maybe_flag`: **8 distinct scores**
  (-0.4446 to -0.6478) tracking event content (lateral_move, privilege_change,
  psexec.exe, network_connect, …), with both `[normal]` and `[DETECTED]`
  lines. Previously: 1 identical score on every tick.
- `pytest tests/test_cli.py tests/test_live_scoring.py -q` — **34 passed**.

### Notes
- 15/16 events detected in the sample run: the Alertness contamination is
  derived from the training data's attack rate (~0.4 with the small
  `/train`-style dataset), which makes the boundary aggressive. Engine-core
  behavior, left unchanged.

## 2026-09-03 — Fix sample dataset: all orbit risks collapsed to 0.99

### Root cause
`sample/sample_events.csv` (uploaded copy: `datasets/DS-B8AFF2D7.csv`) drew a
fully random public IP pair per row — 200 rows, 200 unique
(source_ip, dest_ip) pairs, every pair total exactly 1. Orbit strength
normalizes against the 95th-percentile pair total (=1 here), so every orbit
got strength 0.9, and with exactly one related incident each,
risk = 0.9 × 1.1 = 0.99 for all. The formula was correct; the data had zero
pair-repetition signal by construction.

### Changed
- New `scripts/generate_sample_events.py` (deterministic, seed 42)
  regenerates the sample with real topology: workstations clustered into
  three internal /24 subnets (one user per workstation), hub servers
  (proxy/web/mail/app/db) receiving repeated connections, an
  attack chain concentrating high/critical events on one path, a few
  repeated external attacker pairs, and an honest long tail of unique
  1-event external pairs.
- `sample/sample_events.csv` regenerated; `datasets/DS-B8AFF2D7.csv`
  (the uploaded copy) refreshed with the same content — rebuild the world
  for that dataset to see the new spread.

### Verification
- World build on the regenerated sample: orbit risk **9 distinct values**
  (0.124–1.0, was 1 value), reach attackScore 8 distinct, blast 7 distinct,
  severity {low 96, medium 31, high 17, critical 6}.
- `/train`-generated datasets (simulator path) were already healthy —
  `datasets/DS-90E8DA8D.csv` pair totals vary ({2:4, 1:13, 3:1, 6:1, 4:2}).

## 2026-09-03 — Scoped build state, real arena scores, one-execution multi-artifact builds

### Changed
- **Frontend — per-artifact build scoping (Bug 1).** `lib/build.ts`
  `useArtifactSource` now takes a required `artifactType` and derives
  `isBuilding` from the in-progress item (`activeBuildTarget`:
  `build.artifacts[currentIndex].targetArtifactType`, falling back to
  `build.target`); `failed` builds no longer hold the shell open. All 10
  tiles (12 call sites) pass their own artifact type. Generating one
  artifact no longer shows the build shell on unrelated pages.
- **Backend — real arena/trophy engine scores (Bug 2).** `world.py`
  replaces the hardcoded arena constants (`SENTINEL 0.6+0.1*caught`,
  `BLASTSCOPE attack_paths/50`, `LEDGER 0.2`, `WHATIF 0.3`, stage rates
  `0.4/0.6/0.8`, trophy `ledger: 0.0`) with data-derived values:
  detection coverage (attributed events / telemetry), attack-family
  attribution rate, evidence-completeness validation rate, mean blast
  radius, mean per-incident risk, and audit-chain completeness.
- **Backend — multi-target builds under one execution.** `POST
  /projects/{id}/build` now accepts `targets`/`requested_artifacts` lists
  (single-target behavior unchanged) and `dataset_id`. New
  `generations/builder.py::build_artifacts` runs each target's
  `ArtifactBuilder` sequentially against the SAME `execution_id` and emits
  a final `agent.completed` so the panel returns to idle; missing
  generations emit `generation.failed` without aborting the batch.
- **Frontend — panel continuity.** New `useAgent().attachExecution(executionId)`
  subscribes the Agent Panel to an externally-created execution (mode
  switch before `setExecutionId` so the SSE effect connects; replays the
  event log from sequence 0). Project page `handleGenerate` now calls
  `createBuildSession` with the selected targets and attaches the returned
  `execution_id`, instead of the event-less synchronous `/generate` call.
- **Simulator — topology + severity diversity.** `scenarios.py` HOSTS pool
  6→32, USERS 6→20, with `BACKBONE_HOSTS` (SRV-DB01/APP01/WEB01, JMP-01)
  shared across instances; `generator.py` gains a deterministic
  `namespace_seed` host/user remap (stride-spaced by instance index),
  per-instance ambient benign network traffic (one benign incident group
  per instance, instance-varying backbone targets), and a per-event
  `severity` column mirroring `world_architect.SEVERITY_BY_FAMILY`.
  Event dicts now list `event_type` before `event_id` — profiling mapped
  canonical `event_type` to the `event_id` column (first-match wins),
  which fragmented every benign row into its own `EVT-*` pseudo-incident.
- **Test fix.** `tests/test_live_scoring.py` normal-event fixture pins its
  timestamp to hour 1 (inside the generator's midnight-base training
  distribution); `datetime.now()` made it time-of-day flaky — the event
  scored 0.001 from the Isolation Forest boundary.

### Added
- `tests/test_multi_target_build.py` — sequential multi-target build under
  one execution (event continuity, per-target `generation.started` order,
  final `agent.completed`) and failed-generation batch continuation.

### Verification
- `pytest tests/ -q --no-header` — **310 passed, 16 failed** (14 documented
  pre-existing LLM-catalog/CLI failures + 2 pre-existing flakes:
  `test_cancel_background_execution` threading race passes in isolation,
  `test_gmicloud_catalog` LLM-provider filtering unrelated).
- `npx tsc --noEmit` and `npx eslint` on changed frontend paths — clean.
- Fresh dataset (seed 7): 41 incidents, severity {low 30, medium 7, high 4},
  blast 8 distinct values, risk 10, orbit risk 5, reach attackScore 7 —
  real variance across all affected pages.

### Notes
- `routers/metrics.py::get_engine_consensus` (lines 70-93) still returns
  hardcoded engine scores for all three stages — flagged in self-audit as
  the same Bug-2 class, but the endpoint has zero frontend consumers
  (`AnvayaAPI.engines` is unused), so it was reported, not reworked.
- Demo orchestrator and direct `generate_for_scenario` callers do not pass
  `namespace_seed` and remain byte-identical.

## 2026-09-03 — CLI narration rebuild and multi-incident batch demo

### Changed
- `backend/anvaya/cli/typer_app.py`:
  - `demo()` now prints step-by-step Rich narration for the full self-correction pipeline (dataset, training, attack, detection, self-correction, BlastScope, What-If, seal, audit).
  - `demo()` accepts a `--delay` option that paces narration by sleeping between step blocks.
  - `demo()` uses the live `on_step` callback on `DemoOrchestrator.run_full_demo()` so output streams as steps complete.
  - New `demo-batch` command runs the full lifecycle across many varied incidents; first `N` are narrated in full detail, the rest as compact one-line summaries, ending with a batch results table.
  - `train()` now narrates dataset generation and the Sentinel self-correction cycle, and surfaces real prior-cycle detail when an incident is already caught.
- `backend/anvaya/demo/orchestrator.py`:
  - `DemoOrchestrator` refactored into shared `_run_single_incident`, `_run_self_correction`, `_run_blastscope`, `_run_whatif`, `_seal_incident`, and `_verify_audit_chain` helpers.
  - `run_full_demo()` accepts an optional `on_step` callback for live progress streaming and preserves the legacy `steps` shape.
  - New `run_batch_demo(count, scenarios, on_step, on_incident)` trains models once, then loops over the four `ATK-*` templates with varied actor, host, seed, and timestamp to produce the requested number of incidents.
- `simulator/anvaya/generator.py`:
  - `generate_for_scenario()` now accepts optional `scenario_seed`, `actor`, and `host` overrides so batch incidents look distinct while preserving the underlying attack pattern.

### Added
- `tests/test_demo_batch.py` — verifies `run_batch_demo` creates the requested count of real incidents, produces valid audit chains, and that summary counts sum to the total.

### Updated
- `.anvaya/knowledge/08_CLI.md` — documented `demo-batch`, `demo --delay`, and the new `train` narration behavior.
- `.anvaya/knowledge/10_ORCHESTRATION_AND_LOGISTICS.md` — documented `DemoOrchestrator.run_batch_demo` and the callback-based progress streaming.
- `.anvaya/knowledge/22_TESTING_AND_VALIDATION.md` — added `tests/test_demo_batch.py` to the key test files and updated the baseline counts.
- `.anvaya/knowledge/24_ACTIVE_RECALL.md` — added Q15 about the CLI demo and batch commands.

### Verification
- `.venv/bin/ruff check backend/anvaya/cli/typer_app.py backend/anvaya/demo/orchestrator.py simulator/anvaya/generator.py tests/test_demo_batch.py` passes.
- `.venv/bin/pytest tests/test_self_correction.py tests/test_demo_batch.py -q` passes.
- `.venv/bin/pytest tests/ -q --no-header` result: 309 passed, 15 failed (pre-existing unrelated failures).

## 2026-09-02 — Put page controls left of user dropdown; render AI from `TopBar`

### Changed
- `frontend/components/top-bar.tsx`:
  - `TopBar` now imports and renders `AgentConsoleTrigger` itself, so it always appears as the rightmost top-bar item.
  - The right side now renders, in order: page-level `right` slot (e.g. `ResetLayoutButton`), `UserDropdown`, `AgentConsoleTrigger`.
- `frontend/components/app-shell.tsx`:
  - Removed `AgentConsoleTrigger` from the `right` prop; `right` is now passed straight to `TopBar`.

### Updated
- `.anvaya/knowledge/06_FRONTEND.md` — updated `TopBar`/`UserDropdown`/`AgentConsoleTrigger` source lines and the top-bar agent trigger description.
- `.anvaya/knowledge/24_ACTIVE_RECALL.md` — Q25 updated to reflect the new right-side order.

### Verification
- `npx tsc --noEmit` in `frontend/` passes.
- `npm run lint` in `frontend/` passes.
- `npm run build` in `frontend/` passes and emits all 29 app routes.

## 2026-09-02 — Consolidate top bar user controls into a dropdown

### Changed
- `frontend/components/top-bar.tsx`:
  - Replaced `UserMenu` (org link + email + sign-out icon) with a single `UserDropdown` trigger that shows the user's name.
  - Removed the three-dots `MoreHorizontal` button and `TopBarMenu` (page metrics/context menu).
  - `UserDropdown` panel contains:
    - The user's name as a header,
    - An organization/workstation link formatted as `<org name> / <email>`,
    - A `Sign out` button.
  - Removed the `DefaultMetrics` and `TopBarMenu` components and the unused `useAnvaya` / `useLiveClock` / `HEADER_DEFAULTS` / `MoreHorizontal` imports.
  - The right side of the top bar now renders `UserDropdown`, then the `right` slot (page-level controls). `AgentConsoleTrigger` was moved into `TopBar` in the next change.
- `frontend/app/projects/page.tsx` and `frontend/app/projects/[projectId]/page.tsx`:
  - Removed the `right={<span>{user?.email}</span>}` prop so the email no longer appears directly in the top bar.

### Updated
- `.anvaya/knowledge/06_FRONTEND.md` — updated `TopBar` and `UserDropdown` source lines and descriptions.
- `.anvaya/knowledge/24_ACTIVE_RECALL.md` — added Q25 describing the top-bar right-side layout and sign-out flow.

### Verification
- `npx tsc --noEmit` in `frontend/` passes.
- `npm run lint` in `frontend/` passes.
- `npm run build` in `frontend/` passes and emits all 29 app routes.

## 2026-09-02 — Replace top-bar agent toggle with SiriOrb + `AI` label

### Changed
- `frontend/components/agent/agent-console.tsx::AgentConsoleTrigger`:
  - Replaced the generic `PanelRight` icon toggle with a compact `SiriOrb` status button and an `AI` label to its right.
  - The trigger is rendered in `TopBar` on the right side of the header.
  - The `SiriOrb` colors stay in sync with the same state-driven palette as the console header orb:
    - `c2` = mode color (`chat` = blue, `agentic` = orange),
    - `c3` = active incident severity (`high` = red, `medium` = amber, `low` = green),
    - `c4` = selected model availability (`available` = sky, `configured` = amber, `unavailable` = gray).
  - The `AIState` follows execution status: `thinking` while running, `done` on completion, `error` on failure, `idle` otherwise.
- `frontend/components/agent/agent-console.tsx`:
  - Removed the now-unused `PanelRight` import and `PanelRightActive` SVG component.

### Updated
- `.anvaya/knowledge/06_FRONTEND.md` — added `AgentConsoleTrigger` to the key-components table and documented the top-bar trigger behavior.
- `.anvaya/knowledge/24_ACTIVE_RECALL.md` — Q20 now notes that the top-bar trigger shares the same `SiriOrb` palette and `AIState` mapping as the console header orb.

### Verification
- `npx tsc --noEmit` in `frontend/` passes.
- `npm run lint` in `frontend/` passes.
- `npm run build` in `frontend/` passes and emits all 29 app routes.

## 2026-09-02 — Fix agent-console delete/overwrite command crash

### Fixed
- `frontend/components/agent/agent-console.tsx`:
  - `message.matchAll(artifactTypePattern)` threw `TypeError` because the regex lacked the `g` flag.
  - Kept the case-insensitive `artifactTypePattern` for the `isArtifactCommand` `RegExp.prototype.test()` check.
  - Added a derived `artifactTypePatternAll = new RegExp(artifactTypePattern.source, "gi")` used only by `matchAll`, ensuring the delete/overwrite artifact-type extraction works on the whole message without global-regex `lastIndex` side effects from the earlier `.test()` call.
  - Reordered the artifact-type alternation to prefer the longer, more specific phrase before its one-word fallback (e.g., `impact gallery` before `impact`, `trophy wall` before `trophy`, `reach board` before `reach`).

### Verification
- `npm run lint` in `frontend/` passes.
- `npm run build` in `frontend/` passes.

## 2026-09-02 — Agent console header orb reacts to mode, model, and incident

### Changed
- `frontend/components/agent/agent-console.tsx`:
  - Removed the top-left "Agent" text and `Bot` icon.
  - Added `Anvaya AI / <mode>` label immediately to the right of the orb (`<mode>` is `ask` or `agent` at reduced opacity).
  - Moved the `SiriOrb` status indicator from the right-side provider-status button to the top-left of the agent console header.
  - Renamed `ProviderStatusButton` to `AgentOrbButton`; it still opens the provider-status panel and keeps the active-provider count dot.
  - `AgentOrbButton` now uses a custom, state-driven multi-color `SiriOrb` palette:
    - `c2` (bloom) = mode color (`chat` = blue, `agentic` = orange).
    - `c3` = incident severity color (`high` = red, `medium` = amber, `low` = green; falls back to mode color).
    - `c4` = model availability color (`available` = sky, `configured` = amber, `unavailable` = gray; falls back to mode color).
    - `c1` and `c4` use `color-mix()` to add tonal depth.
  - The orb pulses (`listening`) for ~650ms whenever ask mode, selected model, or active incident changes.
  - Execution status still sets the base `AIState`: `thinking` while running, `done` on completion, `error` on failure, `idle` otherwise.

### Updated
- `.anvaya/knowledge/06_FRONTEND.md` updated with the new `AgentOrbButton` row and an "Agent console status orb" section.

### Verification
- `npm run build` in `frontend/` passes with no type/lint errors.
- `npm run lint` in `frontend/` passes.

> Record architecture/behavior changes and documentation updates here.

## 2026-09-01 — Initial deep codebase mastery + knowledge base

### Added
- Created `.anvaya/knowledge/` hierarchy:
  - `00_MASTER_INDEX.md` — navigation, top-20 lists, source truth.
  - `01_SYSTEM_OVERVIEW.md` — executive model, major subsystems, data flows.
  - `02_ARCHITECTURE.md` — layered architecture + component diagram.
  - `03_RUNTIME_TOPOLOGY.md` — Docker, ports, CLI entry points, processes.
  - `04_INTEGRATION_GRAPH.md` — edge inventory with mechanism/security.
  - `05_DATA_FLOWS.md` — 6 major flow diagrams.
  - `06_FRONTEND.md` — Next.js stack, providers, data flow.
  - `07_BACKEND.md` — FastAPI routers, engines, DI.
  - `08_CLI.md` — shell, Typer, watch, state.
  - `09_ISOLATION_AND_EXECUTION.md` — sandbox/process boundaries.
  - `10_ORCHESTRATION_AND_LOGISTICS.md` — agent loop, planner, subagents.
  - `11_AI_AND_DETECTION.md` — ML engines, features, providers.
  - `12_INCIDENT_RESPONSE.md` — incident/self-correction lifecycle.
  - `13_API_AND_EXTERNAL_INTEGRATIONS.md` — Tavily, n8n, Gmail, Lyzr, etc.
  - `14_SECURITY_MODEL.md` — auth, audit, trust boundaries.
  - `15_CONFIGURATION.md` — env vars, provider toggles.
  - `17_DATABASE_AND_STATE.md` — SQLModel schema, state machines.
  - `19_FEATURE_TRACES.md` — end-to-end traces.
  - `20_FAILURE_MODES.md` — failure matrix + debug first-look.
  - `24_ACTIVE_RECALL.md` — source-backed question bank.
  - `25_UNKNOWN_QUESTIONS.md` — open questions.
- Added `.devin/rules/00-anvaya-core.md` establishing repository-first, security-first, integration-first, active-recall, and documentation-sync rules.
- Added `.devin/rules/01-documentation-protocol.md`.
- Added `.devin/rules/02-architecture-change-protocol.md`.
- Added `.devin/rules/03-integration-tracing.md`.
- Added `.devin/rules/04-security-sensitive-changes.md`.
- Added `.devin/rules/05-active-recall-maintenance.md`.
- Added `.devin/rules/06-knowledge-integrity.md`.

### Verified
- Confirmed live scoring is implemented in `backend/anvaya/live/__init__.py:112-162`.
- Confirmed shared dispatch point in `backend/anvaya/live/dispatch.py:232-276`.
- Confirmed `AlertnessEngine` Isolation Forest training/eval in `ml/anvaya/alertness/__init__.py`.
- Confirmed `ToolRegistry` with ~40 tools and fallback providers in `backend/anvaya/agent/registry.py`.
- Confirmed agent SSE stream in `frontend/lib/api.ts` and `backend/anvaya/routers/agent.py`.

### Test verification
- Ran `DATABASE_URL=sqlite:///./test_mastery.db .venv/bin/python -m pytest tests/test_live_scoring.py tests/test_provider_adapters.py -q --no-header` — **18 passed**.

### Notes
- All knowledge files now marked ✅ in `00_MASTER_INDEX.md`.
- Unknowns recorded in `25_UNKNOWN_QUESTIONS.md`.

## 2026-09-02 — SmoothUI agent console integration + Tavily endpoint

### Added
- Installed SmoothUI components into `frontend/components/smoothui/`:
  `ai-reasoning`, `ai-tool-call`, `ai-task-list`, `ai-artifact`, `ai-citation`, `ai-branch`, `ai-diff`, `ai-approval`, `ai-sources`, `siri-orb`, `ai-orb-face`, `ai-core`.
- Added shadcn-semantic token aliases in `frontend/app/globals.css`
  (`--color-foreground`, `--color-muted-foreground`, `--color-destructive`, `--color-destructive-foreground`) mapped to the Claude palette.
- New backend route `POST /tavily/search` in `backend/anvaya/routers/agent.py`
  that calls `TavilyAdapter.search` and returns live Tavily results or the
  honest local fixture when `TAVILY_API_KEY` is absent.

### Changed
- `frontend/lib/api.ts::AnvayaAPI.tavilyLookup` now calls `/tavily/search`
  directly and returns a typed promise.
- `frontend/components/agent/agent-console.tsx`:
  - `ToolCard` replaced with `AIToolCall`, including Tavily source rendering.
  - `MessageCard` now renders `INC-...` references as `AICitation` links.
  - `ProviderStatusButton` uses a small `SiriOrb` as the status indicator.
  - Added `ReplayBranchPanel` (using `AIBranch` + `useProjectReplay`) for
    pre/post-patch replay divergence.
  - Added `PendingActionGate` using `AIDiff` + `AIApproval` to require
    explicit approval before delete/overwrite artifact actions.
  - Added `runTavily` trigger so users can type `tavily <indicator>`,
    `lookup <indicator>`, or `search <indicator>` to fire a real Tavily call.
- `frontend/components/agent/live-reasoning.tsx`:
  - `ReasoningCard` replaced with `AIReasoning`.
  - `PlanList` replaced with `AITaskList`.
- `frontend/components/build/build-timeline.tsx`:
  - `ArtifactRow` replaced with `AIArtifact`.
- `frontend/components/smoothui/*` color classes were normalized to ANVAYA
  tokens (`bg-canvas-subtle`, `bg-surface`, `bg-accent`, `text-bg`,
  `border-hairline`, `text-critical`, `bg-critical/10`) and hardcoded oklch
  values in `ai-diff`, `ai-task-list`, `ai-tool-call`, `ai-core` were
  swapped for CSS variables.

### Fixed
- `frontend/components/agent/agent-console.tsx`:
  `TraceGroup` list keys now use the first event's `id` or
  `execution_id:sequence` plus the group index, preventing React key
  collisions (`status:1` duplicates) when the trace contains events from
  multiple executions or events without a persisted `id`.

### Verification
- `npm run build` in `frontend/` passes with no type/lint errors.
- `backend/.venv/bin/python -c "from anvaya.routers.agent import router"` succeeds
  and `'/tavily/search'` is present in the route table.
- Smoke-tested `POST /api/v1/tavily/search` with `indicator=192.168.1.1`;
  returned the expected local fixture and honest `note`.
- Frontend dev server and FastAPI server both start; root page loads.

### Credentials needed for live third-party use
- `TAVILY_API_KEY` must be set (in `.env` or environment) for Tavily to
  return real web-search results; otherwise it serves the labeled local
  fixture.

## 2026-09-02 — Fix generated incidents stuck at `detected` with empty event counts

### Fixed
- `backend/anvaya/generation.py::_persist_incidents()` now transitions
  dataset-derived incidents to `IncidentStatus.ACTIVE` and stores their
  real `event_count`, instead of leaving them frozen at `detected`.
- `frontend/components/tiles/incidents-tile.tsx` now reads `event_count`
  from the `/incidents` live API response instead of discarding it.

### Added
- `IncidentStatus.ACTIVE` in `backend/anvaya/models/enums.py` with
  valid transitions `detected → active` and `active → analyzed`.
- `Incident.event_count` nullable column in
  `backend/anvaya/models/incident.py` populated by `_persist_incidents()`.

### Verification
- `pytest tests/test_incident.py backend/anvaya/tests/test_world_incident_basis.py -q` — **12 passed**.
- `pytest tests/test_artifact_generation.py tests/test_golden_artifact_flow.py tests/test_world_architect.py -q` — **11 passed**.
- `pytest tests/test_api.py -q` — **13 passed**.
- `tsc --noEmit` in `frontend/` passes.
- Manual `ArtifactGenerator.generate_all(["incidents"])` against a seeded
  dataset produced rows with `status="active"`, `event_count=N`, and
  `evidence_summary="N events"`.

## 2026-09-02 — Fix runtime TypeError in Segments tile and top-bar hydration mismatch

### Fixed
- `frontend/components/tiles/segments-tile.tsx` now normalizes incoming
  `Segment` data with `toSegment()`, supplying safe defaults for `traffic`,
  `reach`, `depth`, `rank`, and `risk`. This prevents `TypeError: Cannot
  read properties of undefined (reading 'toFixed')` when live build elements
  or stored payloads omit `traffic` or contain unexpected shapes.
- `RISK_TONE` and `RISK_SEV` lookups in the segment graph overlay and list
  rows now fall back to `0` / `"muted"` for unrecognized risk values.
- `frontend/components/top-bar.tsx::UserMenu` now waits for client mount
  before rendering auth-stateful UI, eliminating a React hydration mismatch
  between server and client when the auth session resolves asynchronously.

### Changed
- `.anvaya/knowledge/06_FRONTEND.md` updated to reflect the `UserMenu`
  client-only hydration guard and the corrected `TopBar` source line.

### Verification
- `bun tsc --noEmit` in `frontend/` passes.
- `bun lint` in `frontend/` passes.
- `bun next build` in `frontend/` passes and emits all 29 app routes.

## 2026-09-02 — Fix duplicate graph edge keys in Segments tile

### Fixed
- `frontend/components/tiles/segments-tile.tsx::toSegment()` now generates
  unique `SRC-{n}` / `DST-{n}` placeholders for missing `from`/`to` endpoints
  and rejects empty strings, preventing duplicate React keys like `->` when
  build elements or stored payloads omit endpoint labels.
- The `nodes` list in `segments-tile.tsx` now derives from both `from` and
  `to` endpoints (deduplicated), so every edge has a corresponding node.
- `frontend/lib/graph.tsx::GraphCanvas` now includes the edge index in each
  edge React key, making parallel edges between the same two nodes stable.

### Verification
- `bun tsc --noEmit` in `frontend/` passes.
- `bun lint` in `frontend/` passes.
- `bun next build` in `frontend/` passes and emits all 29 app routes.

### Affected flows
- `POST /projects/{project_id}/{artifact_type}/regenerate` and the agent
  `manage_artifacts` path for `incidents` now persist `active` incidents.
- `GET /incidents` and `GET /incidents/{id}` now return `event_count`.
- Incidents tile status filter tab `ACTIVE` now matches generated incidents.

## 2026-09-02 — Fix incident risk scores locked to 0.47 / 0.62

### Fixed
- `backend/anvaya/world.py::build_world_model()` now groups dataset-derived
  incidents by `(host, user, attack_family)` (falling back to
  `source/destination` when host/user are missing) instead of by exact
  `(source_ip, destination_ip, family)`. This matches the identity fields
  the UI already uses and lets related activity on the same host/user
  accumulate into multi-event groups.
- Removed the severity gate that discarded `low` and `medium` events before
  they could become incidents. `is_incident` now uses
  `_severity_rank(event.severity) >= 1`, which admits all four severity
  levels while keeping the explicit attack-label check.

### Updated
- `severity_basis` and `risk_basis` now include the `host` and `user` from
  the grouping key for clearer provenance.
- `WorldIncident` title, `host`, and `user` fields are derived from the
  grouped host/user, with source/destination as a fallback for display.

### Verification
- `pytest backend/anvaya/tests/test_world_incident_basis.py -q` — **5 passed**.
- `pytest tests/test_incident.py tests/test_artifact_generation.py tests/test_world_architect.py tests/test_golden_artifact_flow.py tests/test_api.py tests/test_self_correction.py -q` — **47 passed**.
- Manual before/after on the same 100-row seeded dataset:
  - **Old logic:** 47 incidents, only 2 distinct risk scores
    (`0.47` × 24, `0.62` × 23).
  - **New logic:** 28 incidents, 17 distinct risk scores, ranging
    `0.17` to `0.74`, with severities `low`/`medium`/`high`/`critical`
    and group sizes 1–8.

### Affected flows
- `manage_artifacts` / `POST /projects/{project_id}/incidents/regenerate`
  now returns incidents with variable `risk_score` and `blast_radius_score`.
- `GET /projects/{project_id}/incidents/latest` payload now includes
  multi-event incidents and low/medium severities.

## 2026-09-02 — Fix Risk Orbits scores locked to ~0.10/0.11 and UI collisions

### Fixed
- `backend/anvaya/world.py` now aggregates orbit pairs by IPv4 /24 prefix
  (configurable via `orbit_prefix_octets`) with a same-subnet exact-pair
  fallback. This keeps orbits IP-pair-based while letting realistically
  clustered traffic collapse into the same orbit.
- `backend/anvaya/world.py` now derives the interaction-strength scaling
  constant from the data (95th-percentile total maps to strength 0.9),
  instead of the hardcoded `* 20`. This prevents every orbit from being
  squashed to ~0.10/0.11 when `total` does not vary.
- `backend/anvaya/world.py` clamps `orbit_risk` to 1.0 and records
  `scaling_constant` and `reference_total` in `risk_basis` for provenance.
- `frontend/components/tiles/risk-orbits-tile.tsx` now computes a node's
  displayed `risk` from its actual orbit event total (`source_events` +
  `dest_events`), not from `impact_score`. This fixes the inconsistent
  "risk 1.00 · 0 events" tooltips.
- `frontend/components/orbit-network.tsx` now draws node labels as radial
  leader-line labels and hides labels for zero-event nodes, replacing them
  with a `+N nodes` cluster marker. This eliminates the overlapping
  center-cluster labels.

### Added
- `tests/test_regression_fixes.py::test_orbit_risk_scores_have_spread` to
  guard against the uniform-orbit-risk regression.

### Changed
- `WorldModel.edges`, the internal graph `g`, and `incident_pairs` all use
  the same `_pair_bucket()` logic so orbit/event/blast-basis node identities
  stay consistent across the backend.

### Verification
- `pytest tests/test_artifact_generation.py tests/test_golden_artifact_flow.py tests/test_regression_fixes.py -q` — **18 passed**.
- `pytest backend/anvaya/tests/test_world_incident_basis.py backend/anvaya/tests/test_builder_reason.py -q` — **11 passed**.
- `pytest tests/test_world_architect.py -q` — **2 passed**.
- `pytest tests/ -q --no-header --ignore=tests/test_mcp_server.py` — **305 passed, 12 failed** (pre-existing LLM-catalog / provider failures, no orbit/world regressions).
- `npm run build` in `frontend/` passes with no type/lint errors.

### Notes
- The seeded `sample_events.csv` uses fully random public IPs with no
  subnet clustering, so /24 grouping still yields uniform totals. On
  datasets with realistic internal-subnet clustering, the new logic
  produces a real spread of `risk_score` values.
