# ANVAYA — Knowledge Master Index

> Living documentation of the ANVAYA autonomous cyber SOC. This index is the entry point for the `.anvaya/knowledge/` hierarchy. Update it whenever the architecture or important behavior changes.

## How to use this knowledge base

1. **New to ANVAYA?** Start with `01_SYSTEM_OVERVIEW.md`, then read `02_ARCHITECTURE.md` and `04_INTEGRATION_GRAPH.md`.
2. **Tracing a feature?** Go to `19_FEATURE_TRACES.md`.
3. **Debugging a failure?** Go to `20_FAILURE_MODES.md` and `21_THREAT_MODEL.md`.
4. **Changing code?** Read `01-` to `04-` first, then update the relevant section and `CHANGELOG.md`.
5. **Teaching the system?** Use `24_ACTIVE_RECALL.md` and the top-20 lists at the end of this file.

## File inventory

| # | File | Purpose | Status |
|---|------|---------|--------|
| 00 | `00_MASTER_INDEX.md` | This file — navigation, conventions, top-20 lists | ✅ |
| 01 | `01_SYSTEM_OVERVIEW.md` | One-sentence-to-5-minute explanation of ANVAYA | ✅ |
| 02 | `02_ARCHITECTURE.md` | Subsystems, layers, runtime topology, component diagram | ✅ |
| 03 | `03_RUNTIME_TOPOLOGY.md` | Processes, ports, Docker, environment, startup order | ✅ |
| 04 | `04_INTEGRATION_GRAPH.md` | Nodes, edges, data/events, security boundaries | ✅ |
| 05 | `05_DATA_FLOWS.md` | Major request/response and event flows | ✅ |
| 06 | `06_FRONTEND.md` | Next.js 15 app, components, state, hooks, UI data flow | ✅ |
| 07 | `07_BACKEND.md` | FastAPI, routers, services, engines, database access | ✅ |
| 08 | `08_CLI.md` | Interactive shell, Typer commands, watch, state, dispatch | ✅ |
| 09 | `09_ISOLATION_AND_EXECUTION.md` | Sandboxing, process boundaries, Docker, subprocess | ✅ |
| 10 | `10_ORCHESTRATION_AND_LOGISTICS.md` | Agent loop, planner, subagents, retries, queues | ✅ |
| 11 | `11_AI_AND_DETECTION.md` | Alertness/Isolation Forest, What-If/LR, Sentinel, features | ✅ |
| 12 | `12_INCIDENT_RESPONSE.md` | Incident lifecycle, self-correction, blast/what-if/replay | ✅ |
| 13 | `13_API_AND_EXTERNAL_INTEGRATIONS.md` | Tavily, n8n, Gmail, Lyzr, Swytchcode, model providers | ✅ |
| 14 | `14_SECURITY_MODEL.md` | Auth, audit hash chain, trust boundaries, secrets | ✅ |
| 15 | `15_CONFIGURATION.md` | Settings, env vars, feature flags, provider toggles | ✅ |
| 16 | `16_OBSERVABILITY.md` | Logging, structlog, metrics, events, tracing | ✅ |
| 17 | `17_DATABASE_AND_STATE.md` | SQLModel schema, migrations, key state machines | ✅ |
| 18 | `18_CRITICAL_FILE_DEEP_DIVES.md` | Tier-A line-by-line walkthroughs of critical modules | ✅ |
| 19 | `19_FEATURE_TRACES.md` | End-to-end traces of key user features | ✅ |
| 20 | `20_FAILURE_MODES.md` | Important failure paths and containment | ✅ |
| 21 | `21_THREAT_MODEL.md` | Attacker surface, injection, sandbox escape, audit fraud | ✅ |
| 22 | `22_TESTING_AND_VALIDATION.md` | Test structure, commands, verification practices | ✅ |
| 23 | `23_DEVELOPER_WORKFLOWS.md` | How to run, build, test, deploy | ✅ |
| 24 | `24_ACTIVE_RECALL.md` | Spaced-repetition question bank with source answers | ✅ |
| 25 | `25_UNKNOWN_QUESTIONS.md` | Questions still needing human/team verification | ✅ |
| — | `CHANGELOG.md` | Recent architecture/behavior changes | ✅ |

Legend: ✅ reasonably complete, 🟡 skeleton/needs expansion, 🔴 not started.

## Conventions used in this knowledge base

- **Source references** follow the format `<ref_file file="..." />` and `<ref_snippet file="..." lines="N-M" />` where possible. If a claim has no source, it is marked `UNKNOWN — NEEDS VERIFICATION`.
- **Importance scores** appear in file headers: `Architecture Impact`, `Integration Centrality`, `Security Criticality`, `Business Importance`, `Failure Impact`, `Learning Value`. Sum = `IMPORTANCE_SCORE` (0–35).
- **Mastery level** for each subsystem or file: M0 (unseen) → M5 (reconstructable from memory).
- **Truth over assumption:** every architectural claim is grounded in actual code, tests, or configuration. When uncertain, we say so.

## Quick source-of-truth map

| Source | Path | What it owns |
|--------|------|--------------|
| Engineering charter | `/home/de3p/Documents/Next.js/Anavaya/AGENTS.md` | Non-negotiable product + autonomy constraints |
| Devin master prompt | `/home/de3p/Documents/Next.js/Anavaya/DEVIN_MASTER_PROMPT.md` | Agentic execution requirements + provider fallback rules |
| Provider fallback matrix | `/home/de3p/Documents/Next.js/Anavaya/PROVIDER_FALLBACKS.md` | Truthful fallback behavior |
| Event contract | `/home/de3p/Documents/Next.js/Anavaya/AGENT_EXECUTION_EVENTS.md` | Event names/shapes for streaming + build |
| Design rules | `/home/de3p/Documents/Next.js/Anavaya/.devin/rules/newRules.md` | Claude-minimal UI tokens |
| Agent rules | `/home/de3p/Documents/Next.js/Anavaya/.devin/rules/agents.md` | Agent/orchestration constraints |
| XP rules | `/home/de3p/Documents/Next.js/Anavaya/.devin/rules/rules.md` | Integration + testing requirements |
| Frontend build | `/home/de3p/Documents/Next.js/Anavaya/frontend/package.json` | Next.js 15.5.23, React 19, Tailwind 4, React Query 5 |
| Backend build | `/home/de3p/Documents/Next.js/Anavaya/pyproject.toml` | FastAPI + SQLModel + scikit-learn + providers |
| Runtime topology | `/home/de3p/Documents/Next.js/Anavaya/docker-compose.yml` | Postgres 15, backend 8000, frontend 3000 |

## Top-20 quick-reference lists

### Top 20 important files

1. `backend/anvaya/main.py` — FastAPI app, router mount, middleware, lifespan.
2. `backend/anvaya/config.py` — all environment settings and provider toggles.
3. `backend/anvaya/db.py` — engine, session, `init_db()`.
4. `backend/anvaya/live/__init__.py` — `score_and_maybe_flag`, real-time detection entry.
5. `backend/anvaya/live/dispatch.py` — single dispatch point for Tavily/n8n/Gmail/Signal.
6. `backend/anvaya/agent/orchestrator.py` — `AgentOrchestrator.start/run`.
7. `backend/anvaya/agent/agent_loop.py` — `run_investigation`, `run_project_plan`, `run_adaptive`.
8. `backend/anvaya/agent/executor.py` — `LocalToolExecutor`, all tool handlers.
9. `backend/anvaya/agent/registry.py` — `ToolRegistry`, `default_tool_registry()`.
10. `backend/anvaya/agent/events.py` — `EventStore`, execution event persistence.
11. `backend/anvaya/agent/adapters.py` — Tavily, n8n, Gmail, Lyzr, Swytchcode adapters.
12. `backend/anvaya/models/incident.py` — `Incident`, lifecycle + self-correction transitions.
13. `backend/anvaya/models/audit.py` — `AuditRecord`, hash-chain integrity.
14. `backend/anvaya/models/telemetry.py` — `TelemetryEvent` schema.
15. `ml/anvaya/alertness/__init__.py` — `AlertnessEngine` (Isolation Forest).
16. `backend/anvaya/sentinel/__init__.py` — `SentinelEngine` backtracking + self-correction.
17. `backend/anvaya/blastscope/__init__.py` — `BlastScopeEngine` NetworkX blast radius.
18. `backend/anvaya/whatif/__init__.py` — `WhatIfEngine` logistic regression counterfactuals.
19. `frontend/lib/api.ts` — all frontend→backend API calls and React Query hooks.
20. `backend/anvaya/cli/shell.py` — interactive CLI slash command dispatcher.

### Top 20 important symbols

1. `FastAPI` app in `main.py`
2. `Settings` in `config.py`
3. `get_session` / `get_session_sync` in `db.py`
4. `score_and_maybe_flag` in `live/__init__.py`
5. `on_incident_event` in `live/dispatch.py`
6. `AgentOrchestrator.start` / `.run`
7. `AgentLoop.run_investigation` / `.run_project_plan`
8. `LocalToolExecutor.execute`
9. `default_tool_registry`
10. `EventStore.emit` / `create_execution`
11. `TavilyAdapter.search` / `N8NAdapter.trigger` / `GmailAdapter.send`
12. `Incident.transition_to` / `self_correct_to`
13. `AuditRecord.compute_hash` / `verify_chain`
14. `TelemetryEvent` model
15. `AlertnessEngine.train` / `predict_single`
16. `SentinelEngine.backtrack` / `propose_rule` / `validate_rule` / `replay_attack`
17. `BlastScopeEngine.run`
18. `WhatIfEngine.analyze`
19. `AnvayaAPI` in `frontend/lib/api.ts`
20. `InteractiveShell.run` / `_handle`

### Top 20 integrations

1. Frontend ↔ Backend via `apiFetch` (React Query + SSE).
2. Backend ↔ SQLite/PostgreSQL via SQLModel/SQLAlchemy.
3. `POST /telemetry` → `score_and_maybe_flag` → live detection.
4. `anvaya watch` CLI → `score_and_maybe_flag`.
5. Live detection → `on_incident_event` → Tavily/n8n/Signal/Gmail.
6. `POST /projects` → `on_project_created` → n8n Launchpad.
7. Agent console `/agent/execute` → `AgentOrchestrator` → tool registry.
8. `LocalToolExecutor` → `SentinelEngine` / `BlastScopeEngine` / `WhatIfEngine`.
9. `manage_artifacts` → `ArtifactBuilder` → `ProjectArtifactPayload`.
10. `ArtifactBuilder` → `EventStore` → SSE `/agent/executions/{id}/stream`.
11. `TavilyAdapter` → `https://api.tavily.com/search`.
12. `N8NAdapter` → `settings.n8n_webhook_url`.
13. `GmailAdapter` → Gmail API service account.
14. `LyzrAdapter` → `api.lyzr.com/v2/llm/chat/completions`.
15. `SwytchcodeAdapter` (currently hard-disabled via `healthy()=False`).
16. LLM providers: OpenAI, NVIDIA, OpenRouter, OpenCode, SeekAI, GMI Cloud, Empero, AgentRouter.
17. Better Auth → `app/api/auth/[...all]/route.ts`.
18. Docker Compose: Postgres, backend, frontend.
19. `uvicorn` serving FastAPI, `next dev` for frontend.
20. `pytest` test suite across `tests/`.

### Top 20 concepts

1. Unified incident lifecycle: `detected → analyzed → simulated → explained → sealed`.
2. Self-correction status machine: `none → miss → ground_truth_confirmed → ... → caught/still_missed`.
3. Alertness = Isolation Forest anomaly detection.
4. SentinelBacktracker = rule proposal + validation + replay catch.
5. BlastScope = NetworkX graph blast-radius traversal.
6. What-If Watcher = Logistic Regression counterfactuals.
7. ControlLedger = hash-chained audit records.
8. Tool registry with provider/fallback attribution.
9. Event streaming via SSE and React Query polling.
10. Artifact generation with staged `generation.*` / `artifact.*` / `element.*` events.
11. Provider-neutral adapters with honest fallback.
12. Shared dispatch point for live and demo events.
13. `TelemetryEvent` feature extraction (12 columns).
14. Synthetic deterministic scenario generation.
15. Train/validation/test/replay split with reproducible seed.
16. `anvaya watch` real-time log tailing and scoring.
17. Interactive slash-command CLI (`/investigate`, `/train`, `/replay`).
18. Profile-driven agent (`sentinel`, `pathfinder`, `responder`, `auditor`).
19. Subagent spawning with parent/child execution tracking.
20. Truthful provider status; never fabricate live results.

### Top 20 failure modes

1. No trained `Alertness` model → live scoring returns `scored: False`.
2. `predict_single` throws → scoring returns failure reason but no incident.
3. Invalid lifecycle transition → `ValueError` from `Incident.transition_to`.
4. Missing provider credentials → fallback with `fallback_used=True`.
5. Tavily/n8n/Gmail request exception → local fixture/handler recorded.
6. Agent loop step failure → optional steps continue, required steps fail execution.
7. `manage_artifacts` step fails → `stop_on_failure` aborts the project build.
8. Subagent failure/cancellation → parent event emitted, child execution recorded.
9. Audit chain break → `verify_chain` returns `False`.
10. Database lock (SQLite WAL) → retry or use Postgres.
11. Frontend SSE disconnect → React Query polling resumes.
12. Better Auth secret missing → auth endpoints may fail.
13. CORS misconfiguration → frontend cannot reach backend.
14. `FEATURE_COLUMNS` mismatch during inference → model error.
15. Rule validation fails → incident stays in `RULE_PROPOSED`.
16. Replay still misses → `STILL_MISSED` status and backtracking continues.
17. `BlastScopeEngine` cannot find origin host → synthetic `ORIGIN-` node created.
18. `ArtifactBuilder` element selector fails → step retry/fail.
19. Model provider timeout → fallback to local deterministic planner.
20. User cancels execution → `ExecutionContext.status = cancelled`, loop exits.

### Top 20 security concerns

1. Secrets in environment variables only (`OPENAI_API_KEY`, `TAVILY_API_KEY`, etc.).
2. Never send API keys to the frontend; `AnvayaAPI` calls backend, which holds keys.
3. `Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options` headers.
4. CORS allow-list must not accidentally include untrusted origins in production.
5. Better Auth HMAC-SHA256 token validation.
6. Audit hash chain prevents tampering (SHA-256 with previous-hash linking).
7. Agent tool allowlist prevents arbitrary code execution.
8. `requires_confirmation` gates high-risk tools (`seal_incident`, `trigger_automation`).
9. Tool input schema validation before execution.
10. Subprocess in CLI `_do_shell` runs with user privileges — no sandbox.
11. No network isolation between backend and DB in local Docker.
12. Synthetic attacks only — no real-world offensive automation.
13. `uploadthing_secret` not exposed to frontend.
14. LLM outputs are validated against schemas, not executed directly.
15. `rehype-sanitize` sanitizes rendered markdown.
16. `AgentExecutionEvents` filter out hidden chain-of-thought.
17. `gmail_credentials_path` points to service-account JSON — file permissions matter.
18. n8n webhook URL is a secret configuration; UI does not receive it.
19. `score_and_maybe_flag` can create incidents from any `POST /telemetry` — rate limit in production.
20. Model provider endpoints are public; `empero` is a public community endpoint with privacy warning.

### Top 30 active-recall questions

(See full question bank in `24_ACTIVE_RECALL.md`)

1. What is the unified incident lifecycle and where is it enforced?
2. What calls `score_and_maybe_flag` and what does it do when `detected=True`?
3. Which single function dispatches Tavily, n8n, Signal, and Gmail events?
4. How is the audit chain integrity verified?
5. What are the 12 `FEATURE_COLUMNS` and where are they defined?
6. What happens if no `Alertness` model is trained when `POST /telemetry` fires?
7. What is the difference between `Incident.status` and `Incident.self_correction_status`?
8. Which class executes every agent tool locally?
9. What is the fallback rule for `TavilyAdapter` when `TAVILY_API_KEY` is missing?
10. How does the frontend receive live agent events? (SSE + React Query)
11. What is `ARTIFACT_TYPES` and what does `manage_artifacts` do with it?
12. What is the shared dispatch point for project creation → Launchpad?
13. What are the two CLI entry modes and how are they chosen?
14. What does `BlastScopeEngine.run` do when the origin host is not in the asset graph?
15. How does `SentinelEngine` propose a rule from backtracked evidence?
16. What is the `ControlLedger` and what makes it tamper-evident?
17. What is the provider selection algorithm for external integrations?
18. What is the role of `AgentLoop.run_project_plan` vs `run_investigation`?
19. How are artifact build events streamed to the frontend?
20. What is the `anvaya watch` command and what are its two source modes?
21. What is the `WorldObserver` / `DecisionEngine` used for?
22. What is the `LocalToolExecutor._next_sequence` for?
23. How are tool inputs validated?
24. What is the difference between `generation.started` and `artifact.queued`?
25. Which models are trained by the `/train` CLI path?
26. What is the `EVENT_TYPE_CODES` mapping used for?
27. How is the `BlastScope` impact score computed?
28. What happens when `SwytchcodeAdapter.healthy()` is called?
29. How is provider status surfaced in the frontend?
30. What is the judge-observable proof lifecycle ANVAYA is optimized for?

## Active recall schedule

For each major concept, revisit:
- First recall: ~20 minutes after first exposure.
- Recall #2: ~1–2 hours later.
- Recall #3: ~4–6 hours later.
- Final recall: near end of a work session.

Use `24_ACTIVE_RECALL.md` as the source-backed answer key; test yourself before checking.

## Change protocol

Before any non-trivial change:
1. Identify affected files using this index.
2. Read the relevant subsystem doc (`06-` through `17-`).
3. Update `CHANGELOG.md` with what changed and why.
4. Update `24_ACTIVE_RECALL.md` if the mental model changed.
5. Add new source references; remove stale ones.

## Unknowns requiring human verification

(See `25_UNKNOWN_QUESTIONS.md` for the full list.)

- Is there a production Postgres migration path beyond `migrations.py`?
- What is the exact Launchpad/Signal API contract for n8n workflows?
- Are UI reference images in `.devin/references/ui` still the latest authority?
- Has the `docker-compose.yml` been used in a judge demo recently?
