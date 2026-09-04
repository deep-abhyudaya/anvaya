# ANVAYA — API and External Integrations

## Integration inventory

| Integration | Purpose | Config | Provider adapter | Dispatch trigger | Status |
|-------------|---------|--------|------------------|------------------|--------|
| **Tavily** | Threat intelligence search | `TAVILY_API_KEY` | `TavilyAdapter` | `on_incident_event(DETECTED)` | working with fallback |
| **n8n** | Workflow automation | `N8N_WEBHOOK_URL` | `N8NAdapter` | `on_incident_event(DETECTED/SEALED)`, `on_project_created` | working with fallback |
| **Gmail** | Email notifications | `GMAIL_CREDENTIALS_PATH`, `GMAIL_FROM_EMAIL` | `GmailAdapter` | `on_incident_event(SEALED)` | working with fallback |
| **Signal API** | Startuped Signal events | `N8N_WEBHOOK_URL` | `N8NAdapter` (workflow `signal`) | `on_incident_event(*)` | REST/MCP contract verified; n8n live delivery unverified |
| **Launchpad** | Startuped Launchpad account/lead | `N8N_WEBHOOK_URL` | `N8NAdapter` (workflow `launchpad_account`) | `on_project_created` | product APIs verified; n8n live delivery unverified |
| **Lyzr** | Agent/rule proposal | `LYZR_API_KEY` | `LyzrAdapter` | `lyzr_propose_rule` tool | stubbed, fallback available |
| **Swytchcode** | External tool execution | `SWYTCHCODE_API_KEY`, `SWYTCHCODE_BASE_URL` | `SwytchcodeAdapter` | tool dispatch | currently `healthy()=False` |
| **OpenAI** | LLM chat/completions | `OPENAI_API_KEY` | via `llm/providers.py` | planner/chat | working if key set |
| **NVIDIA/OpenRouter/etc.** | LLM gateways | provider API keys | via `llm/providers.py` | planner/chat | working if key set |
| **Startuped MCP** | CRM and XP actions | `.devin/mcp_config.json`, gitignored `.devin/mcp_config.local.json` | Devin CLI MCP client via `mcp-remote` | explicit tool calls / `startuped-xp` skill | live and verified |
| **Startuped JS SDK** | Authenticated developer API calls | `@startuped-ai/sdk@1.0.4`; key sourced from local MCP config for verification only | Node SDK with wrapped `fetch` | explicit server-side developer calls | live and verified with `X-Startuped-Client: sdk-js` |
| **Startuped behavioral signals** | Automatic user/agent/CLI behavior tracking | `STARTUPED_API_KEY`, `STARTUPED_SIGNALS_ENABLED` | backend queue + frontend BFF | route views, UI interactions, form submits, auth, agent events, API mutations, CLI commands | live, non-blocking, privacy-safe |

## Adapter pattern

`backend/anvaya/agent/adapters.py`:

```python
class ProviderAdapter:
    name: str = "unknown"
    env_var: str = ""
    fallback_reason: str = ""

    def configured(self) -> bool: ...
    def healthy(self) -> bool: ...
    def availability(self) -> str: ...
    def fallback_message(self) -> str: ...
```

Rules:
1. If not configured, return a clearly labeled `anvaya-local-*` result.
2. If configured but request fails, catch exception and return fallback.
3. Never claim a fallback result came from the real provider.
4. Always set `fallback_used`, `fallback_reason`, and truthful `provider`.

## Tavily

`TavilyAdapter.search`:
- POSTs `https://api.tavily.com/search` with `api_key`, `query`, `search_depth`, `max_results`.
- Returns `{source: "tavily", provider: "tavily", records: [...]}`.
- Fallback: `{source: "anvaya-local-fixture", provider: "anvaya-local-fixture", records: [{type, value, source, confidence}]}`.

Called by:
- `agent/executor.py` `handle_threat_intelligence_lookup`
- `live/dispatch.py` `_tavily_enrich`

## n8n

`N8NAdapter.trigger(workflow, payload)`:
- POSTs `settings.n8n_webhook_url` with `{workflow, payload, timestamp}`.
- Returns `{provider: "n8n", source: "n8n", status: "triggered"}`.
- Fallback: writes `AuditRecord` and returns `{source: "anvaya-local-handler", fallback_used: True}`.

Workflows used:
- `anvaya_incident_event` — incident detected/sealed.
- `signal` — Startuped Signal API.
- `launchpad_account` — project creation.

## Gmail

`GmailAdapter.send(to, subject, body)`:
- Uses `google-auth` + `google-api-python-client`.
- Reads service-account JSON from `settings.gmail_credentials_path`.
- Fallback: writes `AuditRecord`.

## Lyzr

`LyzrAdapter.propose(prompt, response_schema)`:
- POSTs `https://api.lyzr.com/v2/llm/chat/completions`.
- Uses `LYZR_API_KEY` with `Authorization: ApiKey {key}`.
- Fallback: deterministic `anvaya-local-fixture`.

Note: `LyzrAdapter` is currently a real adapter but is not deeply integrated beyond `lyzr_propose_rule`.

## Swytchcode

`SwytchcodeAdapter`:
- `healthy()` returns `False`, so it always falls back.
- Designed to POST to `{settings.swytchcode_base_url}/v1/execute` with Bearer token.
- Not yet active.

## LLM providers

`backend/anvaya/llm/providers.py` implements a normalized `ModelProvider` interface for:
- OpenAI
- NVIDIA NIM
- OpenRouter
- OpenCode
- SeekAI
- GMI Cloud
- Empero
- AgentRouter
- Local deterministic fallback

Each provider exposes:
- `configured()`
- `chat_completion(messages, ...)`
- `stream(messages, ...)`

## API integration tracing template

For each integration, see `03-integration-tracing.md` rule. Here is Tavily as an example:

- **Caller:** `LocalToolExecutor.handle_threat_intelligence_lookup`, `live/_tavily_enrich`
- **Entry point:** `TavilyAdapter.search`
- **Request:** `{api_key, query, search_depth="basic", max_results=5}`
- **Transport:** HTTPS POST to `https://api.tavily.com/search`
- **Auth:** `TAVILY_API_KEY`
- **Validation:** adapter checks `healthy()` (configured)
- **Business logic:** none beyond formatting response
- **External service:** Tavily API
- **Response:** `{results: [{title, url, content, score}]}`
- **Transformation:** map to `{source, provider, records, record_count}`
- **Consumer:** agent executor or live dispatch
- **Failure:** exception caught → `anvaya-local-fixture` with `fallback_reason`
- **Observability:** `logger.warning("tavily.search_failed")` + fallback dict

## Startuped MCP integration trace

- **CALLER:** Devin model after the `startuped-xp` skill determines a meaningful, verified unit has shipped.
- **ENTRYPOINT:** `mcp__startuped-ai__create_signal` exposed by the `startuped-ai` MCP server.
- **REQUEST:** `{name, description, type: "engagement", status: "active", strength, value}`.
- **VALIDATION:** Startuped MCP tool schema constrains `type`, `status`, `value`, and accepts numeric `strength`; the skill requires factual descriptions and honest significance.
- **AUTH:** `Authorization: Bearer sk_…`, assembled from `AUTH_HEADER` in `.devin/mcp_config.local.json`.
- **TRANSPORT:** Devin stdio launches `npx -y mcp-remote`; the proxy connects by HTTPS to `https://mcp.startuped.ai/sse`.
- **TARGET:** Startuped MCP server v1.2.0, `create_signal` (`POST /api/v1/marketing/signals`).
- **TRANSFORMATION:** `mcp-remote` forwards MCP JSON-RPC `tools/call`; Startuped maps arguments into a marketing signal record.
- **RESPONSE:** MCP text content containing `success`, message, and created signal details.
- **ERROR HANDLING:** If unavailable, the skill skips signaling and the final task summary states that it was unavailable; product delivery never depends on XP logging.
- **RETRY:** No automatic loop; the skill explicitly limits signaling to one call per shipped unit.
- **TIMEOUT:** Managed by the Devin MCP client/`mcp-remote`; no project-specific timeout is configured.
- **LOGGING:** Devin MCP/tool output records success or failure; secrets are redacted by `devin mcp get`.
- **SECURITY BOUNDARY:** Local Devin process and gitignored credential file → external Startuped service over HTTPS.
- **DOWNSTREAM CONSUMERS:** Startuped marketing signal/XP systems and reviewers.

## Startuped SDK/product-action integration trace

- **CALLER:** one-off server-side developer workflow run from the ANVAYA frontend package context.
- **ENTRYPOINT:** `new Startuped(...).auth.validate()` for SDK attribution; Startuped REST product endpoints for account, lead, project, and campaign actions.
- **REQUEST:** structured ANVAYA/Decode SIH 2026 business records, scoped to the Anvaya organization.
- **VALIDATION:** live API schemas and UI request contracts; response status and returned IDs/statuses checked after writes.
- **AUTH:** Bearer API key loaded at runtime from gitignored local MCP configuration.
- **TRANSPORT:** HTTPS to canonical `https://www.startuped.ai`; SDK call explicitly includes `X-Startuped-Client: sdk-js`.
- **TARGET:** `/api/v1/auth/validate-api-key`, `/api/v1/accounts`, `/api/v1/leads`, `/api/v1/projects`, `/api/v1/marketing/campaigns`.
- **TRANSFORMATION:** SDK serializes auth validation; REST requests serialize JSON and use `x-organization-id` for organization scope.
- **RESPONSE:** authenticated identity or created resource with stable Mongo ID; campaign verified as `active` by follow-up GET.
- **ERROR HANDLING:** non-2xx responses are retained and corrected only after reading validation details; no fake success.
- **RETRY:** bounded curl retries for transient network errors; mutations are searched/verified to reduce accidental duplicates.
- **TIMEOUT:** explicit connect timeout on REST calls; command timeout enforced by the local runner.
- **LOGGING:** command output records HTTP status and returned resource IDs without printing the API key.
- **SECURITY BOUNDARY:** local server-side process and ignored credential file → external Startuped organization workspace.
- **DOWNSTREAM CONSUMERS:** Launchpad XP checklist, Startuped CRM/marketing dashboards, hackathon reviewers.

## Startuped behavioral signal trace

- **CALLER:** ANVAYA UI (including agent-panel selectors and chat lifecycle), backend routers, agent `EventStore`, and CLI shell.
- **ENTRYPOINT:** `trackStartupedEvent` in the frontend; `emit_startuped_signal` in the backend.
- **REQUEST:** `{name, description, type, status, strength, value, signalKey, metadata}`.
- **VALIDATION:** event name required; strength clamped to 0–100; metadata reduced to scalar/simple values.
- **AUTH:** Bearer API key read server-side from `STARTUPED_API_KEY` or ignored local MCP config.
- **TRANSPORT:** frontend batches to `/api/startuped/signals`; backend and CLI enqueue to a daemon worker; both use HTTPS to the canonical host.
- **TARGET:** `POST /api/v1/marketing/signals`.
- **TRANSFORMATION:** safe event names and metadata; no raw payloads or hidden reasoning.
- **RESPONSE:** accepted/delivered counts only; no secrets returned.
- **ERROR HANDLING:** all signal failures are swallowed after bounded delivery attempts.
- **RETRY:** backend worker posts with a short timeout; frontend uses one batched request per tick.
- **TIMEOUT:** 2 seconds backend, 3 seconds frontend BFF.
- **LOGGING:** only safe event names and failure status; no API keys or user content.
- **SECURITY BOUNDARY:** browser → same-origin BFF → Startuped; backend/CLI → Startuped.
- **DOWNSTREAM CONSUMERS:** Startuped behavioral analytics and XP/checklist systems.

## Active recall

- Which two integrations are wired through `on_incident_event(DETECTED)`?
- What is the fallback source for Tavily when not configured?
- Which n8n workflow is used for project creation → Launchpad?
- Why does `SwytchcodeAdapter` always fall back today?
- What is the honest fallback pattern for n8n?

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/adapters.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/live/dispatch.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/llm/providers.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/PROVIDER_FALLBACKS.md" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/.env.example" />
