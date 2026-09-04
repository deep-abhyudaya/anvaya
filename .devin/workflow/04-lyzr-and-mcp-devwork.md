# Workflow: Complete Lyzr + MCP / Claude Skills (developer-work XP)

Goal: the two remaining XP categories that require genuine new build
work rather than activating an existing stub. Do this after Workflows
01–03 unless explicitly told to reprioritize — see
`.devin/rules.md` Rule 6.

## Part A — Complete the Lyzr integration

### Step 1 — Confirm the real gap

`LyzrAdapter` in `backend/anvaya/agent/adapters.py` (line ~190) has
`healthy()` hardcoded to `return False`. Re-check this hasn't changed
before starting (per Rule 1's instruction to trust current code over
this document if they diverge).

### Step 2 — Decide Lyzr's actual job (don't duplicate existing logic)

Lyzr is a multi-agent orchestration platform. ANVAYA already has:
- Its own subagent system (`/agent/subagents`, see
  `backend/anvaya/routers/agent.py` lines ~580–712).
- A deterministic, non-LLM fallback path for rule proposal (see
  `sentinel/__init__.py`'s `_llm_propose_rule` and its fallback branch
  when `settings.is_llm_enabled()` is false).

Do not have Lyzr re-implement ANVAYA's existing subagent orchestration
— that's redundant and won't read as a meaningful new capability to a
judge. The strongest, least-redundant fit: **use Lyzr specifically as
an alternate/additional reasoning provider for the rule-proposal step**,
positioned alongside (not replacing) the existing LLM/deterministic
paths — i.e., a third option in whatever provider-selection logic
already exists there, following the same "provider with honest
fallback" pattern as every other adapter in this file.

If, after inspecting Lyzr's actual API docs, a different job fits
better (e.g. Lyzr agent drafting natural-language summaries of sealed
audit records for the credibility/reporting side of the product),
that's an acceptable alternative — the requirement is "real, non-
redundant use of Lyzr," not this exact placement.

### Step 3 — Build following the adapter pattern (Rule 2)

1. `env_var = "LYZR_API_KEY"` already declared on the class — confirm
   the matching `settings.lyzr_api_key` field exists in `config.py`
   (the adapter references it; verify it's actually declared, add it
   if missing, following the existing field-naming convention).
2. Implement `healthy()` for real: a lightweight auth-check call to
   Lyzr's API (check their docs for the cheapest health/ping endpoint),
   not just "key is present" if Lyzr's API makes that easy — but
   `configured()`-only health (matching the n8n pattern) is acceptable
   if Lyzr has no cheap health endpoint.
3. Implement the actual capability method (e.g. `propose(...)` or
   whatever fits the Step 2 use case), same try/except + honest
   fallback shape as every other adapter.
4. Register a `ToolDefinition` and executor handler, same as
   Workflow 01/03's pattern.
5. Wire the call site chosen in Step 2.

### Step 4 — Tests

Same requirements as every other adapter: mock the real API call, test
both success and fallback paths, don't require a real Lyzr key in CI.

## Part B — MCP / Claude Skills / SDK (developer-work XP)

This is structurally different from the provider-adapter pattern above
— it's about exposing ANVAYA's OWN capabilities outward to other
agents/tools, not consuming a third party.

### Option 1 — MCP server exposing ANVAYA's tool registry

1. ANVAYA already has a well-defined tool registry
   (`backend/anvaya/agent/registry.py`, `ToolDefinition`/
   `ToolParameter` classes). This maps naturally onto MCP's tool
   schema — an MCP server can wrap this registry and expose ANVAYA's
   existing tools (`threat_intelligence_lookup`, `trigger_automation`,
   the Sentinel/BlastScope/What-If operations, etc.) to any MCP client
   (Claude Desktop, Claude Code, etc.), not just ANVAYA's own frontend.
2. Build this as a new, separate module (e.g.
   `backend/anvaya/mcp_server.py` or a new `mcp/` package — don't
   modify the existing FastAPI routers to do double duty) using the
   official MCP Python SDK. Each MCP tool handler should call into the
   SAME executor methods the existing `/agent/execute` path uses
   (`executor.handle_threat_intelligence_lookup`, etc.) rather than
   reimplementing logic, so there's exactly one source of truth for
   each tool's behavior.
3. This is genuinely demoable: connect Claude Desktop (or another MCP
   client) to this server and show it calling `threat_intelligence_lookup`
   or querying incident data live, from outside ANVAYA's own UI
   entirely — a strong, visually distinct XP-category proof point.

### Option 2 — Claude Skill(s) for ANVAYA-specific workflows

1. A Claude Skill is a packaged set of instructions/scripts Claude can
   invoke for a specific task type — analogous to the `/mnt/skills/`
   pattern used elsewhere. Candidate: a "SIH pitch prep" or "incident
   report drafting" skill that takes a sealed `AuditRecord`'s JSON and
   produces a formatted incident summary — directly reusable for the
   credibility/reporting angle of the product itself.
2. Keep this scoped and genuinely useful — one well-built skill beats
   three thin ones.

### Option 3 — A minimal SDK/client library

If time allows: a small Python (and/or TypeScript) client package
wrapping ANVAYA's REST API (`/demo/run`, `/incidents`, `/agent/execute`,
etc.) with typed methods — the kind of thing a third-party developer
would actually want if integrating ANVAYA into their own SOC tooling.
Publish-ready structure (a `pyproject.toml`/`package.json`, a README)
counts more than an ad-hoc script.

## Step — Report back (required, see Rule 7)

- Lyzr: live-verified or blocked-on-credential; which reasoning step it
  was wired into and why that was the chosen placement.
- MCP/Skills/SDK: which option(s) were built, whether they're
  independently runnable/demoable (e.g. "connect Claude Desktop to
  `mcp_server.py` and call X" as a literal reproducible instruction),
  and test coverage if applicable.
