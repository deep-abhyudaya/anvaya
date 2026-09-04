# Rule 00 — ANVAYA Core Engineering Charter

## Repository-first reasoning

- The repository source code is the source of truth.
- The ANVAYA presentation, `AGENTS.md`, and `DEVIN_MASTER_PROMPT.md` define intended behavior, but do not assume every documented feature is implemented.
- Inspect the actual code before editing.

## No architectural hallucination

- Never invent existing routes, tables, services, or integrations.
- Search the codebase before creating duplicates.
- If something is uncertain, mark it `UNKNOWN — NEEDS VERIFICATION`, especially in `.anvaya/knowledge/25_UNKNOWN_QUESTIONS.md`.

## Integration-first analysis

- Prefer understanding relationships over memorizing filenames.
- For every file, answer: who calls it, what it calls, what data enters/leaves, and what state it changes.
- Use `04_INTEGRATION_GRAPH.md` and `05_DATA_FLOWS.md` as the canonical integration docs.

## Security-first reasoning

- Never weaken isolation to simplify implementation.
- Never expose API keys, secrets, or hidden chain-of-thought to the frontend.
- Never fake detection, ML metrics, replay success, audit integrity, or external API results.
- All synthetic attack scenarios must remain deterministic, isolated, and defensive.

## Explicit uncertainty

- When uncertain, say so. Do not fabricate certainty.
- Use the `UNKNOWN — NEEDS VERIFICATION` label.
- Update `.anvaya/knowledge/25_UNKNOWN_QUESTIONS.md`.

## Importance-weighted reading

- Score modules by: architecture impact, integration centrality, security criticality, business importance, failure impact, learning value.
- Spend more time on high-score code; summarize low-score boilerplate.

## Preservation of existing behavior

- Preserve the existing architecture and judge-demo flow.
- Do not rewrite to match a marketing claim; implement the smallest coherent vertical slice.

## Documentation synchronization

- Every non-trivial change must update the relevant `.anvaya/knowledge/` doc and `CHANGELOG.md`.
- When adding an integration, follow `03-integration-tracing.md`.
- When changing architecture, follow `02-architecture-change-protocol.md`.
- When changing security-sensitive code, follow `04-security-sensitive-changes.md`.

## Active-recall maintenance

- Add/update/remove questions in `24_ACTIVE_RECALL.md` when the mental model changes.
- Ensure source-backed answers exist.

## Final judge principle

Optimize for judge-observable proof, not marketing:

```text
miss → ground truth → backtrack → rule proposal → validation → identical replay → catch → blast simulation → what-if → sealed audit
```
