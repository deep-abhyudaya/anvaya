# ANVAYA — Provider Fallback Matrix

This document defines truthful fallbacks for optional integrations.

## Principle

External integrations improve ANVAYA; they must not become single points of failure for the core deterministic SOC demonstration.

| Capability | Primary | Fallback 1 | Fallback 2 | Truth requirement |
|---|---|---|---|---|
| Agent orchestration | Lyzr, if configured | existing OpenAI integration | deterministic local policy orchestrator | never claim Lyzr ran unless it ran |
| Tool execution | Swytchcode, if configured | local ANVAYA ToolRegistry | unavailable | never attribute local execution to Swytchcode |
| Web/threat search | Tavily | local deterministic threat-intel fixture/index | unavailable | never fabricate live sources |
| Workflow automation | n8n | local event handler | recorded no-op | never claim n8n ran if unreachable |
| Deployment | Render | Docker/local | — | deployment provider is infrastructure, not a runtime dependency |
| Development assistance | CodeMate | existing engineering workflow | — | not a runtime dependency |
| GTM | Startuped | local docs | — | not a runtime dependency |

## Lyzr unavailable

Use:
1. existing OpenAI integration/function calling already present in the repo, if configured;
2. otherwise deterministic local orchestration.

The local orchestrator should choose tools using explicit rules based on:
- user objective;
- incident state;
- available artifacts;
- tool preconditions.

It must not pretend to be an LLM.

## Swytchcode unavailable

Use the local ToolRegistry.

Provider status must say:
`Local ANVAYA executor`

The UI may still show the exact same tool call card, but provider attribution must be truthful.

## Tavily unavailable

Use a deterministic fixture/index containing only clearly labelled synthetic or curated test intelligence.

UI:
`Threat intelligence provider: Local fixture`

Never invent:
- live URLs;
- live source counts;
- current CVE status;
- current threat actor activity.

## n8n unavailable

Execute the local automation handler if the action is safe and supported.

UI:
`Automation: local handler`

If no local equivalent exists:
`Automation unavailable — recorded only`

## Render unavailable

Nothing in the application should break.

Development:
- Docker Compose/local process.

Production/deployment:
- document Render configuration separately.

## Provider selection algorithm

For every capability:

1. inspect configuration;
2. health-check provider if required;
3. if configured and healthy, use provider;
4. otherwise emit a provider-unavailable event;
5. select fallback;
6. emit fallback event;
7. execute fallback;
8. return provider + fallback_used in ToolResult.

## Never do this

Bad:
`Tavily search complete — 7 sources`
when Tavily was unavailable.

Good:
`Tavily unavailable — local fixture returned 7 synthetic/curated records`

Bad:
`Swytchcode executed Replay`
when the local executor executed Replay.

Good:
`Replay executed by ANVAYA local executor`

Bad:
`Lyzr decided to run BlastScope`
when local policy selected BlastScope.

Good:
`Local orchestrator selected BlastScope`
