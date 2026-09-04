# PHASE 3 — BLACKBOARD, HYPOTHESES, MEMORY, AND CHANGE-OF-MIND

Integrate persistent agent state using existing execution/events/domain records. Do not build a disconnected memory product.

## Blackboard

The canonical active execution should expose a compact state:

- goal
- facts
- hypotheses
- evidence refs
- contradictions
- unknowns
- current entity/incident
- current best candidate
- next best action
- completed tool calls
- failed tool calls

Store only what is needed for resumed execution and model context.

## Hypothesis lifecycle

Support:

`proposed → testing → supported | rejected`

Each hypothesis should have:

- hypothesis ID
- concise statement
- assessment/confidence
- evidence for
- evidence against
- unknowns
- next test
- source execution
- timestamps

Do not claim calibrated probability.

## Evidence model

Prefer references to existing records:

- incident IDs
- telemetry event IDs
- detection run IDs
- graph node/edge IDs
- replay IDs
- artifact IDs
- audit IDs

Do not duplicate entire rows into memory.

## Change of mind

Test the exact scenario:

Initial:
`HOST-17 suspicious — assessment 0.78`

New tool result:
`HOST-17 is a known scanner`

Required:

- hypothesis assessment decreases
- candidate ranking updates
- previous assumption remains auditable
- next action changes

## Episodic memory

Before investigating an entity/project/incident, look for prior execution summaries involving the same target.

Recall only relevant compact facts.

Example:

`Prior investigation on SERVER-9 found possible lateral movement. Current mission will check what changed since that execution.`

## Semantic memory

Reuse durable project facts already persisted by ANVAYA.

Do not infer “memory” merely from static frontend context.

## Procedural memory

Only add procedural memory if there is a safe deterministic place to persist successful strategies. Do not invent a learning system.

## Acceptance test

Two executions against the same entity:

Execution 1 discovers a fact.
Execution 2 must be able to recall the fact and choose a different/targeted next action because of it.
