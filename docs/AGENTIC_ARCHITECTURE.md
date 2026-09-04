# ANVAYA — Agentic Architecture

## Overview

ANVAYA's agentic layer is a persistent, right-side console integrated into the existing application shell. It exposes a provider-neutral tool system, a deterministic local orchestrator, optional model-driven planning, and a streamed execution trace.

The design principle is: **real tool calls, real results, truthful fallback attribution, no hidden chain-of-thought**.

For incident objectives, `AgentOrchestrator` now runs an adaptive `observe → decide → act` loop by default. The loop is goal-driven: it observes the environment, maintains hypotheses on a Blackboard, selects the next best tool, consumes observations, verifies evidence, and persists findings.

## Components

```
┌──────────────────────────────────────────────────────────────────────────┐
│  User objective                                                           │
│       ↓                                                                   │
│  AgentOrchestrator                                                        │
│       ↓                                                                   │
│  resolve_planner() → DeterministicPlanner | ModelPlanner                  │
│       ↓                                                                   │
│  AgentLoop                                                                │
│       ↓                                                                   │
│  Mission / Blackboard / Hypotheses / World / Memory / Verification        │
│       ↓                                                                   │
│  DecisionEngine → next best tool or completion                            │
│       ↓                                                                   │
│  ExecutionContext (live plan, observations, messages, findings)           │
│       ↓                                                                   │
│  ToolRegistry → LocalToolExecutor (+ optional external adapters)          │
│       ↓                                                                   │
│  spawn_subagent → SubagentSpawner / SubagentExecution                     │
│       ↓                                                                   │
│  ToolResult → EventStore                                                  │
│       ↓                                                                   │
│  /agent/executions/{id}/events (polling) or /stream (SSE)                 │
│       ↓                                                                   │
│  AgentConsole (right-side panel)                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Event contract

All execution events are persisted and emitted as `ExecutionEventPayload`:

- `agent.started`
- `agent.plan_created`
- `agent.message`
- `agent.reasoning_started`
- `agent.reasoning_delta`
- `agent.reasoning_completed`
- `agent.decision_started`
- `agent.tool_requested`
- `agent.observation_created`
- `agent.plan_updated`
- `agent.execution_interrupted`
- `tool.started`
- `tool.progress`
- `tool.completed`
- `tool.failed`
- `tool.fallback`
- `artifact.created`
- `incident.updated`
- `subagent.spawned`
- `subagent.started`
- `subagent.completed`
- `subagent.failed`
- `subagent.cancelled`
- `agent.completed`
- `agent.failed`
- `agent.decision`
- `agent.observation`
- `agent.verification_passed`
- `agent.verification_failed`

Events carry only observable, safe metadata: tool name, input summary, provider, duration, status, artifact refs, and fallback information. Secrets, raw prompts, and stack traces are never sent to the frontend.

## Tool execution

The `ToolRegistry` defines the available tools. The `LocalToolExecutor` maps each tool to real ANVAYA business logic:

- `get_incident`, `get_telemetry`, `inspect_detection` → database models
- `observe_environment`, `observe_project` → environment/world state snapshot
- `detect_anomalies`, `rank_candidates` → anomaly ranking from telemetry
- `search_events`, `search_entities` → telemetry and graph search
- `correlate_entities`, `investigate_entity`, `trace_attack_path`, `reconstruct_timeline` → hypothesis-driven investigation
- `compare_baseline`, `calculate_blast_radius`, `test_hypothesis` → evidence evaluation
- `verify_conclusion`, `create_finding` → verification and audit
- `run_sentinel_trace`, `propose_rule`, `validate_rule`, `run_replay` → `SentinelEngine`
- `run_blastscope`, `run_reachability`, `run_segment_analysis` → `BlastScopeEngine` and graph routers
- `run_what_if` → `WhatIfEngine`
- `append_audit_record`, `verify_audit_chain`, `seal_incident` → `ControlLedger`
- `spawn_subagent` → `SubagentSpawner` (foreground/background child execution)
- `run_tests` → local `pytest` invocation
- `threat_intelligence_lookup` → `TavilyAdapter` (or local fixture)
- `trigger_automation` → `N8NAdapter` (or local handler)

## Model providers

`ModelProvider` is an abstraction over NVIDIA NIM, OpenAI, Lyzr, and a deterministic local fallback. Each provider normalizes responses to `NormalizedModelResponse` with `text`, `tool_calls`, `finish_reason`, `usage`, `provider`, and `model`.

The orchestrator selects a planner:

1. If the requested/selectable model is capable and configured, `ModelPlanner` asks it to generate the next plan.
2. Otherwise, `DeterministicPlanner` uses the existing policy plan.

Capability gating rejects a model if the active profile requires a feature the model does not advertise (tool use, streaming, structured output, etc.).

## Profiles

Four built-in profiles share the same tool registry but differ in wording, tool preference, and confirmation policy:

- **Sentinel** — incident investigation
- **Pathfinder** — attack path / impact analysis
- **Responder** — response planning
- **Auditor** — evidence and audit verification

See `docs/AGENT_PROFILES.md` for details.

## Subagents

ANVAYA supports Devin-like subagents via `SubagentSpawner`:

- **Profiles** — built-in `explore`, `general`, `tester` profiles with their own allowed/preferred/fallback tools, confirmation policies, and nesting limits.
- **Modes** — `foreground` blocks the parent until the subagent completes; `background` runs in a separate thread and emits parent events.
- **Nesting** — a subagent may itself spawn subagents up to the profile's `max_nesting`; attempts beyond that are rejected.
- **Lifecycle** — `pending → running → completed | failed | cancelled`; `resume` creates a new subagent clone with the same task.
- **Persistence** — `SubagentExecution` rows track `parent_execution_id`, `child_execution_id`, status, duration, result summary, and tool calls.
- **Frontend** — the Agent Console has a `subagents` tab to spawn, filter, cancel/resume, and open child executions.

## Transport

The primary transport is React Query polling against `/agent/executions/{id}/events`. An SSE stream is available at `/agent/executions/{id}/stream?after={sequence}`. Both use the same event contract. The stream accepts an `after` query parameter so clients can reconnect and resume from the last seen sequence.

## Live execution context

`ExecutionContext` is a new `SQLModel` table that stores the live, mutable state of an in-flight execution. It is keyed by `execution_id` and kept separate from the immutable `Execution` and `ExecutionEvent` tables so existing schemas are unchanged.

It holds:

- `objective`, `incident_id`, `project_id`
- `plan` — the current plan with per-step status, results, and artifact counts
- `observations` — user-safe facts extracted from each tool result
- `messages` — unprocessed user follow-up messages
- `reasoning_summary` — the latest user-safe reasoning sentence
- `current_action` — the step currently being executed
- `status`, `model`, `provider`, timestamps
- `mission` — goal, budget, and stop criteria for the run
- `blackboard` — working memory with hypotheses, evidence, and candidate focus
- `hypotheses` — ranked hypotheses with confidence and next test
- `memory` — recalled prior executions and related context
- `findings` — verified conclusions persisted as audit records
- `verification` — last verification result

`AgentLoop` reads and updates this context at every step boundary and refreshes it before and after tool calls. The `ExecutionContext` is the source of truth for the reasoning panel.

## Reasoning

`ReasoningGenerator` produces user-safe reasoning summaries from the current `ExecutionContext`. The default path is deterministic and grounded in actual tool outputs and plan state. If a configured external model supports streaming, it can optionally stream `agent.reasoning_delta` events, but the final summary always falls back to deterministic output and is sanitized to remove hidden chain-of-thought markers.

## User interaction

A running execution can be influenced through the agent execution API:

- `POST /agent/executions/{id}/message` — append a user message. The loop processes it at the next checkpoint. Messages starting with `only`, `skip`, or naming artifact types update the live plan; messages containing `cancel`, `stop`, `abort`, or `quit` cancel the run.
- `POST /agent/executions/{id}/cancel` — immediately mark the context and execution as `cancelled` and emit `agent.execution_interrupted`.
- `GET /agent/executions/{id}/context` — return the full live context for the reasoning panel.

`AgentLoop` is implemented in `backend/anvaya/agent/agent_loop.py` and is responsible for maintaining the context, emitting the new reasoning/decision/observation events, and reacting to user messages.

## Safety

- Tools are allowlisted in the registry.
- Risk levels and `requires_confirmation` control mutating actions.
- No arbitrary code execution is allowed.
- All attack scenarios remain synthetic and deterministic.
