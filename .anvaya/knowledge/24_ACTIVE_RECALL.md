# ANVAYA — Active Recall Question Bank

> Source-backed answers. Cover the card, answer, then check. Update this file when the mental model changes.

## Level A — Recognition

### Q1. What major subsystems make up ANVAYA?
**A:** Next.js frontend, FastAPI backend, SQLModel database, agentic execution layer, ML/detection engines, external provider adapters, CLI.
**Source:** `01_SYSTEM_OVERVIEW.md`, `02_ARCHITECTURE.md`

### Q2. What is the unified incident lifecycle?
**A:** The canonical full lifecycle is `detected → analyzed → simulated → explained → sealed`. Dataset-derived incidents from `ArtifactGenerator` land at `active` (`detected → active`), and `active → analyzed` allows an active incident to be investigated and sealed.
**Source:** `backend/anvaya/models/incident.py` `LIFECYCLE_TRANSITIONS`

### Q3. What are the 11 `ARTIFACT_TYPES`?
**A:** `incidents, arbor, impacts, reach, replay, ecosystem, arena, orbits, segments, trophy_wall, ledger`
**Source:** `backend/anvaya/models/project.py`

## Level B — Explanation

### Q4. Why does `score_and_maybe_flag` call `on_incident_event`?
**A:** To dispatch downstream integrations (Tavily, n8n, Signal, Gmail) through a single auditable point when a live detection occurs.
**Source:** `backend/anvaya/live/__init__.py:157`

### Q5. Why does `LocalToolExecutor` exist?
**A:** It wraps all real ANVAYA business logic (Sentinel, BlastScope, What-If, artifact generation, external adapters) behind a common `ToolResult` interface so the agent loop can call them uniformly.
**Source:** `backend/anvaya/agent/executor.py`

### Q6. Why is the audit record hash-chained?
**A:** To make tampering detectable: each record's `record_hash` depends on the previous record's hash, so altering one record breaks the chain.
**Source:** `backend/anvaya/models/audit.py:41-69`

## Level C — Trace

### Q7. How does a `POST /telemetry` become an incident?
**A:** `routers/telemetry.py` creates `TelemetryEvent` → `score_and_maybe_flag` in `live/__init__.py` loads `AlertnessEngine` → `predict_single` → if detected `_get_or_create_incident_for_event` → `_append_detection_audit` → `on_incident_event(DETECTED)`.
**Source:** `05_DATA_FLOWS.md` flow #1

### Q8. How does a user objective reach a tool execution?
**A:** Frontend `AnvayaAPI.agentExecute` → `POST /agent/execute` → `AgentOrchestrator.start` → `run` → `AgentLoop.run_investigation` → `_execute_tool_step` → `LocalToolExecutor.execute` → `handle_<tool>`.
**Source:** `05_DATA_FLOWS.md` flow #2

### Q9. How are live agent events rendered in the UI?
**A:** `EventStore.emit` persists `ExecutionEvent` → SSE `/agent/executions/{id}/stream` or poll `/events` → `lib/api.ts` `connectExecutionSSE` / `useAgentEvents` → `AgentProvider` reducer → `AgentConsole`/`BuildPanel`.
**Source:** `frontend/lib/api.ts`, `frontend/components/agent/agent-context.tsx`

## Level D — Prediction

### Q10. What happens if `TAVILY_API_KEY` is not set?
**A:** `TavilyAdapter.search` returns `{source: "anvaya-local-fixture", fallback_used: True, fallback_reason: "Tavily not configured"}` with a curated record.
**Source:** `backend/anvaya/agent/adapters.py:119-138`

### Q11. What happens if `manage_artifacts` fails on a step with `stop_on_failure=True`?
**A:** The agent loop calls `_fail_execution` and stops the entire execution.
**Source:** `backend/anvaya/agent/agent_loop.py:257-267`

### Q12. What happens if a replay still misses?
**A:** Incident `self_correction_status` becomes `STILL_MISSED` and can return to `BACKTRACKING` for another cycle.
**Source:** `backend/anvaya/sentinel/__init__.py:353-368`

## Level E — Modification

### Q13. What files would need to change to add a new external integration?
**A:**
- `backend/anvaya/agent/adapters.py` — new adapter
- `backend/anvaya/config.py` — settings + `is_*_enabled()`
- `backend/anvaya/agent/registry.py` — tool definition
- `backend/anvaya/agent/executor.py` — handler
- `backend/anvaya/live/dispatch.py` — dispatch step
- `.env.example` — env var
- `tests/` — test both configured and fallback paths
**Source:** `.devin/rules/rules.md` Rule 2

### Q14. What changes to add a new frontend tile?
**A:**
- Add page or update existing workspace page in `frontend/app/`
- Add tile component in `frontend/components/tiles/`
- Add API hook in `frontend/lib/api.ts` if needed
- Add route in `frontend/lib/routes.ts` if new artifact type

## Level F — Security

### Q15. Where could an attacker try to cross a trust boundary?
**A:**
- Malformed `POST /telemetry` to create fake incidents.
- Prompt injection through agent objective.
- Supplying fake `execution_id` to SSE endpoint.
- Attempting to access `/shell` via API (not exposed via API).
- Tampering with `AuditRecord` in DB.
**Source:** `14_SECURITY_MODEL.md`

### Q16. How does the system prevent arbitrary code execution by the agent?
**A:** Tool allowlist, `handle_<tool>` methods, no `exec`/`eval`, strict input schema validation.
**Source:** `backend/anvaya/agent/executor.py`, `backend/anvaya/agent/registry.py`

## Level G — Architecture

### Q17. Why is live dispatch in one function (`on_incident_event`) instead of scattered hooks?
**A:** To avoid N slightly different trigger implementations and provide one auditable place showing what fires on which event type.
**Source:** `backend/anvaya/live/dispatch.py` docstring

### Q18. Why is `ArtifactBuilder` single-target?
**A:** Multi-target orchestration belongs in `AgentLoop` one layer up; `ArtifactBuilder` emits one artifact type's full event stream.

### Q19. Why do `ArtifactGenerator`-derived incidents land at `active` and store `event_count`?
**A:** They are dataset-derived, currently-open threats, not incidents that have gone through full sentinel/blastscope/whatif sealing. `active` matches the Incidents tile `ACTIVE` filter tab. `event_count` is persisted so the live `/incidents` feed can render the events column.
**Source:** `backend/anvaya/models/enums.py`, `backend/anvaya/models/incident.py`, `backend/anvaya/generation.py::_persist_incidents()`
**Source:** `.devin/rules/agents.md`

### Q20. How does the agent console orb reflect the current mode, model, and incident?
**A:** The header orb (`AgentOrbButton` in `frontend/components/agent/agent-console.tsx`) is a small `SiriOrb` whose `colors` prop is computed from state. `c2` (bloom) is the mode color (`chat` = blue, `agentic` = orange), `c3` is the incident severity color (`high` = red, `medium` = amber, `low` = green), and `c4` is the model availability color (`available` = sky, `configured` = amber, `unavailable` = gray). Toggling ask mode, selecting a model, or selecting an incident triggers a 650ms `listening` `AIState` pulse. While an execution runs it shows `thinking`, then `done` or `error`. The top-bar `AgentConsoleTrigger` uses the same `SiriOrb` palette and `AIState` mapping and adds an `AI` label to the right of the orb.
**Source:** `frontend/components/agent/agent-console.tsx:49`, `frontend/components/agent/agent-console.tsx:1039`, `frontend/components/agent/agent-console.tsx:1083`, `frontend/components/smoothui/ai-core/index.tsx`

### Q21. Why were incident risk scores locked to 0.47 and 0.62, and how was it fixed?
**A:** The risk formula itself is fine, but its two inputs were degenerate: (1) incidents were grouped by exact `source_ip + destination_ip + attack_family`, and real telemetry uses random IP pairs, so almost every group had `event_count = 1` and `event_factor = 0.05`; (2) the `is_attack` gate only admitted `high`/`critical` events, so `severity_factor` could only be `0.75` or `1.0`. The fix groups by `(host, user, attack_family)` (with source/destination fallback) and removes the severity gate, allowing all four severities and multi-event groups, which spreads risk scores across the full range.
**Source:** `backend/anvaya/world.py::build_world_model()`

### Q23. Why were Risk Orbits scores locked to ~0.10/0.11, and how was it fixed?
**A:** Orbits were grouped by exact `(source_ip, destination_ip)`; with random IPs each pair occurred once, so `total = 1`, `strength = 1/N * 20` produced ~0.10, and the incident multiplier gave only 0.10/0.11. The fix: (1) bucket IPv4 pairs by /24 prefix with a same-subnet exact fallback, so realistically clustered traffic collapses; (2) derive the scaling constant from the data so the 95th-percentile `total` maps to strength ~0.9; (3) clamp `risk_score` to 1.0; (4) compute node `risk` in `risk-orbits-tile.tsx` from actual orbit event totals instead of `impact_score`; (5) render radial leader-line labels and a `+N` cluster marker for zero-event nodes to avoid center overlap.
**Source:** `backend/anvaya/world.py::_ip_bucket()`, `_pair_bucket()`, `build_world_model()`; `frontend/components/tiles/risk-orbits-tile.tsx`; `frontend/components/orbit-network.tsx`

### Q24. How does the agent console handle a delete/overwrite artifact command?
**A:** It matches an action word (`delete`, `overwrite`, `regenerate`, etc.) plus an artifact-type word. It then extracts all artifact-type matches from the message with a dedicated global regex used by `matchAll`, so it can show the user a `PendingActionGate` (`AIDiff` + `AIApproval`) listing the exact targets and asking for explicit approval before proceeding.
**Source:** `frontend/components/agent/agent-console.tsx:218-241`, `frontend/components/agent/agent-console.tsx:435-439`

### Q25. What lives in the top-bar right side and how do you sign out?
**A:** The top bar left shows the page title. The right side renders, in order: the page-level `right` slot (e.g. `ResetLayoutButton`), then `UserDropdown` (`components/top-bar.tsx:19`), then `AgentConsoleTrigger` (`components/top-bar.tsx:125`). `UserDropdown` shows the user's name and opens a small panel with the user name at the top, an organization link formatted as `<org name> / <email>`, and a `Sign out` item. The previous email label, sign-out icon, and three-dots page menu have been removed.
**Source:** `frontend/components/top-bar.tsx:108`, `frontend/components/top-bar.tsx:19`, `frontend/components/top-bar.tsx:125`

## Level H — Reconstruction

### Q21. Without looking, describe the live detection flow.
**A:** (Reconstruct from memory; check against `05_DATA_FLOWS.md` flow #1.)

### Q22. Without looking, describe the provider fallback algorithm.
**A:** (Reconstruct from memory; check against `PROVIDER_FALLBACKS.md` and `backend/anvaya/agent/adapters.py`.) Steps: check configured → check healthy → if healthy call real API → on any failure return `fallback_used: True` with `anvaya-local-*` source and `fallback_reason`.

### Q26. What is the difference between `anvaya demo` and `anvaya demo-batch`?
**A:** `anvaya demo` runs a single self-correction incident (`DemoOrchestrator.run_full_demo`) and narrates every step with Rich as it completes via a live `on_step` callback. `anvaya demo-batch` runs `DemoOrchestrator.run_batch_demo`: it trains the models once, then produces the requested number of incidents by varying actor, host, seed, and timestamp across the four `ATK-*` templates. The first `N` incidents (default 2) are narrated in full detail; the rest are compact one-line summaries, ending with a batch table.
**Source:** `backend/anvaya/cli/typer_app.py:68`, `backend/anvaya/cli/typer_app.py:409`, `backend/anvaya/demo/orchestrator.py:511`, `backend/anvaya/demo/orchestrator.py:555`

### Q27. How is Startuped XP signaling connected and constrained?
**A:** Devin CLI loads the shared `startuped-ai` MCP command from `.devin/mcp_config.json`, overlays the Bearer credential from gitignored `.devin/mcp_config.local.json`, and auto-approves only `mcp__startuped-ai__create_signal` through `.devin/config.json`. The `startuped-xp` skill permits one honest signal only after a meaningful, verified unit ships.
**Source:** `.devin/mcp_config.json`, `.devin/mcp_config.local.json`, `.devin/config.json`, `.devin/skills/startuped-xp/SKILL.md`

### Q28. How does Startuped distinguish SDK calls for XP attribution?
**A:** Authenticated SDK/CLI requests must include `X-Startuped-Client` (`sdk-js`, `sdk-python`, or `cli`). The installed JS SDK 1.0.4 did not add it in its default HTTP headers, so the verified call wrapped `fetch` to inject `X-Startuped-Client: sdk-js` before calling `client.auth.validate()` against the canonical host.
**Source:** `frontend/package.json`, installed SDK HTTP implementation, live `POST /api/v1/auth/validate-api-key` verification

### Q29. How does ANVAYA emit Startuped behavioral signals without delaying the UI?
**A:** The frontend queues route, generic interaction, form, auth, and agent-panel state events in memory and schedules a non-blocking batch to `/api/startuped/signals`; backend and CLI events are queued to a daemon worker. The browser never receives the Startuped API key, and signal delivery failures do not affect product behavior.
**Source:** `frontend/lib/startuped.ts`, `frontend/app/api/startuped/signals/route.ts`, `backend/anvaya/startuped_signals.py`

## Spaced repetition schedule

Add each question to your personal SRS (Anki/Obsidian) with the following intervals:
- Again: 10 minutes
- Hard: 1 hour
- Good: 1 day
- Easy: 3 days

Mark cards for the following high-priority concepts:
- `score_and_maybe_flag`
- `on_incident_event`
- `LocalToolExecutor`
- `AgentLoop.run_investigation`
- `SentinelEngine` steps
- `AuditRecord.compute_hash`
- `ToolResult` fallback fields
- `AlertnessEngine` contamination logic
- `WhatIfEngine.analyze`
- `BlastScopeEngine.run` impact score

## Quick self-test (closed book)

Answer these in one minute each:
1. What is the single shared dispatch point for incident events?
2. What does `fallback_used` mean?
3. What ML model powers Alertness?
4. What are the four main Sentinel steps?
5. What is stored in `ProjectArtifactPayload`?
6. What is the CLI command to start real-time log tailing?
7. How is the audit chain verified?
8. What is the default `NEXT_PUBLIC_API_URL`?
9. Which router handles live telemetry?
10. What is the role of `handle_manage_artifacts`?

Check your answers against the source files listed in this bank.
