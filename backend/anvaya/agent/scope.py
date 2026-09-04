"""Scope enforcement for agent execution.

Parses user objectives to extract explicit artifact/action constraints and
enforces them throughout replanning. Prevents the model from hallucinating
scope expansions.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


class ScopeConstraints(BaseModel):
    """Explicit constraints derived from the user objective."""

    allowed_artifacts: list[str] = Field(default_factory=list)
    mode: str = "all"
    raw_objective: str = ""

    def allows(self, artifact_type: str) -> bool:
        """Check whether an artifact type is within scope."""
        if self.mode == "all":
            return True
        return artifact_type in self.allowed_artifacts

    def filter_artifacts(self, requested: list[str]) -> list[str]:
        """Filter a requested artifact list against scope constraints."""
        if self.mode == "all":
            return requested
        return [a for a in requested if a in self.allowed_artifacts]

    def to_constraint_strings(self) -> list[str]:
        """Return human-readable constraint strings for mission state."""
        if self.mode == "all":
            return ["scope:all_artifacts_allowed"]
        return [f"only:{a}" for a in self.allowed_artifacts]


_ARTIFACT_ALIASES: dict[str, str] = {
    "orbit": "orbits",
    "orbits": "orbits",
    "risk orbit": "orbits",
    "risk orbits": "orbits",
    "reach": "reach",
    "reach board": "reach",
    "reachability": "reach",
    "segment": "segments",
    "segments": "segments",
    "arena": "arena",
    "nerve arena": "arena",
    "ecosystem": "ecosystem",
    "threat ecosystem": "ecosystem",
    "trophy": "trophy_wall",
    "trophy wall": "trophy_wall",
    "trophies": "trophy_wall",
    "replay": "replay",
    "miss replay": "replay",
    "arbor": "arbor",
    "decision arbor": "arbor",
    "impact": "impacts",
    "impacts": "impacts",
    "impact gallery": "impacts",
    "incident": "incidents",
    "incidents": "incidents",
    "ledger": "ledger",
    "control ledger": "ledger",
    "everything": "all",
    "all": "all",
}

_ONLY_PATTERN = re.compile(
    r"\b(?:only|just|solely|exclusively)\b",
    re.IGNORECASE,
)

_AND_PATTERN = re.compile(r"\band\b", re.IGNORECASE)


def parse_scope(objective: str) -> ScopeConstraints:
    """Parse the user objective to extract scope constraints.

    Examples:
        "Create only orbits"           -> ScopeConstraints(allowed=["orbits"], mode="only")
        "Create orbits and reach"       -> ScopeConstraints(allowed=["orbits", "reach"], mode="explicit")
        "Create everything"             -> ScopeConstraints(mode="all")
        "Generate all artifacts"        -> ScopeConstraints(mode="all")
        "Build the risk orbits"         -> ScopeConstraints(allowed=["orbits"], mode="explicit")
        "Investigate incident INC-2214" -> ScopeConstraints(mode="all")  # non-artifact objective
    """
    objective_lower = objective.lower().strip()
    constraints = ScopeConstraints(raw_objective=objective)

    if any(kw in objective_lower for kw in ("everything", "all artifact", "all views")):
        constraints.mode = "all"
        return constraints

    found: list[str] = []
    for alias, canonical in sorted(_ARTIFACT_ALIASES.items(), key=lambda x: -len(x[0])):
        if canonical == "all":
            continue
        if alias in objective_lower:
            if canonical not in found:
                found.append(canonical)

    if not found:
        constraints.mode = "all"
        return constraints

    has_only = bool(_ONLY_PATTERN.search(objective_lower))

    constraints.allowed_artifacts = found
    constraints.mode = "only" if has_only else "explicit"
    return constraints


def enforce_scope(
    tool_name: str,
    inputs: dict[str, Any],
    constraints: ScopeConstraints,
) -> dict[str, Any]:
    """Filter tool inputs against scope constraints.

    For artifact-management tools, filters ``requested_artifacts`` to only
    include types permitted by the scope. Returns the (possibly modified)
    inputs dict.
    """
    if constraints.mode == "all":
        return inputs

    if tool_name not in ("manage_artifacts", "generate_artifacts"):
        return inputs

    requested = inputs.get("requested_artifacts")
    if not isinstance(requested, list):
        return inputs

    filtered = constraints.filter_artifacts(requested)
    if not filtered:
        filtered = list(constraints.allowed_artifacts)

    return {**inputs, "requested_artifacts": filtered}
