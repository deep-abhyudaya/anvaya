# Workflow: Activate Tavily + n8n (fastest available XP)

Goal: turn the two already-built, currently-fallback-only integrations
into live, provably-working ones. Both adapters exist and are correct —
see `.devin/rules.md` Rule 1 for exact file/line references. This
workflow does NOT rewrite any adapter logic; it activates what's there
and proves it works.

## Step 1 — Tavily

1. Obtain a real Tavily API key (https://tavily.com — human on the team
   must sign up and provide the key; do not fabricate one).
2. Create `.env` at the repo root if it doesn't exist (copy from
   `.env.example` if you create that in this same task per Rule 5), and
   set `TAVILY_API_KEY=<real key>`.
3. Start the backend locally
   (`uvicorn anvaya.main:app` or the repo's documented run command —
   check `backend/anvaya/main.py` / any `Makefile`/`justfile` for the
   canonical command before guessing at one).
4. Call `POST /agent/execute` with a tool invocation for
   `threat_intelligence_lookup` and a real-looking indicator (e.g. an
   attack technique name already used in
   `simulator/anvaya/scenarios.py`'s `ATK-MISS-001` scenario, like
   `"lateral_movement"` or `"ssh_scp_exfiltration"`).
5. Confirm the response has `"provider": "tavily"` and
   `"fallback_used": false` — NOT `"anvaya-local-fixture"`. If you get
   the fixture response, the key isn't being picked up or the request
   is failing; check `TavilyAdapter.search`'s except block logs
   (`logger.warning("tavily.search_failed", ...)`) for the real error
   before assuming it's a code bug — it's most likely a bad/missing key.
6. Add a corresponding test in `tests/` (search existing test files for
   `tavily` first to see if a mocked-success-path test already exists;
   if so extend it, if not add one) that mocks `httpx.post` to return a
   realistic Tavily response shape and asserts the adapter parses it
   correctly. This test must NOT require a real network call or a real
   key — mock it.
7. In the frontend, confirm `lib/api.ts` has (or add) a helper that
   calls the agent-execute endpoint for this tool, and confirm the
   relevant UI (Agent Console, or a dedicated threat-intel surface per
   Rule 4) actually renders the live result, not a hardcoded example.

## Step 2 — n8n

1. Stand up a real n8n instance (n8n Cloud free tier, or self-hosted —
   whichever the team already has access to; do not guess, ask if
   unclear) with one simple workflow: a webhook trigger node that does
   something visibly real (e.g. posts to a Slack/Discord channel, or
   just logs to a Google Sheet row) so there's something demoable at
   the other end, not just a 200 OK.
2. Copy that workflow's webhook URL into `.env` as
   `N8N_WEBHOOK_URL=<real webhook URL>`.
3. Call `POST /agent/execute` for the `trigger_automation` tool with a
   real `incident_id` (use one from a demo run — see
   `backend/anvaya/demo/orchestrator.py`) and a `workflow` name matching
   what the n8n workflow expects.
4. Confirm the response has `"status": "triggered"`,
   `"provider": "n8n"`, `"fallback_used": false` — and confirm
   independently (in the n8n dashboard's execution log, or the
   Slack/Sheet it posts to) that the workflow actually ran. Do not
   trust the ANVAYA-side response alone as proof.
5. Add/extend a test in `tests/` mocking `httpx.post` for the n8n
   trigger call, asserting both the success path and the
   not-configured/failed fallback path (the fallback should write a
   real `AuditRecord` — assert that happens too, since that's existing,
   tested-adjacent behavior worth protecting from regression).

## Step 3 — Report back (required, see Rule 7)

State explicitly for each of Tavily and n8n:
- Live and verified, or blocked on a credential/account a human must
  supply (name exactly what's missing).
- The test command run and result.
- A link/screenshot-equivalent description of the independent proof
  (n8n execution log entry, actual Tavily result content) — not just
  "the endpoint returned 200."
