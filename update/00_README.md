# ANVAYA — Staff-Level Agentic Integration Prompt Pack

This pack is written against the uploaded ANVAYA backend/frontend source tree and is intended for Devin.

## Current codebase anchors

- `backend/backend/anvaya/agent/orchestrator.py` — current deterministic plan-and-run orchestrator.
- `backend/backend/anvaya/agent/planner.py` — model-backed planner + deterministic fallback; currently produces a whole plan rather than an adaptive loop.
- `backend/backend/anvaya/agent/registry.py` — existing provider-neutral ToolRegistry.
- `backend/backend/anvaya/agent/executor.py` — existing LocalToolExecutor wrapping Sentinel, BlastScope, What-If, replay, graph, artifacts, n8n/Tavily adapters and test execution.
- `backend/backend/anvaya/agent/events.py` — persistent Execution/EventStore with polling/SSE support.
- `backend/backend/anvaya/agent/subagents.py` — existing parent/child subagent lifecycle with foreground/background execution.
- `backend/backend/anvaya/agent/chat.py` — existing model chat + streaming path.
- `backend/backend/anvaya/agent/messaging.py` — operational agent messages.
- `backend/backend/anvaya/models/execution.py` — persistent execution/event records.
- `backend/backend/anvaya/models/project.py` — projects, datasets, generations, project artifacts; 11 current artifact types.
- `backend/backend/anvaya/generation.py` — dataset-grounded `ArtifactGenerator` and project artifact persistence.
- `backend/backend/anvaya/routers/agent.py` — agent execution, chat, stream, tools, executions, subagents.
- `backend/backend/anvaya/routers/projects.py` — project/dataset/generation/artifact APIs.
- `frontend/components/agent/agent-context.tsx` — client execution state, 1s event polling, project context.
- `frontend/components/agent/agent-console.tsx` — persistent agent console UI, profiles/models, event cards, subagent tab, composer.
- `frontend/lib/api.ts` — agent execution/event/subagent/artifact client contracts.

## Important current limitation the prompts address

The current system is agentic in presentation and tool execution, but the core orchestration path still behaves primarily as:

`objective → resolve context → build one plan → execute fixed steps → complete`

and project-oriented requests can route into artifact generation.

The goal of this pack is to integrate a genuine observe → plan → act → observe → adapt → verify → remember loop using the existing orchestration, tool registry, executor, event store, subagent system, project/dataset/artifact state, and existing frontend console.

## Non-goal

Do NOT build a parallel agent framework, parallel world model, duplicate ToolRegistry, duplicate event bus, duplicate execution store, or duplicate dashboard state. Extend/refactor the existing paths.

## Recommended usage

1. Give Devin `01_MASTER_IMPLEMENTATION_PROMPT.md` as the governing prompt.
2. Then run the phase prompts one at a time in order if Devin starts taking shortcuts.
3. Use `08_ADVERSARIAL_ACCEPTANCE_PROMPT.md` at the end as a hard gate.
4. Keep `09_CURRENT_CODEBASE_INTEGRATION_MAP.md` in the repo context when prompting Devin.

