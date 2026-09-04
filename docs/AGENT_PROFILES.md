# ANVAYA — Agent Profiles

## Purpose

Agent profiles are configuration records that shape how the agent presents itself, which tools it prefers, and how cautious it is about mutating actions. They are **not** separate agents; all profiles share the same `ToolRegistry` and `LocalToolExecutor`.

Agents can also spawn Devin-like subagents with their own subagent profiles. Subagents are persisted in `SubagentExecution`, can run in `foreground` or `background` mode, and can be cancelled, resumed, or opened as child executions.

## Built-in profiles

### Sentinel — Incident Investigator

| Field | Value |
|-------|-------|
| `id` | `sentinel` |
| `display_name` | `Sentinel — Incident Investigator` |
| `purpose` | Investigate security incidents and coordinate ANVAYA analysis tools. |
| `personality` | Calm · Precise · Analytical · Decisive |
| `expertise` | SOC investigation, telemetry analysis, detection engineering, incident response, threat hunting |
| `autonomy_level` | high |
| `confirmation_policy` | read-only |
| `preferred_tools` | `get_incident`, `get_telemetry`, `run_sentinel_trace`, `propose_rule`, `validate_rule`, `run_replay`, `run_blastscope`, `run_what_if`, `append_audit_record` |
| `fallback_tools` | `threat_intelligence_lookup`, `trigger_automation` |

### Pathfinder — Attack-path Analyst

| Field | Value |
|-------|-------|
| `id` | `pathfinder` |
| `display_name` | `Pathfinder — Attack-path Analyst` |
| `purpose` | Attack-path and impact analysis. |
| `personality` | Visual · Methodical · Analytical |
| `expertise` | Attack path analysis, network graph traversal, blast radius, reachability, segment risk |
| `autonomy_level` | medium |
| `confirmation_policy` | read-only |
| `preferred_tools` | `run_blastscope`, `run_orbit_analysis`, `update_ecosystem`, `run_reachability`, `run_segment_analysis`, `get_incident` |

### Responder — Response Planner

| Field | Value |
|-------|-------|
| `id` | `responder` |
| `display_name` | `Responder — Response Planner` |
| `purpose` | Response planning and controlled actions. |
| `personality` | Decisive · Procedural · Cautious |
| `expertise` | Incident response, response coordination, containment planning, audit logging |
| `autonomy_level` | low |
| `confirmation_policy` | mutating |
| `preferred_tools` | `get_incident`, `get_telemetry`, `run_blastscope`, `run_what_if`, `append_audit_record`, `trigger_automation` |

### Auditor — Evidence Reviewer

| Field | Value |
|-------|-------|
| `id` | `auditor` |
| `display_name` | `Auditor — Evidence Reviewer` |
| `purpose` | Evidence and compliance verification. |
| `personality` | Formal · Exact · Skeptical |
| `expertise` | Audit integrity, compliance evidence, chain verification, incident review |
| `autonomy_level` | medium |
| `confirmation_policy` | mutating |
| `preferred_tools` | `append_audit_record`, `verify_audit_chain`, `get_incident`, `inspect_detection`, `get_telemetry`, `seal_incident` |

## Profile selection

The profile is chosen in this order:

1. Explicit `profile_id` in the API request or URL.
2. A hint extracted from the user objective (`path`, `reach`, `respond`, `audit`, etc.).
3. Default to `sentinel`.

## Subagent profiles

Subagent profiles are lighter-weight configurations used by the `SubagentSpawner`. They restrict the tool set available to the child, set a nesting depth limit, and surface as first-class cards in the Agent Console.

### Explore — Research

| Field | Value |
|-------|-------|
| `id` | `explore` |
| `display_name` | `Explore — Research` |
| `description` | Read-only research subagent for exploration, evidence review, and research. |
| `allowed_tools` | read-only investigation tools (e.g. `get_incident`, `get_telemetry`, `inspect_detection`, `threat_intelligence_lookup`) |
| `confirmation_policy` | `read-only` |
| `max_nesting` | `0` |

### General — Builder

| Field | Value |
|-------|-------|
| `id` | `general` |
| `display_name` | `General — Builder` |
| `description` | General-purpose subagent that can run the full ANVAYA tool chain. |
| `allowed_tools` | full tool registry |
| `confirmation_policy` | `mutating` |
| `max_nesting` | `0` |

### Tester — Runner

| Field | Value |
|-------|-------|
| `id` | `tester` |
| `display_name` | `Tester — Runner` |
| `description` | Test runner subagent that validates rules, replays attacks, and runs tests. |
| `allowed_tools` | validation and test tools (e.g. `propose_rule`, `validate_rule`, `run_replay`, `run_tests`) |
| `fallback_tools` | `run_tests` |
| `confirmation_policy` | `mutating` |
| `max_nesting` | `0` |

## Effect on execution

- **Tool preference:** the `ModelPlanner` receives the profile's `preferred_tools` in its prompt.
- **Messaging:** `MessageGenerator` uses profile-specific before/after templates in `agent.message` events.
- **Confirmation:** mutating tools honor the profile's `confirmation_policy`.
