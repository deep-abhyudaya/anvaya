# ANVAYA Agentic Integration Pack

This archive contains the engineering prompt and supporting contracts for adding an agentic execution layer to ANVAYA.

Files:

- `DEVIN_MASTER_PROMPT.md` — paste this into Devin as the primary engineering instruction.
- `PROVIDER_FALLBACKS.md` — provider/fallback truthfulness and selection rules.
- `AGENT_EXECUTION_EVENTS.md` — realtime event contract for tool calls and UI activity.

## Intended experience

```text
User objective
   ↓
Agent
   ↓
Tool registry
   ↓
Real ANVAYA capability
   ↓
Realtime execution event
   ↓
UI activity card
   ↓
Artifact/result
   ↓
Next tool
```

Example tools include the existing project's capabilities around:
- replay
- Sentinel/backtracking
- BlastScope
- ecosystem analysis
- orbit/risk analysis
- What-If
- audit/ledger

External providers are optional:
- Swytchcode → external tool/API execution layer
- Tavily → live web/threat-intelligence enrichment
- Lyzr → optional agent orchestration
- n8n → optional workflow automation
- Render → deployment
- CodeMate → development
- Startuped.ai → GTM/product work

The core ANVAYA demo must remain functional without external credentials.

## Source grounding

The project engineering charter says to inspect the repository before editing, never fake test/ML/detection/audit results, keep synthetic data deterministic, keep simulation replayable, validate model outputs, and optimize for the judge-observable lifecycle:
`miss → ground truth → backtrack → rule proposal → validation → identical replay → catch → blast simulation → what-if → sealed audit`.

The prompt intentionally treats documented capabilities as requirements to verify against the repository rather than assuming they are already implemented.
