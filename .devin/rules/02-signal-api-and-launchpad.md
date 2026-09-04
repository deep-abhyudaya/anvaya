# Workflow: Signal API tracking + Launchpad wiring

Goal: earn XP in the "Signal API" (track real user behavior) and
"Launchpad" (create accounts, leads, campaigns) categories by routing
ANVAYA's real events — now including genuinely live-detected ones from
Workflow 00's `anvaya watch` pipeline, not just demo-scripted ones —
through n8n. **Depends on both Workflow 00 (live event pipeline +
`on_incident_event` dispatch point) and Workflow 01 Step 2 (n8n live and
wired into that dispatch point) being complete.**

**Before starting: get the actual API/webhook contract for Startuped's
Signal API and Launchpad from the hackathon organizers or their docs.
Do not guess field names or auth scheme — a fabricated integration that
doesn't match their real contract earns zero XP and wastes the time
spent building it.**

## Step 1 — Inventory real ANVAYA events worth tracking

Read (don't re-derive from scratch) these existing event sources:
- **`on_incident_event` (Workflow 00 / Rule 2a)** — this is now the
  primary source. It already fires on live-detected incidents
  (`DETECTED`, from real `anvaya watch` input) and on scripted/manual
  ones (`SEALED`, `RULE_APPROVED`, etc.), so hooking Signal API here
  captures both real live user-adjacent behavior AND the demo path,
  with one implementation.
- `AuditRecord` creation points — every sealed incident, every rule
  validation, every replay already produces one of these
  (`backend/anvaya/models/audit.py`), useful if you need finer-grained
  events than what `on_incident_event` currently distinguishes.
- `/agent/executions/{id}/events` — the streaming execution event feed
  already exposed via SSE (`backend/anvaya/routers/agent.py`,
  `stream_execution_events`) — a secondary source for agent-level
  activity, separate from incident lifecycle.
- Frontend page-view-equivalent actions: incident opened, rule
  approved/rejected (check `routers/rules.py` for the approval
  endpoint), project created (check `routers/projects.py` if present) —
  these are genuinely human-driven and may be the strongest fit for
  "track real user behavior" specifically, as opposed to system-
  generated detection events.

Pick 3–5 of these that map cleanly to "real user behavior" for the
Signal API — favor actions a human explicitly took (approving a rule,
opening an incident) over purely automated system events.

## Step 2 — Build the n8n relay workflow(s)

1. In the same n8n instance from Workflow 01, add a new workflow with a
   webhook trigger that accepts a generic event payload
   (`{event_type, user_id, incident_id, timestamp, metadata}` — adjust
   to match Signal API's real contract once you have it).
2. Inside that workflow, add an HTTP Request node that POSTs to the real
   Signal API endpoint with the correct auth (API key/header — confirm
   exact scheme from their docs) and payload shape.
3. **Do not add a second, separate call site in ANVAYA's backend for
   this.** The events chosen in Step 1 that already flow through
   `on_incident_event` (Rule 2a) should route to this n8n workflow as
   just another step inside that same function, using the already-live
   `N8NAdapter().trigger(...)` call from Workflow 01 Step 2c — pass a
   `workflow` parameter distinguishing this Signal-API-bound workflow
   from the Slack/notification-bound one built in Workflow 01. For the
   few events NOT already covered by `on_incident_event` (e.g. plain
   "incident opened" page views, or rule approval if that's not yet an
   `event_type` there), add them as new `event_type` values to the
   shared dispatch function rather than bypassing it with an inline
   `N8NAdapter()` call at the route handler — keep the one-dispatch-
   point discipline from Rule 2a intact.
4. Fire-and-forget / non-blocking: for high-frequency events like every
   incident view, consider whether a background task fits the existing
   patterns in `backend/anvaya/demo/orchestrator.py`'s `_run()`
   threading approach, rather than adding latency to every user-facing
   request.

## Step 3 — Launchpad account/lead/campaign creation

1. Confirm from Launchpad's actual docs what "creating an account,
   lead, or campaign" requires as a payload.
2. Pick the most natural ANVAYA trigger point — most likely: when a new
   project is created in ANVAYA (check `routers/projects.py`), fire an
   n8n workflow that creates a corresponding Launchpad account/lead.
   Project creation is not currently one of `on_incident_event`'s event
   types (that function is incident-scoped) — either add a small,
   separate `on_project_event` following the identical pattern from
   Rule 2a (one function, one dispatch point, gated by
   `is_n8n_enabled()`), or extend the existing dispatch function to a
   more general name if that's a cleaner fit once you see the real
   code — use judgment, but keep the "one shared dispatch point per
   entity type" discipline either way, don't scatter inline
   `N8NAdapter()` calls at the route handler.
3. Build this as a second n8n workflow (separate webhook) or a second
   node path in the existing one — whichever keeps the workflow
   readable; don't cram unrelated logic into one giant n8n workflow.

## Step 4 — Tests

- Add a test asserting the relevant backend call sites actually invoke
  `N8NAdapter().trigger(...)` with the expected `workflow` name and
  payload shape (mock the adapter itself here, not `httpx` — this is
  testing "does the app call the adapter correctly," which is a
  different concern from "does the adapter call n8n correctly," already
  covered in Workflow 01's tests).
- Do not add a test that requires the real Signal API / Launchpad
  endpoints to be reachable — mock at the n8n-webhook boundary.

## Step 5 — Report back (required, see Rule 7)

- Which specific ANVAYA events are now wired to Signal API, with exact
  file/line references for each call site added.
- Whether Launchpad wiring is live-verified (confirm a real
  account/lead/campaign actually appeared in Launchpad's system, not
  just that ANVAYA's side returned success) or blocked on missing
  API access/docs.
- Test command and result.
