---
trigger: always_on
---
# ANVAYA — Integration & XP Rules

These rules apply to ALL work in this repo related to Startuped XP
scoring (Launchpad, Signal API, third-party integrations, developer
work — SDKs, Claude Skills, MCP). Read this before starting any task
tagged with an XP category.

## 0. Context — why this file exists

The hackathon scores XP by tier (2,000+ / 1,000+ / 500+ XP → cash
tiers). XP comes from: (1) Launchpad usage — accounts, leads,
campaigns; (2) Signal API — tracking real user behavior; (3)
integrations — Gmail, LinkedIn, Instagram, X; (4) developer work —
SDKs, Claude Skills, MCP. Every task you pick up should be traceable to
one of these four categories, and you should say which one in your
summary when you finish a task.

**Priority principle: real, working, demoable integrations beat a
larger number of half-finished ones.** A judge or scoring system that
can call an endpoint and see it actually hit a third-party API is worth
more than five endpoints that silently no-op. Follow the existing
codebase's own convention for this — see Rule 2.

## 1. Ground truth — what already exists, verified by reading the code

Do not re-derive this by searching the repo again; it is correct as of
this file being written. If you find it's changed, trust the code over
this file and update this file to match.

- **Tavily**: `backend/anvaya/agent/adapters.py::TavilyAdapter` is a
  REAL, WORKING adapter. It POSTs to `https://api.tavily.com/search`
  when `settings.tavily_api_key` is set, and returns a clearly-labeled
  local fixture (`source: "anvaya-local-fixture"`) when not. It's
  already wired as the `threat_intelligence_lookup` tool in
  `backend/anvaya/agent/registry.py` (line ~802) and called from
  `backend/anvaya/agent/executor.py::handle_threat_intelligence_lookup`
  (line ~1777). **This one just needs a real API key in `.env` to go
  from fallback-mode to live — do this first, it's the cheapest XP in
  the repo.**
- **n8n**: `N8NAdapter` in the same file is REAL and WORKING. It POSTs
  to `settings.n8n_webhook_url` when set, with an honest local-record
  fallback (writes an `AuditRecord` instead of no-op-ing silently) when
  not. Wired as the `trigger_automation` tool, same registry/executor
  files, called from `handle_trigger_automation` (line ~1826). **Also
  just needs `N8N_WEBHOOK_URL` set to a real n8n instance/webhook to go
  live.**
- **Lyzr**: `LyzrAdapter` EXISTS but is DELIBERATELY STUBBED —
  `healthy()` hardcoded to `return False` with a comment
  `# Lyzr integration is stubbed; truthful unavailable.` (line ~201).
  Nothing calls a real Lyzr API anywhere. This is real, unstarted build
  work, not a config flip.
- **Gmail, LinkedIn, Instagram, X**: zero references anywhere in the
  backend. Clean slate — no existing adapter, no config key, no
  registry entry.
- **MCP / Claude Skills**: zero references anywhere in the backend.
  Clean slate.
- **Config keys already present** in `backend/anvaya/config.py`:
  `tavily_api_key`, `n8n_webhook_url`, plus the pattern
  `is_<provider>_enabled()` methods (e.g. `is_tavily_enabled`,
  `is_n8n_enabled`, `is_swytchcode_enabled`). **Follow this exact
  naming pattern for any new provider** (`lyzr_api_key` already
  exists as a settings field per the adapter's `env_var = "LYZR_API_KEY"`
  — verify this before adding a duplicate).
- **Live event bus (built by Workflow 00, referenced by every workflow
  after it)**: once Workflow 00 lands, real-time detections are no
  longer only produced by the scripted demo orchestrator. They also
  come from `score_and_maybe_flag()` (new module, `backend/anvaya/live/`
  per Workflow 00) firing on every `POST /telemetry` call and from the
  `anvaya watch` CLI command feeding that same endpoint. **Every
  workflow from 01 onward must hang its trigger points off this live
  path, not off the old demo-orchestrator-only trigger points.**
  Concretely: "when an incident is created/sealed" now means "any
  incident, however it was created — live-detected or demo-scripted,"
  and the correct place to hook a side effect (Tavily lookup, n8n
  Signal API push, Gmail notify, etc.) is a single shared dispatch
  point that fires regardless of source — see Rule 2a below.

## 2. The adapter pattern — copy it exactly for every new integration

Every provider integration in this repo follows the same shape. When
adding Gmail/LinkedIn/Instagram/X, or completing Lyzr, follow this
pattern precisely — do not invent a different structure:

1. A `ProviderAdapter` subclass in `backend/anvaya/agent/adapters.py`
   with: `name`, `env_var`, `fallback_reason` class attributes;
   `configured()` (checks the relevant settings field is non-empty);
   `healthy()` (usually same as `configured()` unless a cheap live
   health check is worth the latency); and the actual capability method
   (`search`, `trigger`, `send`, etc.) that makes the real HTTP call
   wrapped in try/except, returning a dict with `source`/`provider` set
   to the real provider name on success, and a CLEARLY LABELED fallback
   dict (`source: "anvaya-local-fixture"` or `"anvaya-local-handler"`)
   on failure or when not configured. **Never let a fallback silently
   claim to be the real provider** — this is a hard rule the existing
   code already follows (see `TavilyAdapter.search`'s except block) and
   must not be violated, since a judge/demo that catches a fake "live"
   result as fabricated is worse than not having the integration.
2. A settings field in `config.py` (`<provider>_api_key` or
   `<provider>_webhook_url`) plus an `is_<provider>_enabled()` method.
3. A `ToolDefinition` registered in
   `backend/anvaya/agent/registry.py` — copy the shape of the
   `threat_intelligence_lookup` or `trigger_automation` entries
   (lines ~802–858) exactly: `name`, `description`, `category`,
   `parameters` (list of `ToolParameter`), `risk_level`, `provider`,
   `fallback_provider="anvaya"`, `requires_confirmation` (true for
   anything that sends/posts/creates externally), `idempotent`.
4. A handler method in
   `backend/anvaya/agent/executor.py` following the exact shape of
   `handle_threat_intelligence_lookup` / `handle_trigger_automation`
   (lines ~1777–1860+): instantiate the adapter, check `.healthy()`,
   call the real method on success, fall through to a labeled local
   fixture/handler on failure, return a `ToolResult` with
   `fallback_used` and `fallback_reason` set honestly.
5. A test in `tests/` (see Rule 3) that exercises both the
   configured-and-mocked-success path and the not-configured-fallback
   path, mirroring whatever test file already covers Tavily/n8n if one
   exists — search `tests/` for `tavily` or `n8n` (case-insensitive)
   before writing a new test file, to avoid duplicating fixtures/mocks
   that already exist.

## 2a. One shared dispatch point — required once Workflow 00 exists

Do not let each downstream integration (Tavily, n8n/Signal-API,
Launchpad, Gmail, Lyzr) independently hook into `score_and_maybe_flag()`
or the demo orchestrator separately — that produces N slightly-different
trigger implementations that drift out of sync. Instead:

1. Build ONE function, e.g. `on_incident_event(incident, event_type,
   session)` in `backend/anvaya/live/dispatch.py`, where `event_type`
   is one of a small enum: `DETECTED` (live catch), `SEALED`,
   `RULE_APPROVED`, etc. — reuse `IncidentStatus`-adjacent naming
   already in the codebase rather than inventing new terms.
2. Call this function from exactly two places: (a) the end of
   `score_and_maybe_flag()` in Workflow 00, with `event_type=DETECTED`;
   (b) wherever the existing demo orchestrator / rule-approval / seal
   logic already transitions incident state, with the matching
   `event_type`. This means live-detected AND demo-scripted incidents
   both flow through the same downstream integrations automatically.
3. Every workflow below (Tavily enrichment, n8n Signal API push, Gmail
   notify, etc.) registers itself as a step inside `on_incident_event`,
   gated by `event_type` and by its own `is_<provider>_enabled()` check
   — not as a separate call scattered at the original trigger site.
   This keeps one auditable place that shows exactly what fires on
   what, which is also good for the "audit ledger" story ANVAYA already
   tells.

## 3. Testing requirements — non-negotiable for XP credibility

- Every new adapter or tool handler needs at least one passing test
  before it counts as "done." An integration nobody can prove works is
  not worth XP — it's a liability if a judge asks you to demonstrate it
  live and it silently fails.
- Use `pytest`, SQLite (`DATABASE_URL=sqlite://`), and mock the actual
  HTTP call (`httpx` — see how existing tests likely mock `httpx.post`
  for n8n/Tavily; search `tests/` first) rather than hitting a real
  external API in CI. Live-API smoke tests are fine as a SEPARATE,
  explicitly-marked test (`@pytest.mark.live` or similar) that's not
  part of the default `pytest tests/` run, so the suite stays fast and
  doesn't require live credentials to pass.
- Before marking any integration task complete, run:
  `pytest tests/ -q --no-header` and confirm you haven't broken the
  existing 285-passing baseline (14 known-unrelated failures in LLM
  catalog metadata and CLI shell tests are pre-existing and not your
  concern unless a task specifically targets them).

## 4. Frontend wiring — integrations need to be SEEN, not just callable

An integration that only exists as a backend tool call is invisible to
a judge unless they inspect API traffic. For XP purposes, prefer adding
a visible frontend surface for any new integration:

- Check `lib/api.ts` in the frontend repo for the existing fetch-helper
  pattern (e.g. `demo: () => apiFetch("/demo/run", ...)`) and add a
  matching helper for any new endpoint.
- Reuse the Agent Console (`components/agent-console.tsx` if present)
  or add a small dedicated panel — do not build a whole new page unless
  the integration is substantial enough to warrant one (e.g. a
  dedicated `/threat-intel` view for Tavily results might be worth it;
  a single Gmail-send action probably fits inside an existing incident
  detail view instead).
- Follow the visual system already defined in this repo's design rules
  doc (`docs/newRules.md` if present, or the Claude-minimal palette
  discussed elsewhere in this project) — do not introduce a new visual
  style for integration UI.

## 5. Environment / secrets handling

- Add every new provider's env var to a `.env.example` file at the repo
  root (create one if it doesn't exist) with a placeholder value and a
  one-line comment on where to get a real key. This is required for
  Launchpad/XP scoring reviewers to know what to configure — an
  integration with no documented env var is effectively undiscoverable.
- Never commit a real API key, webhook URL, or secret to the repo,
  including in test fixtures, `.env` (as opposed to `.env.example`), or
  example payloads in documentation.
- If a task requires a real credential you don't have (e.g. a Gmail
  OAuth client secret, a Lyzr API key), stop and flag it rather than
  fabricating a placeholder that looks real — say explicitly in your
  summary what credential is needed and where a human needs to supply
  it.

## 6. Priority order — do these in this order unless told otherwise

**0. Live scoring + real-time log watcher (see `.devin/workflows/00-
live-scoring-and-watch-cli.md`) — do this FIRST, before any XP-category
work below.** This isn't an XP-category task; it's a correctness fix.
The product pitch claims ANVAYA "watches activity and flags new attacks
and intruders as they happen." Verified against the code, this is
currently NOT TRUE — `AlertnessEngine.predict()`/`.predict_single()`
are fully implemented but never called against live/incoming telemetry
anywhere in the codebase (confirmed by direct search across every
router, the CLI, and the demo orchestrator). Every MISS/CAUGHT decision
today comes from a hardcoded rule check, not the trained model. Fix
this before doing anything else in this file, because every task below
assumes the product's core claim is true, and a judge or the XP system
probing "show me it catching something you didn't script" will surface
this gap immediately otherwise.

Highest XP-per-hour first among the remaining categories, per the
ground truth in Rule 1:

1. **Activate Tavily for real** (add real API key to `.env`, verify a
   live call succeeds, confirm the frontend surfaces it) — smallest
   possible task, immediate proof of a working live integration.
2. **Activate n8n for real** (stand up or point to a real n8n instance/
   webhook, build one simple workflow, verify `trigger_automation`
   actually fires it) — same reasoning.
3. **Signal API wiring via n8n** — route real ANVAYA events (incident
   viewed, rule approved, replay run, incident sealed) through n8n to
   Startuped's Signal API. This is probably the single highest-value
   task for the "Signal API" XP category since ANVAYA already emits
   these events (see `AuditRecord` creation points and
   `/agent/executions/{id}/events` streaming) — the work is routing,
   not inventing new signal.
4. **Launchpad wiring** — likely also via an n8n workflow triggered on
   project creation (`POST /projects` or wherever that lives in
   `backend/anvaya/routers/`) to create a Launchpad account/lead/
   campaign record. Confirm Launchpad's actual API/webhook contract
   before building — do not guess its request shape.
5. **One new social/email integration** (Gmail is likely lowest-friction
   via a service account or OAuth; LinkedIn/Instagram/X typically have
   stricter app-review requirements — confirm which is actually
   feasible to stand up before committing time to it).
6. **Complete the Lyzr stub** — real build work, do this once the above
   is solid, per the priority reasoning already established for this
   project (config-flip integrations first, net-new build work after).
7. **MCP / Claude Skills / SDK work** — see `.devin/workflows/` for a
   dedicated workflow on this; it's structurally different from the
   provider-adapter pattern above (it's about exposing ANVAYA's own
   tools to external agents, not consuming a third party).

## 7. Reporting back — required for every task

At the end of every task in this category, state explicitly:
- Which XP category it counts toward (Launchpad / Signal API /
  integration / developer work).
- Whether the integration is LIVE (real API key configured, real call
  succeeding) or FALLBACK-ONLY (code complete, but no credential
  configured yet — needs a human to supply one before it's demoable).
- The exact test command run and its pass/fail result.
- Any credential or external account still needed from a human before
  this can go live.

Do not report a task as "done" if it's fallback-only without saying so
explicitly — an XP reviewer or judge testing this live will find out
immediately, and an honest "needs a credential" status is worth more
trust than an overstated "done."
