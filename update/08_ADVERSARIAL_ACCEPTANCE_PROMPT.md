# ANVAYA — ADVERSARIAL ACCEPTANCE / NO-FEELINGS PRODUCTION GATE

You are not allowed to mark the agentic integration complete because the UI looks better or because more tool/event names exist.

You must prove the existing ANVAYA system is genuinely adaptive.

## Gate 1 — Dashboard-removal test

Call the backend agent directly with:

> Find the most important security issue in this project. Decide how to investigate it. Do not generate artifacts unless they help answer the question. Continue until you have a high-confidence conclusion or the evidence is insufficient.

The backend must perform meaningful work without requiring a frontend.

PASS requires:

- environment observation
- at least 2 decision cycles
- real tool results
- next action selected using previous result
- verification before conclusion
- persisted execution

FAIL if:

- it only executes a fixed plan
- it only creates artifacts
- it immediately returns a canned answer

## Gate 2 — Adaptive branch

Provide a fixture where tool A can return one of two materially different observations.

The next tool must differ based on the observation.

PASS if the same objective can produce different valid next actions from different world states.

## Gate 3 — Change of mind

Start with a suspicious entity.

Introduce evidence identifying it as benign.

PASS if hypothesis status/assessment changes and the mission continues with another candidate.

## Gate 4 — Recovery

Force the preferred tool to fail.

PASS if ANVAYA:

- records failure
- selects a valid alternative or retry
- updates state
- continues where possible
- never emits false success

## Gate 5 — Verification

Force a candidate to have contradictory evidence.

PASS if ANVAYA refuses to finalize it and gathers more evidence or returns insufficient evidence.

## Gate 6 — Memory

Execution 1 records an important fact.
Execution 2 targets the same entity.

PASS if the fact is recalled and influences the next action.

## Gate 7 — Subagents

Provide a task that can benefit from network + timeline analysis.

PASS if the parent uses existing subagent infrastructure, receives structured results, and synthesizes them.

## Gate 8 — User interruption

Start a multi-step mission and cancel it.

PASS if execution becomes cancelled and no false completion event appears.

## Gate 9 — Realtime

Observe an execution from another client/browser.

PASS if events appear live, survive reconnect, and can be replayed from persistent history.

## Gate 10 — Artifact restraint

Give an objective where only one artifact is necessary.

PASS if the agent does not mass-generate all artifacts.

## Gate 11 — Project isolation

Project A must never read or mutate Project B's datasets, artifacts, or executions.

## Gate 12 — Provider fallback

Disable the selected model provider.

PASS if the existing fallback path works and truthfully reports fallback usage.

## Gate 13 — No fake intelligence

Search the new implementation for:

- arbitrary sleeps used for UX
- canned “thinking” text unrelated to actual state
- fake progress percentages
- tool events emitted before actual execution
- completion events emitted before persistence
- model claims unsupported by evidence

Any such issue is a FAIL.

## Required final evidence

Your final report must include:

1. exact files changed
2. execution state transition model
3. tool decision contract
4. evidence/blackboard representation
5. memory integration path
6. subagent integration path
7. realtime transport path
8. tests added
9. commands executed
10. exact acceptance-gate results
11. known pre-existing failures
12. remaining risks

Do not claim “fully agentic” unless all gates above pass.
