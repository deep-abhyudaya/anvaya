# ANVAYA MASTER AUTONOMOUS BUILD WORKFLOW

## Mission
Build the complete ANVAYA project end-to-end with minimal human intervention while preserving correctness, reproducibility, and the self-correction proof.

## How to run
Use this file as the master instruction for a Devin session. Start with:

> Execute `.devin/workflow/MASTER_BUILD.md` from top to bottom. Do not stop after creating a plan. Implement, test, measure, repair, document, and continue through all phases. Use the acceptance gates. When a phase is green, create a focused PR and continue to the next phase.

## Global loop
For every phase:
1. inspect current repository state;
2. read applicable rules and skills;
3. identify dependencies;
4. implement the smallest complete vertical slice;
5. add tests;
6. run tests/lint/typecheck/build;
7. diagnose failures;
8. repair root causes;
9. rerun;
10. update docs and assumptions;
11. create PR/checkpoint;
12. continue.

## Phase 0 — Reconnaissance and architecture
Create:
- `docs/ARCHITECTURE.md`
- `docs/REQUIREMENTS_TRACEABILITY.md`
- `docs/ASSUMPTIONS.md`
- `docs/DECISIONS.md`

Do not code product features until the architecture and contracts are coherent.

Acceptance:
- repository structure defined
- data contracts defined
- incident lifecycle defined
- dependency graph defined
- unknowns documented

## Phase 1 — Foundation
Implement:
- Next.js app
- FastAPI app
- PostgreSQL
- SQLModel
- migrations
- Docker Compose
- configuration
- logging
- test harness
- CI

Acceptance:
- frontend builds
- backend starts
- DB connects
- migrations apply from empty DB
- health checks pass

## Phase 2 — Domain model
Implement entities for:
- incidents
- telemetry
- alerts
- rules
- detection runs
- ground-truth events
- assets
- network relationships
- simulations
- counterfactuals
- response actions
- audit records
- model versions
- replay runs

Implement state machine:
`detected → analyzed → simulated → explained → sealed`

Acceptance:
- invalid transitions rejected
- relations tested
- migrations reproducible

## Phase 3 — Automatic synthetic dataset factory
Create a scenario catalog and generator.

Required capabilities:
- scenario templates
- seeded generation
- configurable volumes
- benign/attack mixtures
- noise injection
- missing fields
- temporal sequences
- entity-aware behavior
- explicit ground truth
- replayable scenario IDs
- automatic train/validation/test split

Create a CLI such as:
- `anvaya data generate`
- `anvaya data validate`
- `anvaya data summarize`
- `anvaya data replay <scenario>`

Acceptance:
- generated dataset validates against schema
- split has zero forbidden leakage
- generation is reproducible from seed + config
- scenario coverage report generated

## Phase 4 — Alertness engine
Implement Isolation Forest behavioral anomaly detection.

Pipeline:
telemetry → feature extraction → preprocessing → training → evaluation → artifact/version → inference

Acceptance:
- evaluation report exists
- inference API works
- model metadata persisted
- no training/test leakage
- unit + integration tests pass

## Phase 5 — SentinelBacktracker
Implement:
- confirmed miss ingestion
- telemetry backtracking
- evidence timeline
- candidate rule proposal
- deterministic rule validation
- identical attack replay
- outcome persistence

Use the LLM only for structured proposal/explanation.

Acceptance:
- at least one deterministic scenario proves `MISS → PATCH → REPLAY → CAUGHT`
- no fake success state exists
- replay is visible in API and UI contracts

## Phase 6 — BlastScope
Implement NetworkX graph construction and blast-radius simulation.

Acceptance:
- deterministic graph fixtures
- path/reachability tests
- clear distinction between observed and simulated relationships
- API and persistence integrated

## Phase 7 — What-If Watcher
Implement Logistic Regression risk model and counterfactual engine.

Acceptance:
- model evaluation report
- feature validation
- counterfactual risk delta
- explanations are explicitly model-based, not causal claims

## Phase 8 — ControlLedger
Implement append-only/tamper-evident audit chaining with model/rule/version references.

Acceptance:
- every automated state-changing action is auditable
- chain verification works
- tampering test fails verification

## Phase 9 — Frontend
Build the judge-ready dashboard around real APIs.

Required experience:
- incident list/detail
- detection evidence
- self-correction replay
- blast radius
- what-if
- audit
- model/rule metadata

Acceptance:
- no production component relies on hardcoded fake results
- responsive UI
- error/loading states
- browser test of core flows

## Phase 10 — End-to-end demo orchestrator
Create a single command:
`anvaya demo`

The command must:
1. generate normal telemetry;
2. trigger a known synthetic attack;
3. ensure the pre-patch path misses;
4. inject ground truth;
5. create incident;
6. backtrack;
7. propose rule;
8. validate rule;
9. replay identical scenario;
10. verify catch;
11. run BlastScope;
12. run What-If;
13. seal audit trail;
14. surface status to UI/API.

Acceptance:
- the demo fails if the corrected rule does not actually catch the replay
- entire sequence can run repeatedly from a clean state

## Phase 11 — Evaluation and observability
Generate:
- precision
- recall
- F1
- false-positive rate
- false-negative rate
- confusion matrices where relevant
- inference latency
- replay success rate
- self-correction success rate
- scenario coverage

Add structured logs and performance timing for each lifecycle stage.

## Phase 12 — Security and reliability audit
Act as hostile QA.
Test:
- auth bypass
- IDOR-like incident access
- injection issues
- malformed telemetry
- malformed LLM output
- invalid state transitions
- audit tampering
- replay false-success
- model/version mismatch
- race conditions
- stale frontend states
- infinite retry loops

Fix confirmed P0/P1 issues before finalization.

## Phase 13 — Deployment readiness
Prepare Vercel frontend + Railway/Fly.io backend + PostgreSQL deployment.

Do not perform irreversible production changes without explicit authorization.

Acceptance:
- production build succeeds
- env template documented
- secrets excluded
- migrations documented
- health checks pass
- rollback notes written

## Phase 14 — Final judge mode
Pretend you are a skeptical SIH technical judge.

Verify the complete claim with actual evidence.

Produce:
- `docs/FINAL_DEMO_SCRIPT.md`
- `docs/FINAL_EVIDENCE.md`
- `docs/LIMITATIONS.md`
- `docs/TECHNICAL_QA.md`

Do not make unsupported claims. Distinguish what is measured, simulated, assumed, or future work.

## Phase gate behavior
A phase is not complete if:
- tests are failing;
- the demo is mocked;
- a critical metric is missing;
- data leakage is suspected;
- docs contradict implementation;
- an acceptance criterion is unverified.

When blocked by an external service, create a local deterministic stub and continue all work that does not require the missing service. Record the exact blocker.

## Autonomous backlog creation
When discovering follow-up work:
- create a clear issue/task with severity and acceptance criteria;
- prioritize P0/P1 before polish;
- never silently expand scope beyond ANVAYA's core proof.
