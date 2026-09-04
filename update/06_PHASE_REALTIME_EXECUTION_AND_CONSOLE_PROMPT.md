# PHASE 5 — REALTIME EXECUTION, STREAMING, AND AGENT CONSOLE INTEGRATION

Turn the existing Agent Console into a truthful live observer of the agent loop.

Do not make a new UI shell.
Do not add fake delays.
Do not simulate “thinking.”

## Current architecture to preserve

Backend:
- `EventStore`
- `ExecutionEvent`
- `/agent/executions/{id}/events`
- `/agent/executions/{id}/stream`

Frontend:
- `components/agent/agent-context.tsx`
- `components/agent/agent-console.tsx`
- `lib/api.ts`

## Critical current gap

The current `/agent/execute` path invokes the orchestrator synchronously and the frontend uses 1-second polling for execution events.

Fix this so long-running agent objectives return an execution ID and continue in the existing server execution/event path, while retaining polling as fallback.

## Event types

Use the existing event model and extend minimally with safe operational events such as:

- agent.observation
- agent.decision
- agent.replan
- agent.hypothesis_created
- agent.hypothesis_updated
- agent.verification_started
- agent.verification_passed
- agent.verification_failed
- agent.memory_recalled
- execution.iteration_started
- execution.iteration_completed
- agent.awaiting_input
- agent.cancel_requested
- agent.cancelled

## Safe “reasoning” display

Do NOT expose private chain-of-thought.

Show only:

- concise decision summary
- operational purpose
- tool selection reason summary
- observation summary
- plan change summary
- verification outcome

Example:

`The network anomaly is stronger than the authentication anomaly, so I’m tracing graph relationships before ranking candidates.`

This is a user-safe summary, not hidden reasoning.

## Live execution view

Extend existing event cards to show:

- objective
- iteration
- current action
- current hypothesis
- tool
- progress
- observations
- plan updates
- verification
- subagents
- final outcome

## SSE

The backend must persist events before/around emitting them, and the frontend must be able to:

- connect
- receive live events
- deduplicate by execution ID + sequence
- reconnect
- request missed events
- resume without losing the execution

## Chat vs agentic

Do not mix plain chat streaming with agent execution events.

Chat may stream tokens.
Agentic mode streams execution state and safe model decision summaries.

## User interaction while active

Use the existing composer to support:

- status query
- cancellation
- scope change
- dataset change
- skip optional step
- continue mission

Follow-up messages should target the active execution when clearly intended.

## Acceptance test

Run a multi-step mission and observe the console without refreshing.

The console must show, in chronological order:

1. agent started
2. observation
3. decision
4. tool started
5. tool result
6. new observation
7. changed/next decision
8. verification
9. completion

No artificial sleeps.
