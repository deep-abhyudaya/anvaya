"""Operational message generation for agent streams.

Messages are short, observable, and tied to execution state. They never
reveal hidden reasoning, system prompts, or chain-of-thought.
"""

from __future__ import annotations

from anvaya.agent.profiles import AgentProfile


class MessageGenerator:
    """Generate concise operational messages for the agent stream."""

    def __init__(self, profile: AgentProfile):
        self.profile = profile

    def start(self, objective: str, incident_id: str) -> str:
        if self.profile.id == "pathfinder":
            return f"Mapping the attack path for {incident_id}."
        if self.profile.id == "responder":
            return f"Assessing response options for {incident_id}."
        if self.profile.id == "auditor":
            return f"Beginning evidence review for {incident_id}."
        return f"I'll investigate {incident_id} and run the ANVAYA tool chain."

    def plan_created(self, steps: list[str]) -> str:
        if self.profile.id == "auditor":
            return "I'll proceed through the evidence and verification steps."
        if self.profile.id == "pathfinder":
            return f"Plan: trace the path through {len(steps)} graph steps."
        return f"Plan created with {len(steps)} steps. Starting with context."

    def before_tool(self, tool_name: str, state: dict) -> str:
        return _BEFORE_TEMPLATES.get(self.profile.id, {}).get(
            tool_name, _before_default(tool_name, self.profile)
        )

    def after_tool(
        self, tool_name: str, result_summary: str, status: str, artifact_count: int
    ) -> str:
        if status == "failure":
            return (
                f"{self._tool_label(tool_name)} did not succeed. "
                "I'll record the result and continue."
            )
        if artifact_count:
            return f"{self._tool_label(tool_name)} complete. Created {artifact_count} artifact(s)."
        return f"{self._tool_label(tool_name)} complete: {result_summary}."

    def fallback(self, provider: str, fallback: str) -> str:
        if self.profile.id == "auditor":
            return (
                f"{provider} is unavailable. I'll use the {fallback} fallback "
                "and label the result clearly."
            )
        return f"{provider} unavailable. Using {fallback} fallback."

    def complete(self, success: int, failed: int) -> str:
        if failed:
            return (
                f"Investigation finished. {success} steps succeeded, "
                f"{failed} failed. Artifacts are linked below."
            )
        return "Investigation complete. All steps succeeded and the incident is sealed."

    def _tool_label(self, tool_name: str) -> str:
        return _LABELS.get(tool_name, tool_name.replace("_", " ").title())


_LABELS: dict[str, str] = {
    "get_incident": "Incident context",
    "get_telemetry": "Telemetry",
    "inspect_detection": "Detection inspection",
    "run_sentinel_trace": "Sentinel backtrack",
    "confirm_ground_truth": "Ground truth",
    "propose_rule": "Rule proposal",
    "validate_rule": "Rule validation",
    "run_replay": "Replay",
    "run_blastscope": "BlastScope",
    "build_or_update_ecosystem": "Ecosystem",
    "run_orbit_analysis": "Orbit analysis",
    "run_reachability": "Reachability",
    "run_segment_analysis": "Segment analysis",
    "run_what_if": "What-If",
    "append_audit_record": "Audit record",
    "verify_audit_chain": "Audit verification",
    "seal_incident": "Seal",
    "threat_intelligence_lookup": "Threat intelligence",
    "trigger_automation": "Automation",
}


_BEFORE_TEMPLATES: dict[str, dict[str, str]] = {
    "sentinel": {
        "get_incident": "I'll start with the incident context.",
        "get_telemetry": "High-severity lateral-movement incident found. "
        "I'll inspect the telemetry next.",
        "run_sentinel_trace": "The sequence has a suspicious remote connection "
        "followed by lateral movement. I'll trace the miss.",
        "propose_rule": "I found the evidence needed to reproduce the missed detection.",
        "validate_rule": "The replay is ready. I'll verify the patched detector.",
        "run_replay": "The rule is validated. I'll replay the identical attack.",
        "run_blastscope": "The replay caught the scenario after the rule update. "
        "I'll assess downstream exposure.",
        "run_what_if": "The blast radius is calculated. I'll evaluate the counterfactual risk.",
        "append_audit_record": "Results are ready. I'll append an audit record.",
        "verify_audit_chain": "I'll verify the audit hash chain before sealing.",
        "seal_incident": "The audit chain is valid. I'll seal the incident.",
    },
    "pathfinder": {
        "run_blastscope": "I'll map the blast radius for this incident.",
        "run_orbit_analysis": "The graph branches through reachable assets. "
        "I'll inspect the highest-risk path.",
        "run_reachability": "I'll check which assets are reachable from the compromise point.",
        "run_segment_analysis": "I'll rank segments by exposure.",
        "update_ecosystem": "I'll build the ecosystem model for this attack path.",
    },
    "responder": {
        "get_incident": "I'll review the incident before proposing any response.",
        "run_blastscope": "I'll assess downstream exposure before taking action.",
        "run_what_if": "I'll evaluate counterfactuals to understand response trade-offs.",
        "trigger_automation": "The detection is validated. "
        "I'll assess response options before any mutation.",
    },
    "auditor": {
        "get_incident": "I'll inspect the incident record.",
        "get_telemetry": "I'll review the telemetry evidence.",
        "inspect_detection": "I'll check the detection run record.",
        "append_audit_record": "I'll append a control-mapped audit record.",
        "verify_audit_chain": "I'll verify the audit chain before sealing.",
        "seal_incident": "The replay result is recorded. I'll verify the chain before sealing.",
    },
}


def _before_default(tool_name: str, profile: AgentProfile) -> str:
    label = _LABELS.get(tool_name, tool_name.replace("_", " ").title())
    if profile.id == "auditor":
        return f"I'll review {label.lower()}."
    if profile.id == "pathfinder":
        return f"Mapping {label.lower()}."
    if profile.id == "responder":
        return f"Checking {label.lower()} before any action."
    return f"I'll run {label.lower()} next."
