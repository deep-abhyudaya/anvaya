"""Provider-neutral tool registry."""

from __future__ import annotations

from typing import Any

from anvaya.agent.schemas import ToolDefinition, ToolParameter
from anvaya.models.project import ARTIFACT_TYPES


class ToolRegistry:
    """Central registry for agent tools."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool definition."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_by_category(self, category: str) -> list[ToolDefinition]:
        """List tools in a category."""
        return [t for t in self._tools.values() if t.category == category]

    def validate_inputs(self, name: str, inputs: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate inputs against the tool's parameter schema.

        Returns (valid, errors).
        """
        tool = self.get(name)
        if not tool:
            return False, [f"Tool '{name}' not found"]

        errors: list[str] = []
        for param in tool.parameters:
            if param.required and param.name not in inputs:
                errors.append(f"Missing required parameter '{param.name}'")
                continue

            value = inputs.get(param.name, param.default)
            if value is None:
                continue

            if param.type == "string" and not isinstance(value, str):
                errors.append(f"Parameter '{param.name}' must be a string")
            elif param.type == "integer" and not isinstance(value, int):
                errors.append(f"Parameter '{param.name}' must be an integer")
            elif param.type == "number" and not isinstance(value, (int, float)):
                errors.append(f"Parameter '{param.name}' must be a number")
            elif param.type == "boolean" and not isinstance(value, bool):
                errors.append(f"Parameter '{param.name}' must be a boolean")
            elif param.type == "array" and not isinstance(value, list):
                errors.append(f"Parameter '{param.name}' must be a list")
            elif param.type == "object" and not isinstance(value, dict):
                errors.append(f"Parameter '{param.name}' must be an object")

            if param.enum:
                if isinstance(value, list):
                    for item in value:
                        if item not in param.enum:
                            errors.append(
                                f"Parameter '{param.name}' item '{item}' must be one of "
                                f"{param.enum}"
                            )
                elif value not in param.enum:
                    errors.append(f"Parameter '{param.name}' must be one of {param.enum}")

        return len(errors) == 0, errors


def default_tool_registry() -> ToolRegistry:
    """Return the default ANVAYA tool registry."""
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="get_incident",
            description="Load an incident by ID.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_telemetry",
            description="Inspect telemetry for an incident or scenario.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="limit",
                    description="Maximum events to return",
                    type="integer",
                    required=False,
                    default=100,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="inspect_detection",
            description="Inspect the latest detection run for an incident.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="run_sentinel_trace",
            description="Run SentinelBacktracker evidence backtracking for an incident.",
            category="sentinel",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="medium",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="confirm_ground_truth",
            description=(
                "Confirm the attack ground-truth for an incident and advance self-correction state."
            ),
            category="sentinel",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="high",
            requires_confirmation=True,
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="propose_rule",
            description="Propose a candidate detection rule from backtracked evidence.",
            category="sentinel",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="medium",
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="validate_rule",
            description="Validate the proposed rule against historical telemetry.",
            category="sentinel",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="medium",
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="run_replay",
            description="Create and run an identical replay with the validated rule.",
            category="sentinel",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="high",
            requires_confirmation=True,
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="run_blastscope",
            description="Run BlastScope graph traversal and blast-radius analysis.",
            category="simulation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="medium",
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="build_or_update_ecosystem",
            description="Build or update the threat ecosystem visualization.",
            category="simulation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="mode",
                    description="Simulation mode",
                    type="string",
                    required=False,
                    default="CONTAIN",
                    enum=["IGNORE", "CONTAIN"],
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="generate_artifacts",
            description=(
                "Generate project artifacts (orbits, segments, reach, arena, "
                "ecosystem, trophy_wall, replay, arbor, impacts, ledger, incidents) "
                "from a dataset."
            ),
            category="generation",
            parameters=[
                ToolParameter(
                    name="project_id",
                    description="Project identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="dataset_id",
                    description=(
                        "Optional dataset identifier; if omitted the most recent "
                        "project dataset is used"
                    ),
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="requested_artifacts",
                    description="Artifact types to generate",
                    type="array",
                    required=True,
                    enum=ARTIFACT_TYPES,
                ),
            ],
            risk_level="medium",
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="manage_artifacts",
            description=(
                "Full artifact lifecycle control: generate, regenerate "
                "(delete+generate), or delete project artifacts (orbits, segments, "
                "reach, arena, ecosystem, trophy_wall, replay, arbor, impacts, "
                "ledger, incidents, or all)."
            ),
            category="generation",
            parameters=[
                ToolParameter(
                    name="project_id",
                    description="Project identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="action",
                    description="Lifecycle action to perform",
                    type="string",
                    required=True,
                    enum=["generate", "regenerate", "delete"],
                ),
                ToolParameter(
                    name="requested_artifacts",
                    description='Artifact types to operate on; use ["all"] for every type',
                    type="array",
                    required=False,
                    default=["orbits"],
                    enum=ARTIFACT_TYPES,
                ),
                ToolParameter(
                    name="dataset_id",
                    description=(
                        "Optional specific dataset; otherwise the latest project dataset is used"
                    ),
                    type="string",
                    required=False,
                    default="",
                ),
            ],
            risk_level="high",
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="run_orbit_analysis",
            description="Run orbit/risk analysis for an incident or project.",
            category="simulation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident or project identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="run_reachability",
            description="Run asset reachability analysis.",
            category="simulation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="run_segment_analysis",
            description="Run ranked network segment analysis.",
            category="simulation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="run_what_if",
            description="Run What-If counterfactual risk analysis.",
            category="defense",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="changes",
                    description="Counterfactual feature changes",
                    type="object",
                    required=False,
                    default={"is_off_hours": 0.0, "is_new_device": 0.0},
                ),
            ],
            risk_level="medium",
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="observe_environment",
            description=(
                "Observe the current environment: project, incident, "
                "telemetry, and graph state."
            ),
            category="observation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="project_id",
                    description="Project identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="objective",
                    description="Objective text for context extraction",
                    type="string",
                    required=False,
                    default="",
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="observe_project",
            description="Observe a project and its datasets, artifacts, and prior executions.",
            category="observation",
            parameters=[
                ToolParameter(
                    name="project_id",
                    description="Project identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="detect_anomalies",
            description="Detect anomalous entities and events for an incident or project.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="project_id",
                    description="Project identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="top_k",
                    description="Number of top candidates",
                    type="integer",
                    required=False,
                    default=5,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="search_events",
            description="Search telemetry events for an incident or entity.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="entity_id",
                    description="Entity to search",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="limit",
                    description="Maximum events",
                    type="integer",
                    required=False,
                    default=50,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="search_entities",
            description="Search graph/telemetry entities for an incident.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="query",
                    description="Search string",
                    type="string",
                    required=False,
                    default="",
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="correlate_entities",
            description="Correlate an entity with related entities via events and graph.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="entity_id",
                    description="Entity to correlate",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="investigate_entity",
            description="Deep-dive into a specific entity and compute a risk assessment.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="project_id",
                    description="Project identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="entity_id",
                    description="Entity to investigate",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="trace_attack_path",
            description="Trace attack paths from a source entity using graph data.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="entity_id", description="Source entity", type="string", required=True
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="reconstruct_timeline",
            description="Reconstruct the event timeline for an entity or incident.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="entity_id",
                    description="Entity to focus on",
                    type="string",
                    required=False,
                    default="",
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="calculate_blast_radius",
            description="Calculate the blast radius for an incident.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="compare_baseline",
            description="Compare current entity activity against a baseline.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="entity_id", description="Entity to compare", type="string", required=True
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="rank_candidates",
            description="Rank suspicious candidates for an incident or project.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="project_id",
                    description="Project identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="top_k",
                    description="Number of top candidates",
                    type="integer",
                    required=False,
                    default=5,
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="test_hypothesis",
            description="Test a hypothesis by correlating evidence.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="entity_id", description="Entity to test", type="string", required=True
                ),
                ToolParameter(
                    name="hypothesis",
                    description="Hypothesis statement",
                    type="string",
                    required=False,
                    default="",
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="create_finding",
            description="Create a finding record for a verified conclusion.",
            category="audit",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="statement", description="Finding statement", type="string", required=True
                ),
                ToolParameter(
                    name="confidence",
                    description="Confidence score",
                    type="number",
                    required=False,
                    default=0.0,
                ),
                ToolParameter(
                    name="evidence",
                    description="Evidence references",
                    type="string",
                    required=False,
                    default="",
                ),
            ],
            risk_level="medium",
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="verify_conclusion",
            description="Verify the current mission conclusion against evidence.",
            category="investigation",
            parameters=[
                ToolParameter(
                    name="execution_id",
                    description="Execution identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="project_id",
                    description="Project identifier",
                    type="string",
                    required=False,
                    default="",
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_metrics",
            description="Get overall dashboard metrics.",
            category="investigation",
            parameters=[],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="append_audit_record",
            description="Append a ControlLedger audit record.",
            category="audit",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="action", description="Audit action", type="string", required=True
                ),
                ToolParameter(
                    name="previous_state",
                    description="Previous state",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="new_state",
                    description="New state",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="reason", description="Reason", type="string", required=False, default=""
                ),
                ToolParameter(
                    name="control_mapping",
                    description="Compliance control mapping",
                    type="string",
                    required=False,
                    default="NIST.RESPOND.AUDIT",
                ),
            ],
            risk_level="high",
            requires_confirmation=True,
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="verify_audit_chain",
            description="Verify the audit hash chain for an incident or globally.",
            category="audit",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier (optional)",
                    type="string",
                    required=False,
                    default="",
                ),
            ],
            risk_level="low",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="seal_incident",
            description="Seal an incident and append a final audit record.",
            category="audit",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="critical",
            requires_confirmation=True,
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="threat_intelligence_lookup",
            description="Look up threat intelligence for an indicator.",
            category="intelligence",
            parameters=[
                ToolParameter(
                    name="indicator",
                    description="IP, domain, hash, CVE, or technique",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="indicator_type",
                    description="Type of indicator",
                    type="string",
                    required=False,
                    default="auto",
                    enum=["auto", "ip", "domain", "hash", "cve", "technique"],
                ),
            ],
            risk_level="low",
            provider="tavily",
            fallback_provider="anvaya",
            idempotent=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="trigger_automation",
            description="Trigger a post-investigation workflow automation.",
            category="automation",
            parameters=[
                ToolParameter(
                    name="workflow", description="Workflow name", type="string", required=True
                ),
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="payload",
                    description="Workflow payload",
                    type="object",
                    required=False,
                    default={},
                ),
            ],
            risk_level="high",
            provider="n8n",
            fallback_provider="anvaya",
            requires_confirmation=True,
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="notify_via_email",
            description="Send a notification email to the SOC team or a stakeholder.",
            category="notification",
            parameters=[
                ToolParameter(
                    name="to",
                    description="Recipient email address",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="subject",
                    description="Email subject",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="body",
                    description="Email body (plain text)",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="high",
            provider="gmail",
            fallback_provider="anvaya",
            requires_confirmation=True,
            idempotent=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="lyzr_propose_rule",
            description="Use Lyzr to propose a detection rule from incident evidence.",
            category="intelligence",
            parameters=[
                ToolParameter(
                    name="incident_id",
                    description="Incident identifier",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="attack_family",
                    description="Attack family to focus the rule on",
                    type="string",
                    required=True,
                ),
            ],
            risk_level="medium",
            provider="lyzr",
            fallback_provider="anvaya",
            requires_confirmation=False,
            idempotent=True,
        )
    )

    registry.register(
        ToolDefinition(
            name="spawn_subagent",
            description="Spawn a Devin-like subagent to handle a focused subtask.",
            category="agentic",
            parameters=[
                ToolParameter(
                    name="task",
                    description="The subtask to delegate",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="profile_id",
                    description="Subagent profile: explore, general, or tester",
                    type="string",
                    required=False,
                    default="general",
                    enum=["explore", "general", "tester"],
                ),
                ToolParameter(
                    name="mode",
                    description="foreground (blocking) or background (parallel)",
                    type="string",
                    required=False,
                    default="background",
                    enum=["foreground", "background"],
                ),
                ToolParameter(
                    name="parent_execution_id",
                    description="Parent execution ID (defaults to current execution)",
                    type="string",
                    required=False,
                    default="",
                ),
                ToolParameter(
                    name="incident_id",
                    description="Incident context for the subagent",
                    type="string",
                    required=False,
                    default="",
                ),
            ],
            risk_level="medium",
            idempotent=False,
        )
    )

    registry.register(
        ToolDefinition(
            name="run_tests",
            description="Run a pytest test path and report the result.",
            category="automation",
            parameters=[
                ToolParameter(
                    name="test_path",
                    description="Test path relative to project root (e.g. tests/test_agent.py)",
                    type="string",
                    required=False,
                    default="tests",
                ),
            ],
            risk_level="medium",
            idempotent=True,
        )
    )

    return registry
