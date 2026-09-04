# MASTER PROMPT — Execute the Real-Time Integration Workflows

You are working in the ANVAYA repository. `.devin/rules.md` and
`.devin/workflows/00-*.md` through `.devin/workflows/04-*.md` already
exist in this repo and are the authoritative spec for this work — read
all five files in full before writing any code. This prompt's job is to
tell you to actually RUN them, in order, end to end, not to restate
their content.

## Non-negotiable execution order

Do not reorder, parallelize across workflows, or skip ahead. Workflow
00 is a hard dependency for everything after it — every later workflow
was written assuming Workflow 00's live event pipeline and shared
`on_incident_event` dispatch point already exist. Building 01–04 first
would mean redoing their trigger-wiring once 00 lands, which wastes
time you don't have.

1. `.devin/workflows/00-live-scoring-and-watch-cli.md` — build this
   completely (Parts A, B, and C) before touching anything else.
2. `.devin/workflows/01-activate-tavily-n8n.md` — including the
   live-dispatch wiring steps (1c, 2c), not just the standalone
   activation steps.
3. `.devin/workflows/02-signal-api-and-launchpad.md`
4. `.devin/workflows/03-new-integration-gmail-first.md`
5. `.devin/workflows/04-lyzr-and-mcp-devwork.md`

If you get blocked on a missing credential (Tavily key, n8n instance,
Signal API docs, Launchpad API docs, Gmail credentials, Lyzr key), do
not stop all work — post the exact blocker per Rule 7, move to the next
independently-buildable piece of the SAME workflow (e.g. build Gmail's
adapter/handler/test scaffolding even without a real credential yet,
per Workflow 03 Step 3's explicit instruction), and only move to the
next workflow number once the current one's buildable-without-a-human
work is genuinely exhausted.

## Before you write any code

1. Read `.devin/rules.md` in full, especially Rule 1 (ground truth —
   what's real vs. stubbed vs. missing) and Rule 2a (the shared
   dispatch point every workflow after 00 depends on).
2. Read all of `.devin/workflows/00-live-scoring-and-watch-cli.md`
   through `04-lyzr-and-mcp-devwork.md` in full before starting Step 1
   of Workflow 00 — later workflows reference exact function names
   (`on_incident_event`, `score_and_maybe_flag`) that 00 defines, and
   you need the full picture to avoid naming/shape drift between them.
3. Confirm the actual local run commands before assuming any — this
   repo has no documented `Makefile`/`justfile` at the time this prompt
   was written. Check `pyproject.toml`'s `[project.scripts]` (confirms
   `anvaya = "anvaya.cli:main"` as the CLI entrypoint) and confirm the
   correct way to start the FastAPI server (`backend/anvaya/main.py`
   defines the `app` object — check for a documented `uvicorn` command
   in any README before guessing the module path).
4. Run the existing test suite once, before any changes, and record the
   baseline: `pytest tests/ -q --no-header`. At the time this prompt was
   written the baseline was 285 passed / 14 failed (failures in
   unrelated LLM-catalog-metadata and CLI-shell tests). Confirm this
   still holds — if the baseline has drifted, note the new baseline in
   your first report rather than silently comparing against a stale
   number.

## Execution loop per workflow

For each workflow file, in order:

1. Re-read that specific workflow file immediately before starting it
   (don't rely on your earlier full read — file content may have been
   updated, and re-reading confirms you're building against the current
   version).
2. Implement every numbered step in that file, in the order given.
3. Run `pytest tests/ -q --no-header` after finishing the workflow's
   steps and before reporting it done. The passing baseline must not
   regress — if it does, fix the regression before moving to the next
   workflow, don't carry a broken baseline forward.
4. Produce the exact report format required by `.devin/rules.md` Rule 7
   for that workflow (XP category, live vs. fallback-only status, test
   command + result, credentials still needed).
5. Only after that report is produced, move to the next workflow file.

## What "done" means for this whole master prompt

Not "all five workflow files have been read." Specifically:

- `anvaya watch --source synthetic` is a real, runnable command that
  prints live-scored events to the terminal, with at least one visibly
  flagged as detected.
- A real telemetry event POSTed to `/telemetry` (or fed via the watch
  CLI) that looks like the `ATK-MISS-001`-style attack pattern in
  `simulator/anvaya/scenarios.py` results in a real `Incident` and
  `AuditRecord` being created, without any manual orchestration call —
  purely from the live-scoring path.
- Triggering that live detection also fires Tavily and n8n
  automatically via `on_incident_event`, provided their credentials are
  configured (or is clearly reported as fallback-only/blocked if not).
- Every workflow's Step "Report back" has actually been produced, not
  skipped.
- The full test suite passes at least at the original 285-passing
  baseline, with new tests added per each workflow's testing
  requirements.

## Final summary format, after all five workflows

Produce one consolidated summary (in addition to each workflow's
individual report) covering:

1. A table: workflow number → status (complete / partially complete +
   why / blocked + on what) → XP category → live or fallback-only.
2. The exact commands a human on the team needs to run right now to see
   this working end to end (e.g. "run `anvaya watch --source synthetic`
   in one terminal, open `/incidents` in the browser, watch a new
   incident appear within N seconds, with a Tavily result attached").
3. A list of every credential/account still needed from a human,
   consolidated from all five workflows' individual blockers, so
   nothing is scattered across five separate reports when someone needs
   to go collect API keys.
4. Confirmation of the final `pytest tests/ -q --no-header` result.

Do not claim the pitch's "watches for new attacks and intruders as they
happen" line is now fully backed by working code unless item 2 above is
genuinely true and you've verified it yourself, live, in this
environment — not inferred from reading your own diff.
