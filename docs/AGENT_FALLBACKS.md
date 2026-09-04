# ANVAYA — Agent Fallbacks

## Principle

ANVAYA must never silently pretend an external integration is working. Every optional provider has a **local fallback** that is deterministic and safe. The console and logs truthfully report which provider was actually used and why.

## Fallback levels

### 1. Model provider fallback

- If no API key or base URL is configured, the orchestrator uses `LocalProvider`.
- If a model is selected that is not compatible with the required capabilities, the orchestrator falls back to a compatible model.
- If the external API returns an error, the call is retried once, then `LocalProvider` is used.

### 2. Tool provider fallback

- `TavilyAdapter.search` → if `TAVILY_API_KEY` is missing, returns a local fixture and sets `source=anvaya-local-fixture`.
- `N8NAdapter.trigger` → if `N8N_WEBHOOK_URL` is missing, records the payload and returns `status=recorded`.
- `SwytchcodeAdapter` → if `SWYTCHCODE_API_KEY` is missing, returns a simulated coverage response.
- `LyzrAdapter` → if `LYZR_API_KEY` is missing, falls back to the local orchestrator.

### 3. Planning fallback

- `ModelPlanner.build_plan` returns `None` when the model is unavailable, returns an error, or produces an unparseable plan.
- The orchestrator detects `None` and switches to `DeterministicPlanner`, which uses the existing policy plan.

### 4. Tool execution fallback

- If a tool handler raises an exception, `LocalToolExecutor` records `tool.failed`.
- If the tool has an optional external dependency that failed, a `tool.fallback` event is emitted with the same `provider` and `fallback_reason`.
- `fallback_used=True` and `fallback_reason` are always present in the `ToolResult` when a substitution occurred.

## Truthful attribution

The frontend `ToolCard` displays:

- The provider name used.
- `fallback_used` badge.
- `fallback_reason` text.
- A **Provider status** panel showing every adapter/model's current `availability` (`available`, `configured`, `unavailable`) and health.

## Event contract

Fallbacks produce the same event types as successful calls so the trace remains consistent:

- `tool.started` → `tool.fallback` (if substituted) → `tool.completed` / `tool.failed`

Fallbacks never inject fake success. If a tool genuinely cannot be satisfied even locally, `tool.failed` is emitted.
