# ANVAYA — Devin Master Engineering Prompt
## Agentic Tool Execution + Optional Sponsor Integrations + Deterministic Fallbacks

You are acting as the senior/staff engineer responsible for extending the existing ANVAYA repository.

IMPORTANT:
- Inspect the repository before editing.
- The repository code is the implementation source of truth.
- AGENTS.md and the supplied ANVAYA specification define intended product behavior, but do not assume every documented feature is implemented.
- Never invent existing routes, database tables, services, dependencies, or integrations.
- Search the codebase before creating duplicates.
- Preserve the existing ANVAYA architecture and judge-demo flow.
- Do not expose hidden chain-of-thought. The UI must show observable tool execution events, inputs/outputs that are safe to display, status, timing, and artifacts—not private reasoning.
- Never fake detection, ML metrics, replay success, audit integrity, or external API results.

## Current product context

ANVAYA is a defensive cyber SOC simulator. Its judge-observable proof is:

miss → ground truth → backtrack → rule proposal → validation → identical replay → catch → blast simulation → what-if → sealed audit

Existing core capabilities include:
- FastAPI backend
- Next.js frontend
- SQLModel/database layer
- deterministic synthetic telemetry and scenarios
- Alertness / Isolation Forest
- SentinelBacktracker
- NetworkX BlastScope / graph analysis
- Logistic Regression What-If
- deterministic replay
- ControlLedger / audit chain
- ecosystem / orbit / segment / impact-oriented frontend experiences
- existing demo/static data in parts of the application

The existing engineering charter explicitly requires deterministic simulation/replay, strict validation of model outputs, no data leakage, tests, documentation, and no false claims.

## Primary goal

Add a robust agentic execution layer so a user can ask ANVAYA to investigate an incident and watch ANVAYA execute real tools in real time.

The experience should feel like modern agentic developer products:
1. user gives an objective;
2. agent starts;
3. a tool call appears;
4. tool executes;
5. result/artifact appears;
6. next tool call is selected;
7. progress streams into the UI;
8. the final investigation state is persisted.

The system must work even when optional external providers are unavailable.

## NON-NEGOTIABLE FALLBACK PRINCIPLE

Every optional external integration must have a local fallback.

Never make the core ANVAYA demo fail because:
- Swytchcode credentials are missing;
- Lyzr access is unavailable;
- Tavily credentials are missing;
- n8n is unavailable;
- Render is not being used;
- network access is unavailable.

The application must expose provider status and use the best available implementation.

Preferred order:

Agent orchestration:
1. Lyzr, if configured and actually usable
2. existing OpenAI integration/function-calling already present in the repository, if configured
3. deterministic local tool orchestrator

Tool execution:
1. Swytchcode, if configured and actually usable
2. local ANVAYA ToolRegistry / executor

Threat intelligence:
1. Tavily, if configured and actually usable
2. local deterministic threat-intelligence fixture/index
3. clearly labelled "unavailable" state
Never fabricate live intelligence.

Automation:
1. n8n webhook/workflow, if configured and reachable
2. local ANVAYA event handler
3. no-op/auditable fallback that records "automation unavailable"

Deployment:
1. Render deployment when configured
2. Docker Compose/local execution for development
3. do not make Render a runtime dependency.

## Sponsor/provider roles

These are optional integrations, not reasons to rewrite ANVAYA:

### Swytchcode
Primary external tool execution/integration layer.
Swytchcode currently documents agent-ready API integrations, manifests, CLI execution, MCP support, authentication, retries and execution controls.

Use it where it genuinely adds value:
- external API/tool execution
- validated tool schemas
- provider auth boundary
- observable execution status
- optional MCP-based tool discovery where appropriate

Do NOT pretend Swytchcode executes ANVAYA's internal Python functions unless the chosen integration path actually supports that. Internal ANVAYA tools must remain callable locally.

### Tavily
Live web/threat-intelligence enrichment.
Use it for:
- IP/domain/hash/CVE/technique queries
- incident enrichment
- source discovery
- evidence links/snippets

Do not replace deterministic incident evidence with web search.
Do not fabricate results when Tavily is unavailable.
Fallback to a clearly labelled local threat-intel fixture/index.

### Lyzr
Optional agent-development/orchestration provider.
The user currently does not have Lyzr access.
Do NOT block implementation on Lyzr.
Create a provider interface so Lyzr can be added later without changing the UI or tool contracts.
Use the existing repository OpenAI integration as the preferred model-backed fallback if available.
If no model provider is available, use a deterministic policy-based orchestrator.

### n8n
Optional workflow automation.
Use for external workflow automation where useful:
- post-investigation notification
- evidence/report workflow
- audit/export workflow
- demo workflow trigger

Do not make n8n necessary for core SOC operations.
Fallback to local handlers.

### Render
Deployment/infrastructure only.
Do not add fake runtime features to the product just to claim Render usage.
Prepare deployment configuration for the actual application.
Prefer multiple real services only where justified by the existing architecture and the hackathon requirement.

### CodeMate
Development-time tool only. Do not create a fake runtime dependency.

### Startuped.ai
Product/GTM activity only. Do not create a fake runtime dependency.

## TOOL CONTRACT

Create a typed, provider-neutral tool registry.

Do not hardcode provider-specific logic into the UI.

Conceptual interface:

ToolDefinition:
- name
- description
- category
- input_schema
- output_schema
- risk_level
- requires_confirmation
- provider
- fallback_provider
- timeout_ms
- idempotent
- supports_streaming

ToolResult:
- tool_call_id
- tool_name
- status
- provider
- started_at
- completed_at
- duration_ms
- input_summary
- output_summary
- artifact_refs
- error_code
- error_message
- fallback_used
- fallback_reason

Do not invent database columns until you inspect the existing models. Reuse existing persistence where appropriate; otherwise add a cohesive event model only if needed.

## INTERNAL ANVAYA TOOLS

Expose existing real capabilities through a single tool abstraction.

First inspect the repository and map the real implementation to these capabilities:

- get_incident
- get_telemetry
- inspect_detection
- create_replay
- run_replay
- get_replay_result
- run_sentinel_trace
- confirm_ground_truth
- propose_rule
- validate_rule
- run_blastscope
- build_or_update_ecosystem
- run_orbit_analysis
- run_reachability
- run_segment_analysis
- run_what_if
- get_metrics
- append_audit_record
- verify_audit_chain
- seal_incident

IMPORTANT:
These are capability names, not assumed existing API routes.
Map each one to the actual repository implementation.
If a capability does not exist, do not silently fake it. Either:
- implement it using existing business logic, or
- mark it unavailable and provide a deterministic fixture only where a demo visualization genuinely requires it.

## AGENT POLICY

The agent must be policy-driven, not an unrestricted LLM.

For every objective:
1. identify the incident/context;
2. choose a tool from the registry;
3. validate inputs;
4. execute;
5. validate output;
6. emit an event;
7. decide whether another tool is needed;
8. stop when the objective is satisfied.

The agent must never:
- execute arbitrary shell commands from model output;
- execute arbitrary Python generated by a model;
- directly mutate the database through an LLM;
- invent an incident result;
- claim an external search happened when it did not;
- claim a replay caught an attack without observing the detector result;
- expose API keys or secrets to the frontend;
- bypass tool input validation.

Use allowlisted tools only.

## REAL-TIME EXECUTION TRACE

Implement a server-side event stream.

Preferred:
- SSE if it fits the existing FastAPI architecture with minimal complexity.

Fallback:
- React Query polling of an execution/event endpoint at the existing project cadence.

Do not introduce WebSockets merely for marketing if SSE/polling is sufficient.

Event types should include at minimum:

agent.started
agent.plan_created
tool.started
tool.input_ready
tool.progress
tool.completed
tool.failed
tool.fallback
artifact.created
incident.updated
agent.completed
agent.failed

Example observable event:

{
  "execution_id": "...",
  "sequence": 12,
  "type": "tool.started",
  "tool_call_id": "...",
  "tool_name": "create_replay",
  "provider": "anvaya",
  "label": "Creating deterministic replay",
  "timestamp": "...",
  "status": "running"
}

Never include hidden chain-of-thought.

## UI EXPERIENCE

Build an Agent Activity / Execution panel that fits the existing ANVAYA UI. Do not redesign the whole product.

Example:

INVESTIGATION
INC-B2D82C97
● RUNNING

✓ Incident loaded
✓ Telemetry inspected — 37 events

◉ Creating Replay
  Replay #R-1042
  ANVAYA / 1.2s

✓ Searching Threat Intelligence
  Tavily / 7 sources

◉ Updating Ecosystem
  3 entities · 2 relationships

◉ Running Orbit
  14 nodes traversed

○ Running What-If

The user can expand a tool event to see:
- tool name
- safe input summary
- provider
- status
- duration
- safe output summary
- artifact/result link
- fallback information

The UI should feel live:
- new events appear without a full page refresh;
- running tools show an active state;
- completion updates the same event;
- failures show the fallback;
- artifacts become clickable when created.

Examples of artifact cards:
- Replay created
- Ecosystem updated
- Orbit generated
- BlastScope result
- What-If analysis
- Threat intelligence evidence
- Audit record

## AGENTIC DEMO SCENARIO

Make one polished end-to-end path for the existing deterministic missed-attack scenario.

Target observable sequence:

1. Load incident
2. Inspect telemetry
3. Confirm the known ground-truth state through the existing supported mechanism
4. Run Sentinel/backtracking
5. Propose a detection rule
6. Validate rule
7. Create deterministic replay
8. Execute replay
9. Verify the detector actually caught it
10. Run BlastScope
11. Update/build ecosystem visualization if supported by real implementation
12. Run Orbit/risk analysis if supported by real implementation
13. Run What-If
14. Append audit events
15. Verify audit chain
16. Seal incident

Do not claim success unless the actual result proves it.

The agent should be able to stop early if a step is genuinely unavailable, while clearly recording why.

## TOOL FALLBACK UI

When an external provider is unavailable, show:

"Swytchcode unavailable — using ANVAYA local executor"

or:

"Tavily unavailable — using local threat-intel fixture"

or:

"Lyzr unavailable — using ANVAYA model/local orchestrator"

Do not make fallback look identical to live external data.
The user must know which provider actually ran.

## OBSERVABILITY

Persist enough execution metadata to reconstruct:
- who/what started an execution;
- which tools ran;
- provider used;
- fallback used;
- timestamps;
- status;
- safe input/output summaries;
- artifacts;
- errors.

Use the existing ControlLedger for important audit transitions where appropriate.

Do not store:
- secrets;
- full API keys;
- private model chain-of-thought;
- unnecessary raw third-party content.

## FAILURE HANDLING

Every tool call needs:
- timeout;
- structured exception mapping;
- retry policy where safe;
- idempotency for repeatable operations;
- fallback selection;
- event emission.

Never retry a non-idempotent mutation blindly.

If an external provider times out:
1. mark provider failure;
2. emit tool.failed;
3. select fallback;
4. emit tool.fallback;
5. execute fallback;
6. continue if safe.

## SECURITY

- All external credentials belong in environment variables/secrets.
- Never send credentials to the browser.
- Validate all tool arguments with strict schemas.
- Use allowlists for tools.
- Enforce per-tool risk level.
- Read-only tools can run automatically.
- Mutating tools should support confirmation policy.
- Never allow the model to generate arbitrary code for execution.
- Never introduce real-world offensive cyber actions.
- Keep all attack scenarios synthetic and deterministic.

## TESTING

Add tests for:
1. tool registry discovery;
2. schema validation;
3. local tool execution;
4. provider selection;
5. fallback selection;
6. provider timeout;
7. provider failure;
8. event ordering;
9. duplicate/idempotent execution;
10. SSE or polling event delivery;
11. UI rendering of running/completed/failed/fallback events;
12. end-to-end deterministic demo.

Test with NO external credentials first.

Then add optional integration tests that are skipped unless provider credentials are present.

The test suite must prove:
- missing Swytchcode does not break the demo;
- missing Lyzr does not break the demo;
- missing Tavily does not break the demo;
- missing n8n does not break the demo;
- local fallback produces truthful results;
- no fake provider attribution appears.

## IMPLEMENTATION ORDER

Phase 0 — Audit
- inspect full repo;
- map current routes/services/models/frontend pages;
- identify actual replay/ecosystem/orbit/BlastScope/What-If implementations;
- identify existing OpenAI integration;
- identify current static/demo data;
- identify existing realtime/polling mechanisms;
- produce docs/AGENTIC_AUDIT.md.

Phase 1 — Provider-neutral tool system
- ToolDefinition;
- ToolResult;
- registry;
- local executor;
- provider interface;
- fallback policy.

Phase 2 — Internal ANVAYA tools
- wrap existing business logic;
- do not duplicate engines;
- ensure each tool returns typed results/artifacts.

Phase 3 — Execution events
- execution ID;
- event sequence;
- SSE if appropriate;
- polling fallback;
- persistence.

Phase 4 — Agent orchestration
- Lyzr adapter interface;
- existing OpenAI adapter if available;
- deterministic local orchestrator;
- policy-based tool selection.

Phase 5 — External providers
- Swytchcode adapter;
- Tavily adapter;
- n8n adapter;
- Render deployment configuration;
- provider health/status.

Phase 6 — UI
- execution panel;
- tool cards;
- artifact cards;
- provider/fallback badges;
- live progress;
- failure/fallback states.

Phase 7 — Demo
- polish the missed-attack investigation path;
- make the tool trace visually excellent;
- ensure Replay/Ecosystem/Orbit/BlastScope/What-If results are real and clickable.

Phase 8 — QA
- run backend tests;
- run frontend checks;
- run integration tests;
- run the demo from a clean environment with zero external credentials;
- then test available provider integrations;
- inspect git diff;
- update docs.

## DEFINITION OF DONE

Do not say "done" until:
- repository audit is complete;
- implementation uses real existing business logic;
- tool registry works;
- local fallback works with no provider credentials;
- at least one real agent execution path works;
- events stream to the UI;
- tool calls visibly appear in realtime;
- Replay/Ecosystem/Orbit/BlastScope/What-If are represented only when their underlying implementation/result exists;
- external provider status is truthful;
- tests pass;
- lint/type checks pass;
- docs explain setup and fallback behavior;
- no secrets are committed;
- no hidden chain-of-thought is exposed;
- no fake detection or ML claims are introduced.

## Final instruction

Do not start by rewriting the architecture.

Start by auditing the actual repository and creating docs/AGENTIC_AUDIT.md.

Then implement the smallest cohesive vertical slice:

USER OBJECTIVE
→ AGENT
→ TOOL REGISTRY
→ LOCAL TOOL EXECUTOR
→ REAL ANVAYA TOOL
→ EXECUTION EVENT
→ LIVE UI
→ RESULT ARTIFACT

Once that works, add Swytchcode/Tavily/n8n adapters behind the same interfaces.

The final product should make a judge able to see ANVAYA actively doing work—not merely receiving a chat response.
