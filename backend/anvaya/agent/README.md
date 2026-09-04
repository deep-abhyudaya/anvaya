# anvaya.agent — Agentic Execution Layer

This package provides the provider-neutral tool system, execution event store,
deterministic orchestrator, and operational messaging for ANVAYA's autonomous
SOC demo.

## Modules

| Module | Purpose |
|--------|---------|
| `schemas.py` | `ToolDefinition`, `ToolResult`, `ExecutionEventPayload`, `ExecutionSummary`, `AgentProfile`, `ModelConfig` and other Pydantic schemas. |
| `profiles.py` | Built-in `AgentProfile` and `ModelConfig` definitions with truthful availability. |
| `adapters.py` | `ProviderAdapter` layer with health checks and local fallbacks for OpenAI, Lyzr, Swytchcode, Tavily, n8n, and the local ANVAYA policy. |
| `messaging.py` | `MessageGenerator` emits operational `agent.message` events before/after each tool based on the active profile. |
| `registry.py` | `ToolRegistry` — provider-neutral tool catalog with input validation. `default_tool_registry()` returns the full ANVAYA tool suite. |
| `executor.py` | `LocalToolExecutor` — maps tool calls to existing ANVAYA engines (`Sentinel`, `BlastScope`, `WhatIf`, audit, etc.) with safe output summaries and artifact refs. |
| `orchestrator.py` | `AgentOrchestrator` — deterministic policy that plans and executes the self-correction investigation lifecycle. Falls back to this local policy whenever an external model provider is unavailable. |
| `events.py` | `EventStore` — persists execution traces to `Execution` and `ExecutionEvent` tables and provides ordered event retrieval for polling and SSE. |

## Tool contract

Each tool is a `ToolDefinition` with:
- `name` and `description`
- `category` (investigation, sentinel, simulation, defense, audit, intelligence, automation)
- `parameters` with types and validation rules
- `risk_level` and `requires_confirmation`
- `provider` and `fallback_provider`

Execution produces a stream of `ExecutionEvent` records:
- `agent.started`, `agent.plan_created`
- `agent.message` — operational status messages
- `tool.started`, `tool.progress`, `tool.completed`, `tool.failed`, `tool.fallback`
- `artifact.created`
- `incident.updated`
- `agent.completed`, `agent.failed`

## Profiles and models

Built-in agent profiles:
- `sentinel` — evidence-first SOC investigator
- `pathfinder` — attack-path and impact analyst
- `responder` — response planner
- `auditor` — evidence and compliance reviewer

Built-in models:
- `anvaya-local-orchestrator` — always available deterministic policy
- `openai-gpt-4o-mini` — available when `OPENAI_API_KEY` is set
- `lyzr-orchestrator`, `swytchcode-tool`, `tavily-search`, `n8n-automation` — available when configured

`/api/v1/agent/profiles` and `/api/v1/agent/models` return the full catalog with
availability derived from the current environment.

## Local fallback

No external providers are required. If `OPENAI_API_KEY`, `TAVILY_API_KEY`, or
`N8N_WEBHOOK_URL` are absent, the orchestrator uses local ANVAYA logic and
labels the result `fallback_used: true` with a `fallback_reason`.

## Usage

```python
from anvaya.db import get_session
from anvaya.agent import AgentOrchestrator

with next(get_session()) as session:
    orch = AgentOrchestrator(session)
    execution_id = orch.start("Investigate missed incident INC-001", incident_id="INC-001")
    execution = orch.run(execution_id)
    print(execution.status)
```

## API endpoints

- `GET /api/v1/agent/profiles` — list agent profiles
- `GET /api/v1/agent/models` — list model metadata and availability
- `GET /api/v1/agent/tools` — list all tools
- `POST /api/v1/agent/tools/{tool}/validate` — validate tool inputs
- `POST /api/v1/agent/execute` — start an execution
- `POST /api/v1/agent/seed` — create a demo incident for the agent
- `POST /api/v1/agent/init-demo` — create a self-correction demo incident
- `GET /api/v1/agent/executions` — list executions
- `GET /api/v1/agent/executions/{execution_id}` — get execution summary
- `GET /api/v1/agent/executions/{execution_id}/events` — poll execution trace
- `GET /api/v1/agent/executions/{execution_id}/stream` — Server-Sent Events stream
