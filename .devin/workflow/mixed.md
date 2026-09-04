# Workflow: Mixed/combined objective plans (investigation + artifact generation)

Requires workflow 02 complete, tested, and merged/verified working first.
Do not start this workflow until "generate orbits then incidents then impact
tree gallery" and "generate all" both narrate correctly per-artifact in the
running app. This workflow builds on that loop; it does not replace it.

Goal: a single objective that mixes incident-investigation steps and
artifact-generation steps — e.g. "investigate INC-2214, then rebuild the
orbits and impact gallery" — produces ONE ordered, fully-narrated plan, using
the same per-step loop from workflow 02, instead of requiring the user to
split the request into separate turns.

## Steps

1. From workflow 01's findings, locate the function that currently classifies
   an objective as investigation-shaped vs project-artifact-shaped (routes to
   `run_investigation` vs `run_project_plan`). Read it fully before changing
   anything.

2. Extend that classification so it can detect a mixed objective — one that
   contains both an incident reference (existing incident ID pattern, or
   "investigate"/"triage" language already used to trigger
   `run_investigation`) and artifact-generation language (existing
   `parse_scope` artifact-alias detection from `scope.py`). Reuse
   `parse_scope`'s alias table for the artifact-detection half — do not
   duplicate it.

3. When a mixed objective is detected, build a single ordered plan whose
   steps are a concatenation of:
   - investigation tool-call steps, in the order implied by the objective
     text (or the existing deterministic scenario order from
     `DEVIN_MASTER_PROMPT.md`'s "AGENTIC DEMO SCENARIO" section if the
     objective doesn't specify an order for the investigation portion)
   - artifact-generation steps, one per artifact type, in the literal order
     the user listed them (same as workflow 02)
   using the exact plan-step shape from workflow 02 (each step self-contained
   with its own `tool`, `inputs`, `label`). Do NOT merge `manage_artifacts`
   and investigation tools into one tool call — they stay as distinct steps
   in one list.

4. Execute the combined plan through the same per-step loop workflow 02
   built (reasoning → decision → tool-requested → [build stream or
   investigation-tool result] → observation-created, per step, in order).
   The loop should not need to know or care whether a given step is an
   investigation tool or `manage_artifacts` — it's just "execute this step's
   tool call and narrate it," which is already type-agnostic if workflow 02
   was implemented against the shared plan-step shape.

5. If the objective's investigation portion and generation portion have no
   explicit ordering relationship (e.g. "investigate X and also make sure
   orbits and incidents are up to date" — ambiguous whether investigation or
   generation should run first), default to investigation-first, generation-
   second. Document this default in `docs/AGENTIC_AUDIT_MULTI_ARTIFACT.md`.

## Tests to add

- Mixed-objective test: "investigate INC-XXXX and rebuild orbits and the
  impact gallery" (use a real test-fixture incident ID). Assert the event log
  shows investigation-tool steps and artifact-generation steps, each
  separately narrated, in the expected order, followed by one
  `agent.completed`.
- Regression: pure investigation objective and pure multi-artifact objective
  (from workflow 02) both still produce their correct event shapes —
  confirm the new classification logic didn't change routing for either.

## Exit criteria

Do not report this workflow complete until:
- The mixed-objective test passes.
- Both regression tests (pure investigation, pure multi-artifact) still pass
  unmodified from workflow 02's state.
- A manual run of a mixed objective against a real project+incident narrates
  and executes both halves correctly in the running app.