# ANVAYA — Critical File Deep Dives

> Tier-A line-by-line walkthroughs of the most important modules. Add new deep dives here as understanding improves.

## Tier A — critical files

### `backend/anvaya/live/__init__.py`

**Purpose:** single real-time scoring entry point.

**Key logic:**
- `score_and_maybe_flag(event, session)` at line 112 is the only place live `AlertnessEngine` should be invoked.
- If `event.id is None`, persists the event.
- `engine.load_latest()` fetches the active `ModelVersion` and joblib artifact.
- If `engine.model is None`, returns `scored: False` with reason.
- `predict_single(event)` returns `{detected, score, model_id}`.
- If detected: `_get_or_create_incident_for_event` and `_append_detection_audit`.
- Always calls `on_incident_event(incident, IncidentEventType.DETECTED, session)`.

**Security:** no user input beyond the telemetry fields; no shell execution.

**Failure:** `predict_single` exception caught and returns `scored: False`.

### `backend/anvaya/agent/executor.py`

**Purpose:** executes all agent tools locally.

**Key logic:**
- `LocalToolExecutor.execute(tool_name, inputs, ...)` at line 83.
- `_next_sequence` increments per execution event.
- `handle_<tool>` methods wrap business logic.
- `handle_manage_artifacts` at line 725 creates one `ArtifactBuilder` per artifact type.
- External adapters are called with `fallback_used` truthfully set.

**Security:** only pre-defined handlers can run; no arbitrary code execution.

**Failure:** exception caught and returned as `ToolResult` with `execution_error`.

### `backend/anvaya/models/audit.py`

**Purpose:** hash-chained audit records.

**Key logic:**
- `AuditRecord.compute_hash(prev_hash)` at line 41.
- `verify_chain(records)` at line 99.
- The hash includes the previous record's hash, making the chain tamper-evident.

**Security:** SHA-256 of canonical sorted JSON; no encryption.

**Failure:** `verify_chain` returns `False` on any break.

### `ml/anvaya/alertness/__init__.py`

**Purpose:** Isolation Forest training and scoring.

**Key logic:**
- `train` at line 44 fits scaler + model and computes metrics.
- `contamination` derived from actual attack prevalence (clamped [0.01, 0.5]).
- `predict_single` at line 204 returns `{detected, score, model_id}`.
- `load_latest` reads the most recent `ModelVersion` and loads joblib artifacts.

**Security:** trained on synthetic data; no real attack data needed.

**Failure:** missing model returns `engine.model is None`.

### `backend/anvaya/sentinel/__init__.py`

**Purpose:** self-correction engine.

**Key logic:**
- `backtrack` at line 45
- `propose_rule` at line 101
- `validate_rule` at line 195
- `replay_attack` at line 268
- `run_full_cycle` at line 381

**Security:** operates on persisted `TelemetryEvent` and `Incident`; no network.

**Failure:** `STILL_MISSED` can loop back to `BACKTRACKING`.

### `backend/anvaya/live/dispatch.py`

**Purpose:** single shared dispatch point.

**Key logic:**
- `on_incident_event` at line 232.
- `_tavily_enrich`, `_n8n_notify`, `_signal_api_notify`, `_gmail_notify`.
- `_append_dispatch_audit` writes an `AuditRecord`.
- `on_project_created` at line 279 routes to n8n Launchpad workflow.

**Security:** checks `is_*_enabled()` before any call; no credential leak.

**Failure:** adapters return local fallback; audit still written.

### `backend/anvaya/agent/orchestrator.py`

**Purpose:** start and run agent executions.

**Key logic:**
- `start` creates `Execution` and `ExecutionContext`.
- `run` resolves incident/project, selects planner, runs `AgentLoop`.
- `_run_project_plan` handles artifact objectives.
- `_run_mixed_plan` handles mixed investigation + artifact generation.

**Security:** no direct user-controlled code execution.

**Failure:** `_fail` writes a failure execution record.

### `backend/anvaya/agent/agent_loop.py`

**Purpose:** live, reasoning-aware execution loop.

**Key logic:**
- `run_investigation` at line 88: deterministic multi-step plan.
- `run_project_plan` at line 383 (or `run_project_plan` near line 227): artifact build plan.
- `run_adaptive` at line 353: decision engine driven.
- `_execute_tool_step` at line 847 emits events and runs executor.

**Security:** validates inputs against registry before execution.

**Failure:** step failure may stop execution if `stop_on_failure`.

## Tier B — important blocks

- `backend/anvaya/agent/registry.py` — tool registration and validation.
- `backend/anvaya/agent/events.py` — event store and SSE support.
- `backend/anvaya/blastscope/__init__.py` — NetworkX blast radius.
- `backend/anvaya/whatif/__init__.py` — Logistic Regression counterfactuals.
- `backend/anvaya/generations/builder.py` — staged artifact build.
- `frontend/lib/api.ts` — all API calls and hooks.
- `frontend/components/agent/agent-context.tsx` — agent UI state and SSE.

## Tier C — routine boilerplate

- Standard imports, Pydantic models, SQLModel field definitions, test fixtures, generated `.next/types`.

## Active recall

- What is the only function that should call the live Alertness model?
- How does `LocalToolExecutor` choose which code to run?
- What makes the audit record hash chain tamper-evident?
- What does `SentinelEngine.replay_attack` compare?
- What is the single dispatch point for external integrations?

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/live/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/executor.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/models/audit.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/ml/anvaya/alertness/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/sentinel/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/live/dispatch.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/orchestrator.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/agent_loop.py" />
