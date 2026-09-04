# Workflow: Signal API tracking + Launchpad wiring

Goal: earn XP in the "Signal API" (track real user behavior) and
"Launchpad" (create accounts, leads, campaigns) categories by routing
ANVAYA's already-existing real events through n8n. This depends on
Workflow 01 being complete (n8n must be live first).

**Before starting: get the actual API/webhook contract for Startuped's
Signal API and Launchpad from the hackathon organizers or their docs.
Do not guess field names or auth scheme — a fabricated integration that
doesn't match their real contract earns zero XP and wastes the time
spent building it.**

## Step 1 — Inventory real ANVAYA events worth tracking

Read (don't re-derive from scratch) these existing event sources:
- `AuditRecord` creation points — every sealed incident, every rule
  validation, every replay already produces one of these
  (`backend/anvaya/models/audit.py`, and creation call sites across
  `backend/anvaya/sentinel/__init__.py`, `blastscope/__init__.py`,
  `whatif/__init__.py`).
- `/agent/executions/{id}/events` — the streaming execution event feed
  already exposed via SSE (`backend/anvaya/routers/agent.py`,
  `stream_execution_events`).
- Frontend page-view-equivalent actions: incident opened, rule
  approved/rejected (check `routers/rules.py` for the approval
  endpoint), project created (check `routers/projects.py` if present).

Pick 3–5 of these that map cleanly to "real user behavior" for the
Signal API — favor actions a human explicitly took (approving a rule,
opening an incident) over purely automated system events, since that's
closer to what "track real user behavior" likely means.

## Step 2 — Build the n8n relay workflow(s)

1. In the same n8n instance from Workflow 01, add a new workflow with a
   webhook trigger that accepts a generic event payload
   (`{event_type, user_id, incident_id, timestamp, metadata}` — adjust
   to match Signal API's real contract once you have it).
2. Inside that workflow, add an HTTP Request node that POSTs to the real
   Signal API endpoint with the correct auth (API key/header — confirm
   exact scheme from their docs) and payload shape.
3. In ANVAYA's backend, add calls to `N8NAdapter().trigger(...)` (reuse
   the existing adapter — do not write a second HTTP client) at each of
   the 3–5 event points chosen in Step 1. This is a small, additive
   change at each call site, not a new subsystem — look for the
   simplest insertion point (e.g. right after an `AuditRecord` is
   committed, or inside the rule-approval route handler) rather than
   restructuring existing flow.
4. Make this fire-and-forget / non-blocking where possible (the
   existing `trigger_automation` tool handler is already synchronous
   with a timeout — for high-frequency events like every incident view,
   consider whether a background task fits the existing patterns in
   `backend/anvaya/demo/orchestrator.py`'s `_run()` threading approach,
   rather than adding latency to every user-facing request).

## Step 3 — Launchpad account/lead/campaign creation

1. Confirm from Launchpad's actual docs what "creating an account,
   lead, or campaign" requires as a payload.
2. Pick the most natural ANVAYA trigger point — most likely: when a new
   project is created in ANVAYA (check `routers/projects.py`), fire an
   n8n workflow that creates a corresponding Launchpad account/lead. A
   secondary option: when a new incident is sealed, log it as a
   "campaign" data point if that maps to Launchpad's model — only do
   this if it genuinely fits their schema, don't force a mapping that
   doesn't make sense just to hit the category.
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
