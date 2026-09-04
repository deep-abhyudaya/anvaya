# ANVAYA — Agentic Layer Repository Audit

## 1. What is already implemented

### Backend (`backend/anvaya/agent/`)

| Module | Status | Notes |
|--------|--------|-------|
| `schemas.py` | Implemented | `ToolDefinition`, `ToolResult`, `ExecutionEventPayload`, `ExecutionSummary`, `AgentProfile`, `ModelConfig`. |
| `registry.py` | Implemented | Provider-neutral tool registry with input validation. 19 ANVAYA tools registered. |
| `executor.py` | Implemented | `LocalToolExecutor` wraps real engines: `SentinelEngine`, `BlastScopeEngine`, `WhatIfEngine`, audit, graph, metrics. |
| `orchestrator.py` | Implemented | Deterministic policy orchestrator that builds and runs the full self-correction plan. |
| `events.py` | Implemented | `EventStore` persists to `Execution` / `ExecutionEvent` tables; supports polling and SSE. |
| `profiles.py` | Implemented | 4 built-in profiles (Sentinel, Pathfinder, Responder, Auditor) and a static `ModelConfig` list. |
| `messaging.py` | Implemented | `MessageGenerator` emits short, observable `agent.message` events per profile. |
| `adapters.py` | Partial | `ProviderAdapter` base, plus stubs for OpenAI, Lyzr, Swytchcode, Tavily, n8n, and local ANVAYA. **NVIDIA NIM is missing.** |
| `routers/agent.py` | Implemented | Full REST API: `/agent/execute`, `/agent/profiles`, `/agent/models`, `/agent/tools`, `/agent/executions/{id}/events`, `/agent/executions/{id}/stream`, `/agent/seed`. |

### Frontend (`frontend/components/agent/`)

| Component | Status | Notes |
|-----------|--------|-------|
| `agent-context.tsx` | Implemented | Global `AgentProvider`, profile/model loading, incident context extraction, event polling at 1s, execution history. |
| `agent-console.tsx` | Implemented | Right-side collapsible panel, resize, profile/model/incident selectors, conversation tabs, tool/artifact/message cards, auto-scroll. |
| `AppShell` integration | Implemented | `AgentConsoleTrigger` is in `TopBar`; `AgentConsole` is a persistent `aside` in `AppShell`. |
| `api.ts` | Implemented | `AnvayaAPI` client methods for all agent endpoints; React Query hooks. |

### Tests

- `tests/test_agent.py` (10 tests) — **passing**.
- Full suite `tests/` — 65 tests **passing**.

## 2. What is missing for the NVIDIA + external-provider generation

### Backend

1. **NVIDIA NIM provider adapter**
   - `NVIDIAProvider` class behind a `ModelProvider` abstraction.
   - OpenAI-compatible request/response normalization (`NormalizedModelResponse`).
   - Capability metadata: tools, streaming, reasoning, multimodal, structured output.
   - Config: `NVIDIA_API_KEY`, `NVIDIA_MODEL`, `NVIDIA_BASE_URL`, `NVIDIA_TIMEOUT_MS`, `NVIDIA_MAX_RETRIES`.
   - Model registry entries for NVIDIA models.

2. **Model provider abstraction**
   - `ModelProvider` protocol with `NVIDIAProvider`, `OpenAIProvider`, `LyzrProvider`, `LocalProvider`.
   - Capability gating before assignment to a profile.
   - Fallback matrix: Lyzr -> NVIDIA -> OpenAI -> local deterministic.

3. **Model-driven planning loop**
   - Optional model call inside `AgentOrchestrator` to select the next tool.
   - Tool-call parsing and validation.
   - Bounded loop with max steps, timeouts, cancellation, duplicate-call guard, context limit.
   - Falls back to deterministic policy when no model is available or capable.

4. **External tool-provider execution**
   - Swytchcode executor interface (currently hardcoded as unavailable).
   - Tavily live search (currently returns a fixture).
   - n8n webhook trigger (currently records a no-op).
   - Lyzr adapter stub.
   - All must truthfully label `provider_used`, `fallback_used`, `fallback_reason`.

5. **Provider status API expansion**
   - `/agent/providers` exists but does not include NVIDIA or detailed capability metadata.

### Frontend

1. **Provider status panel**
   - Show NVIDIA, Swytchcode, Tavily, Lyzr, n8n status with truthful availability.

2. **Model selector metadata**
   - Expanded model popover with capabilities, context window, provider, and status.

3. **Tool-card expand/collapse**
   - Prompt asks for expandable tool cards with full input/output summaries.

### Documentation

- `docs/AGENTIC_ARCHITECTURE.md`
- `docs/AGENT_PROFILES.md`
- `docs/MODEL_PROVIDERS.md`
- `docs/TOOL_REGISTRY.md`
- `docs/AGENT_FALLBACKS.md`

## 3. Mapping of required tools to real repository functions

| Capability | Tool name | Backend handler / route |
|------------|-----------|--------------------------|
| `get_incident` | `get_incident` | `LocalToolExecutor.handle_get_incident` → `Incident` model |
| `get_telemetry` | `get_telemetry` | `LocalToolExecutor.handle_get_telemetry` → `TelemetryEvent` |
| `inspect_detection` | `inspect_detection` | `LocalToolExecutor.handle_inspect_detection` → `DetectionRun` |
| `run_sentinel_trace` | `run_sentinel_trace` | `SentinelEngine.backtrack` |
| `confirm_ground_truth` | `confirm_ground_truth` | `LocalToolExecutor.handle_confirm_ground_truth` |
| `propose_rule` | `propose_rule` | `SentinelEngine.propose_rule` |
| `validate_rule` | `validate_rule` | `SentinelEngine.validate_rule` |
| `create_replay` / `run_replay` | `run_replay` | `SentinelEngine.replay_attack` |
| `get_replay_result` | embedded in `run_replay` | replay result payload |
| `run_blastscope` | `run_blastscope` | `BlastScopeEngine.run` |
| `update_ecosystem` / `build_or_update_ecosystem` | `build_or_update_ecosystem` | `BlastScopeEngine.run` + `get_ecosystem` |
| `run_orbit_analysis` | `run_orbit_analysis` | derived from `BlastRadiusResult` + incident state |
| `run_reachability` | `run_reachability` | `get_reachability` router + `BlastRadiusResult` |
| `run_segment_analysis` | `run_segment_analysis` | `get_segments` router |
| `run_what_if` | `run_what_if` | `WhatIfEngine.analyze` |
| `get_metrics` | `get_metrics` | `get_metrics` router |
| `append_audit_record` | `append_audit_record` | `AuditRecord` + chain hash |
| `verify_audit_chain` | `verify_audit_chain` | `verify_chain` helper / router |
| `seal_incident` | `seal_incident` | incident state machine + audit record |

Note: the tool registry currently uses `run_replay` (create + run) and `build_or_update_ecosystem` rather than separate `create_replay`/`update_ecosystem`. This satisfies the demo flow because the handler creates and runs the replay in one call.

## 4. Risk / compatibility notes

- The deterministic local orchestrator must remain the final fallback and the default when no external provider is configured.
- Any NVIDIA/OpenAI/Lyzr integration must not bypass the existing `ToolRegistry` and `LocalToolExecutor`.
- Tool results must continue to carry `provider`, `fallback_used`, and `fallback_reason`.
- Existing UI is already right-side and persistent; the frontend work is additive.
- All 65 existing tests must continue to pass.
