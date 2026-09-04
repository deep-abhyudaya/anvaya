# Workflow 00: Real-Time Log Watcher + Live Scoring (build this FIRST)

## Why this workflow exists, and why it's numbered before 01

The user identified a real gap: ANVAYA's pitch claims it "watches
activity and flags new attacks and intruders as they happen." Verified
against the actual code (see `.devin/rules.md` and this project's audit
history), that claim is **not yet true**. Specifically:

- `POST /telemetry` (`backend/anvaya/routers/telemetry.py`) only stores
  events — it never scores them.
- `AlertnessEngine.predict()` / `.predict_single()`
  (`ml/anvaya/alertness/__init__.py`, lines 173–202) are fully
  implemented and correct, but are **never called** from any router,
  the CLI, or the demo orchestrator against a genuinely new/incoming
  event. They're only used in training/self-evaluation.
- There is no process anywhere in the codebase that tails a log file,
  subscribes to a stream, or otherwise watches for real-time input.

This workflow builds the missing piece: a CLI command that watches for
real-time logs and a live-scoring path that turns a positive detection
into a real incident — making the pitch's core claim actually true, not
just narratively true for one scripted demo. **Do this before Workflow
01 (Tavily/n8n activation)** — this is the more load-bearing gap for
demo credibility, since a technically-literate judge probing "what
happens when a genuinely new log line comes in" is a likely, hard
question, whereas Tavily/n8n activation is lower-risk, additive polish.

Workflow 01 (Tavily/n8n) remains valid and should still be done —
just after this one.

## Part A — Wire live scoring onto ingest (the "brain," build first)

This is the prerequisite for Part B; a watcher with nothing scoring its
output is pointless.

### Step 1 — Add a live-scoring path, without breaking existing ingest

`POST /telemetry` in `backend/anvaya/routers/telemetry.py` currently
just persists a `TelemetryEvent` and returns it. Do not remove or
change this base behavior (other code may depend on plain ingest without
side effects — check for callers before changing shared behavior).
Instead, add a new function (e.g. `score_and_maybe_flag(event, session)`
in a new module `backend/anvaya/live/__init__.py` or similar — keep it
separate from the router, matching this codebase's existing convention
of thin routers calling into engine modules) that:

1. Loads the active Alertness model (`AlertnessEngine(session)`, call
   `.load_latest()` — this already exists and works, see
   `ml/anvaya/alertness/__init__.py` line 160).
2. Calls `.predict_single(event)` with the just-created `TelemetryEvent`.
3. If `detected` is `True` in the result:
   - Check whether an `Incident` already exists for this
     `event.incident_id` (if the event arrived with one) or create a
     new one — follow the exact `Incident` construction pattern already
     used in `backend/anvaya/demo/orchestrator.py` (search for where it
     creates the pre-patch incident) so field names/required values
     match exactly, don't guess at the `Incident` model's required
     fields.
   - Set the incident's initial status to reflect a live catch (check
     the `IncidentStatus` enum in `backend/anvaya/models/incident.py`
     for the correct value — likely something like `DETECTED` or
     `ACTIVE`, not `MISS`, since this path represents a successful
     catch, not the deliberately-scripted miss scenario).
   - Write an `AuditRecord` for the detection, following the existing
     hash-chain pattern (`backend/anvaya/models/audit.py`) — reuse
     `compute_hash`/the existing record-creation helper, don't
     reimplement hashing.
4. Return the score/detection result alongside the stored event so the
   API caller (and eventually the CLI watcher) knows what happened.

### Step 2 — Call this from `POST /telemetry`

Modify `create_telemetry` in `routers/telemetry.py` to call the new
`score_and_maybe_flag` function after persisting the event, and include
its result in the response (e.g. add a `"detection": {...}` key to the
existing response). Keep this fast — `predict_single` on one event
should be cheap (no batch overhead) — but if it becomes a latency
concern, note that in your report rather than silently making ingest
async without being asked to.

### Step 3 — Tests

Add `tests/test_live_scoring.py` (or extend an existing telemetry test
file if one covers `POST /telemetry` already — search `tests/` first):
- Train a model on synthetic data within the test (reuse
  `DataFactory`/`AlertnessEngine.train` exactly as
  `tests/` likely already does elsewhere — search for existing
  `AlertnessEngine` test usage before writing a new training fixture).
- POST a telemetry event crafted to be anomalous (e.g.
  `is_off_hours=True, is_new_device=True, is_anomalous_process=True`)
  and assert the response's `detection.detected` is `True` and that an
  `Incident` was actually created in the DB.
- POST a normal-looking event and assert no incident is created.
- Run `pytest tests/ -q --no-header` afterward and confirm the existing
  285-passing baseline isn't broken.

## Part B — The CLI watcher (the "ears")

### Step 1 — Add a new Typer command

In `backend/anvaya/cli/typer_app.py`, follow the exact pattern of the
existing `train()`/`serve()` commands (lines 104, 500) — same
`init_db()` + `get_session_sync()` bootstrap, same `console.print`
(Rich) output style for consistency with the rest of the CLI. Add:

```python
@app.command()
def watch(
    source: str = typer.Option(..., help="Path to a log file to tail, or 'synthetic' for a simulated live feed"),
    interval: float = typer.Option(1.0, help="Poll interval in seconds for file-based sources"),
):
    """Watch a real-time log source and score events as they arrive."""
```

### Step 2 — Two source modes, both real (not two different levels of fake)

1. **File-tail mode** (`source` = a real file path): tail the file the
   way `tail -f` does — read new lines as they're appended, don't
   re-read the whole file each poll. Each new line must be parsed into
   the `TelemetryEvent` shape (see `models/telemetry.py` fields listed
   in this workflow's audit notes below) — write a small, honest parser
   for a plausible log line format (e.g. a simple structured format:
   `timestamp|actor|host|event_type|process|is_off_hours|...`, or JSON
   lines) and clearly document the expected format in the command's
   `--help` text and in a README section, since a real SOC's actual log
   format will differ and this is explicitly a reference
   implementation, not a universal log parser. Do not silently
   fabricate field values that aren't in the log line — leave them at
   the `TelemetryEvent` model's defaults if absent.
2. **Synthetic live-feed mode** (`source="synthetic"`): reuse
   `DataFactory`/`world_architect.py`'s existing scenario generation to
   emit events at a realistic pace (e.g. one every 1–3 seconds,
   randomized) rather than all at once — this gives a genuinely
   watchable, real-time-feeling demo without needing a real external
   log source, and is honest about being synthetic (print
   `[SYNTHETIC]` or similar in the CLI output for every emitted event,
   don't let it look like real production logs).

### Step 3 — POST each parsed/generated event to the live-scoring path

Either call `POST /telemetry` over HTTP (if the CLI is meant to run
against a separately-running server — check how `serve()` and other
commands in this file expect the server's lifecycle to work before
assuming), or call the same underlying function directly in-process if
the CLI is meant to be self-contained (matches how `train()` directly
uses `AlertnessEngine` without going through HTTP). Prefer whichever
matches this codebase's existing CLI-to-backend relationship — check
`train()`/`evaluate()`'s pattern (direct engine calls) as the likely
correct precedent over HTTP.

### Step 4 — Live terminal output

For each event processed, print (Rich, matching `train()`'s style):
- Timestamp, actor, host, event type — the human-readable summary.
- The detection result: score, `detected: True/False`, and if `True`,
  the incident ID just created, in a visually distinct color (e.g. red/
  bold for detected, dim for normal) — this is the actual demo moment,
  make it readable at a glance for a live audience.

### Step 5 — Tests

- Unit test the log-line parser separately from the live loop (pure
  function: line in, `TelemetryEvent`-shaped dict out) — easy to test,
  don't skip it.
- A test for `synthetic` mode can assert it produces N events with
  valid schema in a bounded time window (don't test against real wall-
  clock sleep in the fast test suite — allow an injectable/mockable
  interval or a `--count` limit for testability, e.g.
  `--max-events 5` to bound a test run).

## Part C — Frontend visibility (make the live moment demoable on screen)

- Add a way for `/overview` or `/incidents` to reflect a newly-created
  incident without a manual page refresh — check whether the frontend
  already polls or has any SSE/websocket wiring (search for
  `EventSource` or `useEffect.*interval` in the frontend repo) before
  building a new mechanism; reuse if something already exists (the
  `/agent/executions/{id}/stream` SSE endpoint on the backend suggests
  a precedent for streaming — a similar `/incidents/stream` could
  follow the same shape if nothing simpler already covers this).
- If no live-refresh mechanism exists and building one is out of scope
  for this task, a simple polling `setInterval` refetch on `/incidents`
  every few seconds is an acceptable, low-risk fallback — note this
  explicitly in your report as the chosen approach and why.

## Step — Report back (required, see `.devin/rules.md` Rule 7)

- Confirm `predict_single` is now actually called from a real ingest
  path, with the exact file/function where that call happens.
- Confirm the `watch` CLI command exists, both modes work, and paste
  (or describe precisely) a sample terminal output showing at least one
  detected and one normal event.
- State clearly: is this ready to demo as "watch it flag a new
  attack live" during the actual pitch, or does it still need the
  frontend polling piece (Part C) to be visible on screen? Don't claim
  demo-readiness if Part C wasn't completed.
- Test command and result, confirming the 285-passing baseline held.
