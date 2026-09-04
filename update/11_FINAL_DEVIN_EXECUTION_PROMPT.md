# FINAL COPY/PASTE PROMPT FOR DEVIN

You are the senior/staff engineer taking the existing ANVAYA repository from “agentic-looking artifact generator” to a genuinely autonomous investigation system.

I am explicitly NOT asking you to create a new codebase, prototype, parallel agent engine, or redesign the application.

I want you to integrate the following behavior into the existing architecture already present in this repository.

## The one-line mission

> Make ANVAYA capable of receiving a meaningful security objective and autonomously accomplishing it by repeatedly observing the existing project/data environment, deciding the next best tool action, executing real existing capabilities, learning from results, changing its plan when evidence changes, verifying conclusions, remembering useful prior state, delegating to existing subagents where useful, and persisting/streaming the entire execution — while treating Orbit/Ecosystem/Replay/Reach/etc. as instruments rather than the objective.

## Non-negotiable rule

If the dashboard were deleted, the backend agent must still be able to accomplish a meaningful objective.

If the backend simply generates orbit/ecosystem/replay/trophy artifacts in a fixed sequence, this is NOT done.

## Current architecture to integrate with

Use the existing:

- `AgentOrchestrator`
- `ModelPlanner`
- deterministic planner fallback
- `ToolRegistry`
- `LocalToolExecutor`
- `EventStore`
- `Execution` / `ExecutionEvent`
- `SubagentSpawner`
- project/dataset/generation/artifact models
- dataset-grounded `ArtifactGenerator`
- SentinelBacktracker
- BlastScope
- What-If
- replay
- graph/telemetry/detection/audit services
- agent router
- existing SSE endpoint
- existing Agent Console and React Query/API contracts

Do not create competing versions.

## Required execution model

The execution must become:

`GOAL`
`→ OBSERVE`
`→ DECIDE`
`→ ACT`
`→ OBSERVE RESULT`
`→ UPDATE STATE`
`→ REPLAN`
`→ VERIFY`
`→ COMPLETE / CONTINUE`

Not:

`GOAL → ONE PLAN → EXECUTE EVERYTHING → DONE`

## Required capabilities

### Environment observation

Agent must know, through existing backend records:

- current project
- authoritative dataset
- dataset checksum/profile
- current generation/artifacts
- incidents
- telemetry summary
- graph state
- previous executions/investigations
- unresolved tasks/findings

### Goal/mission state

Represent:

- objective
- success condition
- failure condition
- iteration count
- tool-call budget
- time budget
- current state
- unresolved questions

Use existing `Execution` as the canonical runtime identity.

### Adaptive planning

The model or deterministic fallback chooses a NEXT action based on the latest observation.

The plan is mutable.

Example:

```text
Objective: find most important threat

Observation:
DNS anomaly dominates

Decision:
Investigate DNS relationships

Tool result:
activity maps to known scanner

Reassessment:
Candidate downgraded

New decision:
Investigate privileged authentication anomaly
```

### Tool-first behavior

Agent capabilities should focus on:

- observation
- anomaly detection
- correlation
- path tracing
- timeline reconstruction
- blast-radius analysis
- baseline comparison
- hypothesis testing
- verification
- case/finding/recommendation operations

Reuse existing engines.

### Hypothesis state

Each serious conclusion should have:

- statement
- assessment/confidence
- evidence for
- evidence against
- unknowns
- next test
- status

Allow hypotheses to be rejected and replaced.

### Blackboard

Maintain compact execution-local state containing:

- goal
- facts
- current candidate
- hypotheses
- evidence refs
- contradictions
- open questions
- next best action
- tool results

Do not duplicate the whole database.

### Memory

Reuse prior executions/domain records.

The second investigation of an entity should be able to recall relevant prior facts and choose a targeted action because of them.

### Verification

No unsupported conclusion.

Verify:

- evidence exists
- references resolve
- timestamps make sense
- relationship exists
- provenance is correct
- required tools actually succeeded

If not verified, keep investigating or report insufficient evidence.

### Recovery

Tool failure should trigger:

- retry where safe
- alternate capability where possible
- replan
- explicit failure

Never fake completion.

### Subagents

Reuse existing `SubagentSpawner`.

Use real delegation for decomposable tasks such as:

- timeline analysis
- network analysis
- identity correlation

Parent synthesizes structured child outputs.

### Realtime execution

Fix the current synchronous execution limitation.

Long-running `/agent/execute` work should return an execution ID and continue server-side using the existing execution/event model.

Persist events as they occur.

Stream them through existing SSE.

Polling remains fallback.

No fake sleeps.

### Safe live “reasoning”

Show concise operational summaries such as:

`The network evidence is stronger than the authentication evidence, so I’m tracing graph relationships next.`

Do not expose private chain-of-thought.

### Artifact behavior

Keep all current artifacts.

But the agent must create/use them only when they help answer the objective.

The number of artifacts is NOT the definition of agent success.

### User controls

Support safe interaction with active executions:

- status
- cancel
- continue
- narrow objective
- skip optional step
- change dataset

### Permission policy

Reuse risk/confirmation semantics already present in `ToolDefinition` and agent profiles.

Never allow arbitrary model-supplied mutations across project/org boundaries.

## Implementation discipline

Before editing:

1. inspect the actual repository
2. map the current execution flow
3. identify duplicate/overlapping logic
4. decide the smallest refactor that produces the new behavior
5. document assumptions

During editing:

- reuse existing classes
- preserve API compatibility where possible
- keep modules cohesive
- type new contracts
- add tests before claiming completion
- preserve fallback behavior
- preserve multi-tenant security

After editing:

Run:

- targeted backend tests
- full pytest
- relevant lint/type checks
- frontend build
- targeted frontend/runtime checks

## Absolute anti-patterns

Do not:

- create `AgentOrchestratorV2`
- create another event bus
- create another execution database
- add an unrelated memory store
- create a fake blackboard UI with no backend state
- emit random progress percentages
- add `sleep()` solely to create a streaming illusion
- use canned “thinking…” text
- mass-generate all 11 artifacts for every objective
- expose hidden chain-of-thought
- mark a mission successful because a tool was called
- report findings without evidence

## The acceptance objective

Run:

> “Find the most important security issue in this project. Decide how to investigate it. Do not generate artifacts unless they help answer the question. Continue until you have a high-confidence conclusion or the evidence is insufficient.”

A passing execution must demonstrate:

1. objective parsed
2. environment observed
3. next action selected
4. real tool executed
5. result observed
6. new decision selected from that result
7. hypothesis/evidence state updated
8. verification performed
9. conclusion or evidence-insufficient state persisted
10. event stream reflects the work

Then run a second objective against the same entity and verify memory changes the investigation behavior.

Then force one tool failure and verify recovery.

Then cancel one active mission and verify no false completion.

Then verify project isolation.

## Final report requirement

Do not report “fully agentic” unless the acceptance objective passes.

Your final report must include:

- architecture changes
- exact reused existing components
- exact files changed
- execution lifecycle
- tool decision contract
- blackboard/hypothesis representation
- memory integration
- subagent integration
- realtime transport
- tests and commands
- acceptance results
- known pre-existing failures
- remaining risks

The standard is not “the UI looks like an agent.”

The standard is:

> **ANVAYA can independently pursue a goal, act on its environment, observe results, adapt its plan, verify its conclusion, and remember what it learned.**
