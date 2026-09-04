# ANVAYA — MASTER PROMPT: TURN THE EXISTING SYSTEM INTO A GENUINE AGENTIC INVESTIGATION ENGINE

You are the staff/principal engineer responsible for integrating a genuinely agentic execution architecture into the EXISTING ANVAYA repository.

Your task is not to redesign ANVAYA from scratch.
Your task is not to create a new prototype beside the current system.
Your task is not to add more dashboard screens.
Your task is not to make artifact generation look agentic.

Your task is to make the EXISTING ANVAYA agent capable of autonomously accomplishing meaningful objectives through repeated observation, planning, tool use, adaptation, verification, and memory — while preserving the existing engines, APIs, security model, frontend, artifact system, subagents, execution events, and judge flow.

## 0. SOURCE-OF-TRUTH HIERARCHY

Use this order when making decisions:

1. Existing implementation and existing tests.
2. `AGENTS.md` and existing architecture/contract documents.
3. Existing domain engines and persistence models.
4. The requirements in this prompt.
5. Conservative assumptions documented in `docs/ASSUMPTIONS.md`.

Never invent an existing capability. Search the repository before adding anything.

## 1. ABSOLUTE INTEGRATION RULE

The application already has:

- `AgentOrchestrator`
- `ToolRegistry`
- `LocalToolExecutor`
- model-backed `ModelPlanner`
- deterministic planner fallback
- `EventStore`
- `Execution` / `ExecutionEvent`
- `SubagentSpawner`
- project/dataset/generation/artifact persistence
- dataset-grounded `ArtifactGenerator`
- existing SentinelBacktracker
- BlastScope
- What-If
- replay
- graph/orbit/reach/segment analysis
- n8n/Tavily adapters
- Agent Console
- chat streaming
- provider/model selection

INTEGRATE THESE.

Do not create:

- `NewAgentOrchestrator`
- `AgentEngineV2`
- `SecondToolRegistry`
- `NewEventBus`
- `NewWorldModel` disconnected from project/generation state
- `AgentDatabase`
- `MissionDatabase` that duplicates execution state without a clear reason
- a second frontend agent context
- a second SSE pipeline

If a new abstraction is necessary, first identify the existing abstraction it extends or replaces, then migrate the existing call paths to it. There must be one authoritative execution state.

## 2. THE PRODUCT TRANSFORMATION

Today the mental model is too close to:

`USER OBJECTIVE → ONE PLAN → ARTIFACT/TOOL CHAIN → RESULT`

Transform it to:

`USER OBJECTIVE`
`→ OBSERVE ENVIRONMENT`
`→ FORM/UPDATE GOAL STATE`
`→ PLAN NEXT BEST ACTION`
`→ SELECT TOOL`
`→ EXECUTE`
`→ OBSERVE RESULT`
`→ UPDATE WORLD/BLACKBOARD/MEMORY`
`→ VERIFY`
`→ REPLAN OR COMPLETE`
`→ PERSIST EXECUTION`

The agent must be capable of multiple cycles.

## 3. THE DASHBOARD-REMOVAL TEST

The definitive architecture test is:

> If the frontend dashboard were removed, could the ANVAYA backend agent still receive a meaningful objective and autonomously investigate it using real tools until it reached a justified conclusion?

The answer must become YES.

A dashboard visualization is not evidence of agentic behavior.

## 4. FIRST: RECONNAISSANCE, NOT CODING

Before modifying anything, inspect the entire repository and specifically trace:

- `AgentOrchestrator.start/run/_run_project_plan`
- model planner / deterministic planner selection
- tool registration and parameter validation
- every `LocalToolExecutor.handle_*`
- event persistence and sequence allocation
- execution lifecycle/status transitions
- project/dataset resolution
- generation/artifact persistence
- subagent spawning and parent-event propagation
- chat streaming vs agent execution
- Agent Console state and event consumption
- artifact pages and their API dependencies
- auth/project/organization boundaries
- all existing tests

Produce a private coverage matrix before editing.

## 5. AGENT WORLD / ENVIRONMENT

Do not create a second world database.

Treat existing persisted ANVAYA state as the environment:

- organization
- project
- datasets and checksums
- generations
- artifacts and provenance
- telemetry
- detections
- incidents
- graph nodes/edges
- replay runs
- simulations/counterfactuals
- audit records
- subagent executions
- current execution events

Create a thin, queryable environment-observation layer over those existing records only where the orchestrator currently lacks a clean snapshot.

The observation should be able to answer:

- which project is active?
- which dataset is authoritative?
- which generation is current?
- what artifacts exist?
- which artifacts are stale/missing?
- what incidents exist?
- what previous investigations exist?
- what hypotheses/findings exist, if present?
- what actions are pending?
- what evidence is available?
- what objectives remain unresolved?

Do not copy entire database tables into prompt context. Build compact, typed summaries with IDs and evidence references.

## 6. OBJECTIVES, MISSIONS, AND TASKS

Use the existing `Execution` as the canonical runtime execution identity.

If persistent mission/task semantics are needed, integrate them with `Execution` rather than creating an unrelated lifecycle.

A mission needs, conceptually:

- objective
- project
- dataset scope
- success condition
- failure condition
- max iterations/tool calls
- autonomy/confirmation policy
- current state
- started/completed timestamps
- result
- unresolved questions

Do not introduce a large schema when the information can live safely in existing execution payload/state.

Support objectives such as:

- “Find the most important security issue in this dataset.”
- “Investigate HOST-17.”
- “Explain the root cause of INC-123.”
- “Find likely lateral movement.”
- “Calculate the blast radius of the strongest finding.”
- “Keep investigating until confidence is above 0.85 or the evidence is exhausted.”

The agent should determine the path instead of mapping each objective to a fixed artifact sequence.

## 7. ITERATIVE AGENT LOOP

Refactor the current orchestration semantics around repeated decision cycles.

Conceptual loop:

```python
state = observe_environment()

while not terminal:
    decision = planner.next_action(state, goal, tool_catalog)
    emit_decision(decision)

    if decision.kind == "tool":
        result = execute_tool(decision.tool, decision.inputs)
        persist_result(result)
        state = observe_environment(previous_result=result)
        continue

    if decision.kind == "replan":
        state = observe_environment()
        continue

    if decision.kind == "ask_user":
        pause_execution()
        break

    if decision.kind == "complete":
        verification = verify_goal(state, decision.claim)
        if verification.accepted:
            complete_execution()
        else:
            revise_plan()
```

This is conceptual. Preserve the repository's synchronous/asynchronous boundaries where practical.

The important behavioral property is adaptive iteration, not the exact loop syntax.

## 8. MODEL PLANNING CHANGE

The current `ModelPlanner` asks the model for a full `plan` array.

Do not immediately throw this away.

Evolve it in the smallest safe step so the model can also select a NEXT action from current observations.

Prefer structured decision output such as:

```json
{
  "decision": "tool",
  "tool": "correlate_entities",
  "inputs": {...},
  "purpose": "Test whether the leading anomaly is related to the privileged identity.",
  "confidence": 0.74,
  "expected_information_gain": 0.81,
  "continue_after_result": true
}
```

or a typed equivalent.

Never allow raw free-form model output to directly mutate state.

## 9. TOOL REGISTRY EVOLUTION

The existing `ToolRegistry` is authoritative.

Retain existing tools and organize them into capability families:

OBSERVATION:
- get_incident
- get_telemetry
- inspect_detection
- metrics/context/project/dataset lookups where existing contracts permit

INVESTIGATION:
- run_sentinel_trace
- confirm_ground_truth
- threat_intelligence_lookup
- graph/orbit/reach/segment analysis

ANALYSIS:
- run_blastscope
- run_what_if
- run_replay
- build_or_update_ecosystem
- detection/rule validation tools

ARTIFACT:
- generate_artifacts
- manage_artifacts

AUDIT/ACTION:
- append_audit_record
- verify_audit_chain
- seal_incident
- trigger_automation
- create/update case/finding/recommendation capabilities IF equivalent existing domain persistence can be reused

DELEGATION:
- spawn_subagent

DEVELOPMENT/VERIFICATION:
- run_tests where already intended

Do not add a new tool merely because a screen exists.
Add a capability when there is a real backend operation needed to solve an objective.

## 10. TOOL SELECTION MUST BE GOAL-DRIVEN

The model should not think:

“Which artifacts exist?”

It should think at the capability level:

“What evidence is missing to answer the user's question?”

Example:

User: “What's the biggest threat?”

Bad:
- generate orbit
- generate ecosystem
- generate replay
- generate trophy

Good:
- inspect dataset/project state
- detect anomalies
- rank candidates
- correlate strongest candidates
- investigate strongest candidate
- validate evidence
- conclude

An orbit/replay/ecosystem may become useful tools during that process, but they are means, not objectives.

## 11. OBSERVATION + BLACKBOARD

Do not introduce a second database solely for a blackboard.

Persist compact blackboard state through the existing execution/event mechanism or the smallest suitable extension of the existing execution model.

The blackboard should contain:

- goal
- current hypothesis set
- evidence references
- known facts
- contradictions
- open questions
- completed actions
- failed actions
- current candidate
- next best action
- confidence

Example:

```text
GOAL: find credible threat
FACTS: 124 entities / 912 relationships / 7 incidents
HYPOTHESES:
  credential compromise 0.71
  malware execution 0.21
ACTIVE: HOST-17
OPEN QUESTIONS:
  credential source?
  was SERVER-9 intentionally accessed?
NEXT ACTION:
  inspect authentication history
```

This state must be derived from real observations.

## 12. HYPOTHESES

Integrate hypothesis handling into execution state rather than creating a disconnected “AI reasoning database.”

Each hypothesis should support:

- identifier
- statement
- confidence
- evidence_for
- evidence_against
- unknowns
- status: proposed/testing/supported/rejected
- next test

The model may propose hypotheses.
The system must store evidence references deterministically.

Never claim that confidence is mathematically calibrated unless the underlying method supports that claim.

Use wording such as:

`agent assessment: 0.78`

rather than implying statistical certainty.

## 13. CHANGE OF MIND

The agent must be allowed to invalidate a previous hypothesis.

Example:

Initial:
`HOST-17 suspicious — assessment 0.78`

New observation:
`HOST-17 identified as a known vulnerability scanner`

Agent:
`Reassessing candidate. The original anomaly is likely benign. Assessment reduced to 0.14.`

Persist the observation and the change, not private chain-of-thought.

## 14. NEXT-BEST-ACTION BEHAVIOR

The strongest agent behavior is deciding what information is most useful next.

Use a transparent heuristic or model-produced score where appropriate:

- relevance to objective
- expected information gain
- tool reliability
- evidence freshness
- cost/time
- risk/approval requirements
- dependency availability

Example:

```text
Authentication search — information gain 0.82
Process inspection — 0.61
Another visualization — 0.12
```

This can be an operational decision summary, not hidden reasoning.

## 15. VERIFICATION GATE

No agent claim should automatically become a final finding.

Require verification against available evidence:

- reference IDs resolve
- timestamps are coherent
- relationships exist
- required tool results succeeded
- provenance is valid
- project/dataset association is correct
- confidence threshold or success condition is actually met

If verification fails:

`replan → collect missing evidence → verify again`

## 16. RECOVERY LOOP

When a tool fails:

1. classify failure
2. determine whether retry is safe
3. retry if justified
4. otherwise select an alternative compatible tool
5. update the blackboard
6. continue if the goal remains achievable
7. stop only when required

Never turn a failed tool into a fake success.

## 17. SUBAGENTS

Reuse `SubagentSpawner` and `SubagentExecution`.

Do not create a new worker framework.

Allow the parent agent to delegate when:

- the task is decomposable
- parallel work is beneficial
- each subtask has a concrete deliverable

Example:

Parent: “Determine the most credible attack path.”

Subagents:
- timeline analysis
- network path analysis
- identity correlation

Return structured results:

- finding
- evidence IDs
- confidence/assessment
- unknowns
- recommended next action

The parent synthesizes; subagents do not independently mutate unrelated project state unless explicitly authorized.

## 18. MEMORY

Do not add generic “chat memory” that merely repeats conversation history.

Integrate 4 practical memory classes:

WORKING:
- current execution
- current plan
- current hypotheses

EPISODIC:
- prior completed investigations/executions for the same project/entity/incident

SEMANTIC:
- durable project facts already stored in domain records

PROCEDURAL:
- successful investigation patterns / tool sequences where this can be represented safely and deterministically

Prioritize existing execution/artifact/incident records before adding schema.

Memory must influence next decisions.

## 19. ARTIFACTS BECOME INSTRUMENTS

Keep all 11 artifact types and the dataset-grounded generator.

Do not remove:
- incidents
- arbor
- impacts
- reach
- replay
- ecosystem
- arena
- orbits
- segments
- trophy_wall
- ledger

But stop making them the default goal.

The agent should decide:

- “I need network relationship evidence” → orbit analysis may help.
- “I need event ordering” → replay may help.
- “I need reachability” → reach/BlastScope may help.
- “I need entity relationships” → ecosystem may help.
- “I need to preserve a significant finding” → existing artifact/case/finding mechanism may help.

The dashboard should render these outputs, but the agent's success must not be measured by the number of artifacts created.

## 20. DYNAMIC AGENT ARTIFACTS

Do NOT immediately invent arbitrary dynamic database artifact schemas.

First reuse `ProjectArtifact` / `ProjectArtifactPayload` and existing generation/provenance infrastructure.

If new agent-produced analytical outputs are required, represent them as a typed purpose-bearing artifact under the existing artifact system whenever possible:

- purpose
- inputs
- provenance
- mission/execution ID
- dataset/generation ID
- evidence refs
- summary

Only add a new artifact type when the output is genuinely reusable and user-visible.

## 21. PERMISSION BOUNDARIES

Reuse `ToolDefinition.risk_level`, `requires_confirmation`, and profile confirmation/autonomy policy.

Classify operations as:

READ
SAFE WRITE
REQUIRES APPROVAL
DESTRUCTIVE

Respect project/org auth boundaries.

Never trust model-supplied project IDs or dataset IDs without server-side resolution and authorization.

## 22. REALTIME OBSERVABILITY

Reuse `EventStore`, `ExecutionEvent`, existing SSE endpoint, and existing Agent Console state.

Add user-safe events such as:

- agent.observation
- agent.decision
- agent.replan
- agent.verification_started
- agent.verification_passed
- agent.verification_failed
- agent.hypothesis_created
- agent.hypothesis_updated
- agent.hypothesis_rejected
- agent.memory_recalled
- agent.subtask_started
- agent.subtask_completed
- agent.awaiting_input
- execution.iteration_started
- execution.iteration_completed

Only add the minimum event types needed.

No private chain-of-thought.

Visible “reasoning” must be concise operational summaries generated by the model or safe deterministic summaries derived from actual state.

## 23. IMPORTANT CURRENT BUG/ARCHITECTURAL GAP TO FIX

`/api/v1/agent/execute` currently invokes `orchestrator.run(...)` synchronously and the frontend then polls execution events.

Do not assume this is real streaming.

For long-running agent executions, integrate execution backgrounding/cooperative execution with the existing EventStore/SSE design so:

- request returns an execution ID quickly
- execution continues server-side
- events are persisted as work occurs
- SSE can stream events live
- polling remains a fallback
- reconnect can replay missed events

Do not use artificial sleeps.

## 24. CHAT VS AGENTIC MODE

Preserve the existing distinction:

- chat is a conversation/model-response path
- agentic mode is tool-using objective execution

Do not route serious objectives through plain chat just because streaming chat already exists.

Use chat for questions that do not require action.
Use agent execution for tasks requiring environment interaction, iteration, tools, persistence, verification, or autonomous work.

## 25. USER INTERACTION DURING EXECUTION

Allow safe follow-up controls against an active execution:

- stop/cancel
- skip optional objective
- change dataset
- narrow scope
- ask for status
- request a different investigation target

Do this through the existing execution context and event stream.

Do not start an unrelated new execution every time when the user is clearly modifying the active mission.

## 26. STOPPING CRITERIA

The agent must have explicit termination conditions:

- success condition met
- evidence exhausted
- iteration limit
- tool-call budget
- time budget
- unrecoverable error
- user cancellation
- approval required

Do not allow open-ended runaway execution.

## 27. COST/PERFORMANCE CONTROL

Use compact observation summaries.
Do not dump full telemetry or all graph edges into the model context.

Prefer:
- top-k candidates
- summarized counts
- evidence IDs
- bounded windows
- paginated tool results

Use concurrency only when dependencies allow it.

## 28. SECURITY / DEFENSIVE SCOPE

ANVAYA remains a defensive SOC simulator.

Agent tools must not become arbitrary real-world exploitation mechanisms.
Keep synthetic deterministic scenarios and replay boundaries.

## 29. TESTING — DO NOT “PROVE” AGENTICITY WITH UI SNAPSHOTS

Add backend tests for:

1. repeated agent loop iterations
2. planner choosing next action from tool result
3. plan revision
4. hypothesis creation/update/rejection
5. verification pass/fail
6. retry/fallback/replan
7. mission stopping criteria
8. memory recall affecting next action
9. subagent delegation and synthesis
10. cancellation
11. project/org isolation
12. provenance
13. event ordering
14. reconnect/event replay
15. model unavailable → deterministic fallback

Add an end-to-end objective test:

`Find the most important security issue in this project.`

The expected behavior is not a fixed sequence.
The assertion should verify:

- at least 2 decision cycles
- at least one observation from a real tool result
- at least one adaptive or conditional next action
- verification before final finding
- persisted execution result
- evidence references

## 30. FRONTEND INTEGRATION

Do not redesign the Agent Console.

Extend:

- `agent-context.tsx`
- `agent-console.tsx`
- `lib/api.ts`

to render the new state:

- objective
- current iteration
- active tool
- current hypothesis
- open questions
- live plan
- plan changes
- verification
- memory recall
- subagents
- final finding

Use existing EventCard patterns and existing ANVAYA visual language.

Do not introduce a second frontend state machine.

## 31. ACCEPTANCE TEST

Run this objective:

> “Find the most important security issue in this project. Decide how to investigate it. Do not generate artifacts unless they help answer the question. Continue until you have a high-confidence conclusion or the evidence is insufficient.”

A successful execution must show:

1. environment observation
2. objective interpretation
3. next action choice
4. real tool execution
5. observation from tool result
6. changed/updated plan or next action
7. evidence/hypothesis state
8. verification
9. conclusion or evidence-insufficient result
10. persistent execution state

If the execution simply produces orbit/ecosystem/replay/trophy artifacts in a fixed order, the implementation has failed this task.

## 32. DEFINITION OF DONE

Do not declare completion because:
- new classes exist
- new tool names exist
- UI cards exist
- events exist
- tests compile

Declare completion only when the existing ANVAYA system can demonstrate:

`goal → observe → choose → act → observe → adapt → verify → remember → outcome`

using the existing engines and persistence boundaries.

The final system must be able to solve a useful objective with the dashboard removed.
