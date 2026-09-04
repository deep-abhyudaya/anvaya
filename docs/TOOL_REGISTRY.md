# ANVAYA — Tool Registry

## Purpose

The `ToolRegistry` is the single source of truth for tools the agent can invoke. It defines each tool's name, intent, input schema, required capabilities, risk level, and confirmation policy.

## Registry location

- Definition: `backend/anvaya/agent/registry.py`
- Runtime execution: `backend/anvaya/agent/executor.py::LocalToolExecutor`

## Adding a tool

```python
from anvaya.agent.registry import ToolSpec, default_tool_registry

registry = default_tool_registry()
registry.register(
    ToolSpec(
        name="get_incident",
        description="Load a single incident by ID.",
        required_inputs=["incident_id"],
        optional_inputs=[],
        required_capabilities=[],
        risk_level="none",
        requires_confirmation=False,
        handler=load_incident_handler,
    )
)
```

## Built-in tools

| Tool | Intent | Key inputs | Risk |
|------|--------|-----------|------|
| `get_incident` | Load incident metadata | `incident_id` | none |
| `get_telemetry` | Load related telemetry rows | `incident_id`, `limit` | none |
| `inspect_detection` | Inspect a specific detector record | `detection_id` | none |
| `run_sentinel_trace` | Run SentinelBacktracker on the incident | `incident_id` | none |
| `propose_rule` | Generate a Sigma-style detection rule | `incident_id`, `technique` | low |
| `validate_rule` | Validate a proposed rule | `rule_text` | low |
| `run_replay` | Replay the scenario with the proposed rule | `incident_id`, `rule_id` | low |
| `run_blastscope` | Compute blast radius via graph traversal | `incident_id`, `focus` | low |
| `run_orbit_analysis` | Analyze threat-ecosystem clusters | `node_id` | none |
| `run_reachability` | Compute reachability from an asset | `asset_id`, `depth` | none |
| `run_segment_analysis` | Analyze segment risk | `segment_id` | none |
| `run_what_if` | Run a counterfactual what-if simulation | `incident_id`, `parameter` | low |
| `update_ecosystem` | Update the threat-ecosystem graph | `incident_id` | low |
| `threat_intelligence_lookup` | Query external threat intel | `indicator`, `indicator_type` | none |
| `trigger_automation` | Trigger an n8n/Swytchcode workflow | `workflow`, `payload` | medium |
| `append_audit_record` | Append an audit record | `incident_id`, `reason` | none |
| `verify_audit_chain` | Verify the audit chain integrity | `incident_id` | none |
| `seal_incident` | Mark the incident as sealed | `incident_id` | low |

## Execution

`LocalToolExecutor.execute()`:

1. Validates that the tool is registered.
2. Coerces inputs to the `ToolSpec`.
3. Calls the handler.
4. Records `tool.started`, `tool.progress`, and `tool.completed` / `tool.failed` events.
5. Produces a `ToolResult` with `output`, `duration_ms`, `provider`, `fallback_used`, and `fallback_reason`.

## Tool results

Each result is normalized to:

```python
class ToolResult(BaseModel):
    tool: str
    status: str
    output: Any
    provider: str = "anvaya"
    duration_ms: float = 0.0
    fallback_used: bool = False
    fallback_reason: str = ""
```

The executor never swallows failures. A tool failure is logged as a `tool.failed` event and, when recoverable, can trigger a `tool.fallback` event.
