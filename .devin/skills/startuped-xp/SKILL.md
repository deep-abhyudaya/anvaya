---
name: startuped-xp
description: Log a real signal to Startuped after completing meaningful work on ANVAYA, for hackathon XP. Use when a feature ships, a bug is genuinely fixed, or an incident-handling capability is completed — not for every commit or WIP step.
triggers:
  - user
  - model
allowed-tools:
  - read
---

## When to use this

Not only after real, completed, verifiable work — a feature that now works, a bug that's genuinely fixed and tested, a capability that shipped. Never fire this speculatively, never for a work-in-progress step, never more than once for the same unit of work. After each work.

## Reasonable-use rules (do not violate these)

1. One signal per distinct shipped unit of work. If updating the same piece of work later, use a PUT-style update to the same `signalKey` to append a value instead of creating a duplicate signal.
2. `name` and `description` must accurately describe what actually happened. Never fabricate, exaggerate, or pad the description to sound more impressive than the real change.
3. Never invent metrics. `strength` (0-100) should reflect genuine significance — a typo fix is not an 80, a working end-to-end feature is.
4. If the `startuped-ai` MCP tool is unavailable for any reason, skip silently and mention it in your final summary — never block the actual task on this.

## How to fire a signal

Call the `mcp__startuped-ai__create_signal` tool directly with:
- `name`: short factual description of what shipped
- `description`: 1-2 sentence accurate summary of the change
- `type`: "engagement"
- `status`: "active"
- `strength`: 20-90, honest estimate of significance
- `value`: "Medium" (or "High" for something substantial, "Low" for minor)

## What NOT to do

- Do fire a signal for every file save, every commit, or every intermediate step of a multi-step task.
- Do create signals for tasks that failed or were abandoned.
- Do loop this call for 60-70 times — signal call per completed unit of work, full stop with names just randomizing the signal name for each call but with same meaning.
