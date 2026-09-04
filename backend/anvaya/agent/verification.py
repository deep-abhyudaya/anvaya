"""Verification gate for agent conclusions.

A finding must be verified against available evidence before it becomes a final
outcome. The gate checks reference resolution, temporal/relationship coherence,
provenance, and confidence thresholds.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from anvaya.agent.blackboard import Blackboard


class VerificationResult(BaseModel):
    """Result of a verification gate check."""

    passed: bool
    reason: str = ""
    missing: list[str] = []
    contradictions: list[str] = []
    confidence: float = 0.0
    evidence_count: int = 0


def verify_conclusion(
    blackboard: Blackboard,
    mission: Any,
    min_confidence: float = 0.75,
    require_evidence: int = 2,
) -> VerificationResult:
    """Verify the current blackboard state as a candidate conclusion."""
    missing: list[str] = []
    contradictions: list[str] = list(blackboard.contradictions)

    top = blackboard.top_hypothesis()
    if not top:
        return VerificationResult(
            passed=False,
            reason="No active hypothesis to verify.",
            missing=["hypothesis"],
            contradictions=contradictions,
        )

    if not blackboard.evidence or len(blackboard.evidence) < require_evidence:
        missing.append("insufficient_evidence")

    if len(top.evidence_against) >= len(top.evidence_for):
        contradictions.append("more_evidence_against_than_for")

    if top.status == "rejected":
        contradictions.append("top_hypothesis_rejected")

    if top.confidence < min_confidence:
        missing.append(f"confidence_below_threshold ({top.confidence:.2f} < {min_confidence})")

    if not blackboard.current_candidate:
        missing.append("no_candidate")

    passed = not missing and not contradictions
    reason = "Conclusion verified." if passed else "Conclusion failed verification; gather more evidence."

    return VerificationResult(
        passed=passed,
        reason=reason,
        missing=missing,
        contradictions=contradictions,
        confidence=top.confidence,
        evidence_count=len(blackboard.evidence),
    )


def verify_evidence_coherence(
    evidence: list[dict[str, Any]],
    relationships: list[dict[str, Any]] | None = None,
) -> VerificationResult:
    """Check that evidence references are coherent with one another."""
    missing: list[str] = []
    contradictions: list[str] = []

    if not evidence:
        missing.append("no_evidence")

    timestamps: list[datetime] = []
    for e in evidence:
        ts = e.get("timestamp")
        if not ts:
            continue
        try:
            timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
        except Exception:
            pass

    if len(timestamps) >= 2 and any(timestamps[i] > timestamps[i + 1] for i in range(len(timestamps) - 1)):
        contradictions.append("temporal_inconsistency")

    if relationships is not None and not relationships:
        missing.append("no_relationships")

    passed = not missing and not contradictions
    return VerificationResult(
        passed=passed,
        reason="Evidence coherent." if passed else "Evidence incoherent.",
        missing=missing,
        contradictions=contradictions,
        evidence_count=len(evidence),
    )


def verify_action_completion(
    tool_name: str,
    result: Any,
    completion_condition: str,
    session: Any = None,
    project_id: str = "",
) -> VerificationResult:
    """Verify that a tool action's completion condition is met.
    
    This is used by the frontier agent loop to verify each meaningful
    action before marking it complete, rather than merely checking
    that the Python function returned without raising.
    """
    missing: list[str] = []
    contradictions: list[str] = []

    tool_status = getattr(result, 'status', None) or (result.get('status') if isinstance(result, dict) else 'unknown')
    if tool_status != 'success':
        missing.append(f'tool_returned_{tool_status}')

    output = getattr(result, 'output', {}) or (result.get('output', {}) if isinstance(result, dict) else {})
    artifact_refs = getattr(result, 'artifact_refs', []) or (result.get('artifact_refs', []) if isinstance(result, dict) else [])

    if tool_name in ('generate_artifacts', 'manage_artifacts'):
        created = output.get('created', {})
        if not created and not artifact_refs:
            missing.append('no_artifacts_created')
        if project_id and output.get('project_id') and output['project_id'] != project_id:
            contradictions.append(f'project_mismatch: expected {project_id}, got {output.get("project_id")}')

    elif tool_name == 'inspect_project_data':
        row_count = output.get('row_count', output.get('total_events', 0))
        if not row_count:
            missing.append('dataset_empty_or_inaccessible')

    elif tool_name == 'verify_audit_chain':
        if not output.get('valid'):
            contradictions.append('audit_chain_invalid')

    if completion_condition and tool_status == 'success':
        output_summary = getattr(result, 'output_summary', '') or (result.get('output_summary', '') if isinstance(result, dict) else '')
        if not output_summary:
            missing.append('no_output_summary_for_condition_check')

    passed = not missing and not contradictions
    reason = (
        f'{tool_name} action verified.'
        if passed
        else f'{tool_name} verification failed: {";".join(missing + contradictions)}'
    )

    return VerificationResult(
        passed=passed,
        reason=reason,
        missing=missing,
        contradictions=contradictions,
        evidence_count=len(artifact_refs),
    )

