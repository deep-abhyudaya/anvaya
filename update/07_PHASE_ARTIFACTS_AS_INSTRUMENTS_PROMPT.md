# PHASE 6 — TURN EXISTING ARTIFACTS INTO AGENT-SELECTED INSTRUMENTS

Do not remove or redesign the dataset-grounded artifact system.

The goal is to change HOW the agent uses it.

## Existing artifact types

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

## Current problem

Project objectives can route toward artifact generation. The agent therefore risks looking like a fixed artifact generator with an LLM narrator.

Fix the control flow so artifacts are selected because they answer an active question.

## Required semantics

If objective:

`Investigate HOST-17`

the agent should determine which evidence is missing.

Potential sequence:

- observe host
- inspect telemetry
- investigate relationships
- run graph/orbit analysis if needed
- reconstruct timeline if needed
- run BlastScope if impact is relevant
- verify
- conclude

It should NOT be required to generate every artifact.

## Keep artifact provenance

Every artifact used by an investigation must remain tied to:

- project
- dataset
- generation
- execution/mission where applicable
- source evidence

## Artifact selection policy

A useful model-facing summary is:

```text
orbit = relationship-pattern evidence
replay = temporal-sequence evidence
reach = reachability evidence
ecosystem = entity/network context
arena = engine/detection comparison
impact = affected assets/impact evidence
ledger = audit/provenance
```

The agent chooses tools based on evidence needs.

## Dynamic analytical outputs

If the agent needs a one-off analytical object such as:

- credential timeline
- attack-path comparison
- evidence bundle

first see whether it can be represented using existing result/artifact payload infrastructure.

Do not create a new permanent artifact type unless:

- it is reused
- it is user-visible
- it has a stable schema
- it has provenance
- it has a clear lifecycle

## Trophy Wall

Trophies should represent meaningful findings/outcomes, not generic generated cards.

A trophy should link to:

- finding/case
- evidence
- execution
- dataset/generation

## Acceptance test

Run an objective where only 2–3 artifacts are useful.

Verify that ANVAYA does not generate all 11 artifact types merely because they exist.
