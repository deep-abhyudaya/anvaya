# PROMPT ENGINEERING RULES FOR DEVIN — ANVAYA

These rules are intended to prevent Devin from producing a superficially impressive but architecturally shallow result.

## Rule 1 — Ask Devin to inspect, not imagine

Every phase begins with:

`Inspect the actual repository and trace existing implementations before editing.`

## Rule 2 — Force source anchoring

Name the actual files and classes that own the behavior.

Bad:
`Implement a new agent system.`

Good:
`Extend AgentOrchestrator.run(), ModelPlanner, ToolRegistry, LocalToolExecutor and EventStore without creating duplicate execution systems.`

## Rule 3 — Separate goals from mechanisms

Bad:
`Add a generate-orbit tool.`

Good:
`Give the agent the capability to investigate network relationship anomalies; reuse orbit/graph analysis if the agent determines it is useful.`

## Rule 4 — Require observable evidence

Every major requirement should have:

- code path
- persisted state
- event
- test
- acceptance example

## Rule 5 — Use negative requirements aggressively

Explicitly tell Devin what NOT to do:

- no parallel agent framework
- no fake thinking
- no fake delays
- no static artifacts for live project data
- no fixed artifact checklist for every objective
- no success event before persistence
- no unverified findings

## Rule 6 — Force adaptive examples

Give examples where the correct next action differs based on tool results.
This prevents Devin from satisfying the requirement with a fixed workflow.

## Rule 7 — Make the “dashboard removal test” a hard gate

If the backend cannot solve the objective without UI, the implementation is not done.

## Rule 8 — Ask for a test that would fail under the old architecture

Examples:

- 3+ decision cycles
- branch based on observation
- hypothesis retraction
- retry/fallback
- memory-influenced action

## Rule 9 — Require truthfulness

The agent must only claim:

- a tool ran if it ran
- a result exists if it persisted
- a finding if evidence supports it
- a model was used if that provider was actually used
- an artifact is current if its provenance matches the current world

## Rule 10 — Optimize for information gain, not activity volume

An autonomous agent is not impressive because it ran 20 tools.
It is impressive because it ran the RIGHT tools and stopped when enough evidence existed.

## Rule 11 — Keep user-visible reasoning safe

Expose concise operational summaries, not private chain-of-thought.

## Rule 12 — Keep fallback deterministic and truthful

If the selected model fails, use the existing deterministic path rather than generating a fake model response.

## Rule 13 — Make the agent interruptible

Autonomy without cancellation is poor UX.

## Rule 14 — Make execution resumable

Persist enough state so an interrupted mission can continue safely.

## Rule 15 — Prefer refactoring over accretion

If an existing function does 80% of the required job, upgrade it instead of adding a second function with overlapping semantics.

## Rule 16 — Do not accept “UI proves it”

A green chip called `AUTONOMOUS` proves nothing.
The backend trace must show adaptive behavior.

## Rule 17 — Keep the system legible

A staff-level implementation should leave:

- clear state transitions
- typed contracts
- concise events
- small cohesive modules
- tests
- docs

Do not solve complexity by creating a giant 2,000-line agent god-object.
