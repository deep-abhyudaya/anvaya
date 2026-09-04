# Workflow: Activate Tavily + n8n (fastest available XP)

Goal: turn the two already-built, currently-fallback-only integrations
into live, provably-working ones, AND wire both to fire automatically
off the live event stream from Workflow 00 — not just via a manual
`POST /agent/execute` call. Both adapters exist and are correct — see
`.devin/rules.md` Rule 1 for exact file/line references. This workflow
does NOT rewrite adapter logic; it activates what's there, proves it
works standalone, then wires it into the shared dispatch point.

**Depends on Workflow 00 being complete** (specifically the
`on_incident_event` dispatch point from Rule 2a) before Step 1c/2c
below — the standalone activation (1a/1b, 2a/2b) can be done in
parallel with Workflow 00 if needed, but the live-wiring steps cannot.

## Step 1 — Tavily

1a. Obtain a real Tavily API key (https://tavily.com — human on the
   team must sign up and provide the key; do not fabricate one).
1b. Create `.env` at the repo root if it doesn't exist (copy from
   `.env.example` if you create that in this same task per Rule 5), and
   set `TAVILY_API_KEY=<real key>`. Start the backend, call
   `POST /agent/execute` for `threat_intelligence_lookup` manually with
   a real-looking indicator, and confirm the response has
   `"provider": "tavily"` and `"fallback_used": false` — NOT
   `"anvaya-local-fixture"`. If you get the fixture response, check
   `TavilyAdapter.search`'s except block logs
   (`logger.warning("tavily.search_failed", ...)`) before assuming it's
   a code bug — it's most likely a bad/missing key.
1c. **Wire it to fire automatically on live detections.** Inside
   `on_incident_event` (Rule 2a), on `event_type=DETECTED`, call
   `TavilyAdapter().search(...)` using the incident's `attack_family`
   or a derived indicator as the query, and attach the result to the
   incident (new field, or a related `IncidentEnrichment` record —
   check whether a suitable existing table/relationship exists on
   `Incident` before adding a new model). This means: the moment the
   `anvaya watch` CLI (Workflow 00) flags something live, a real Tavily
   lookup fires automatically, with no manual API call needed — this is
   the actual demoable moment, not the manual curl from step 1b.
1d. Test: mock `httpx.post` for the standalone adapter test (as before),
   PLUS a new test asserting that triggering `on_incident_event` with
   `event_type=DETECTED` results in exactly one Tavily call (mock the
   adapter at this level, don't re-mock httpx here — different layer).
1e. Frontend: confirm `lib/api.ts` has (or add) a helper surfacing the
   attached enrichment data on the incident detail view, so the live
   Tavily result is visibly rendered without a manual refresh.

## Step 2 — n8n

2a. Stand up a real n8n instance (n8n Cloud free tier, or self-hosted —
   whichever the team already has access to; ask if unclear) with one
   simple workflow: a webhook trigger node that does something visibly
   real (e.g. posts to a Slack/Discord channel, or logs to a Google
   Sheet row).
2b. Copy that workflow's webhook URL into `.env` as
   `N8N_WEBHOOK_URL=<real webhook URL>`. Call `POST /agent/execute` for
   `trigger_automation` manually with a real `incident_id` and confirm
   `"status": "triggered"`, `"provider": "n8n"`,
   `"fallback_used": false` — and confirm independently in the n8n
   dashboard's execution log that it actually ran, not just that ANVAYA
   returned success.
2c. **Wire it to fire automatically on live detections**, same pattern
   as 1c: inside `on_incident_event`, on `event_type=DETECTED` (and
   separately on `event_type=SEALED`, since that's the more natural
   "notify the team, this is fully resolved and audited" moment), call
   `N8NAdapter().trigger(...)`. This is also the natural home for the
   Signal API push described in Workflow 02 — see that file for the
   payload shape once Startuped's real contract is known; both can be
   separate steps inside the same `on_incident_event` function, gated
   by their own `is_n8n_enabled()`/config checks.
2d. Test: standalone adapter test (mock `httpx.post`, both success and
   fallback-writes-AuditRecord paths, as before), PLUS a test asserting
   `on_incident_event(..., event_type=DETECTED)` triggers exactly one
   n8n call with the expected payload shape.

## Step 3 — Report back (required, see Rule 7)

State explicitly for each of Tavily and n8n:
- Live and verified standalone (manual call), AND live and verified via
  the automatic dispatch path (trigger a real detection via
  `anvaya watch --source synthetic` and confirm both fire without any
  manual API call) — or blocked on a credential/account (name exactly
  what's missing).
- The test command run and result.
- A link/screenshot-equivalent description of the independent proof
  (n8n execution log entry, actual Tavily result content attached to a
  real incident) — not just "the endpoint returned 200."
