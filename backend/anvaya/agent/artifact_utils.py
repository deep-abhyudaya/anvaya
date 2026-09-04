"""Artifact action/type inference helpers shared by the agent loop and orchestrator."""

from __future__ import annotations

import re


def infer_artifact_action(objective: str) -> str:
    """Determine whether the user wants to generate, regenerate, or delete artifacts."""
    obj = objective.lower()
    if re.search(r"\b(delete|clear|remove|wipe)\b", obj):
        return "delete"
    if re.search(r"\b(regenerate|re-generate|regen|redo)\b", obj):
        return "regenerate"
    return "generate"


def infer_artifact_types(objective: str) -> list[str]:
    """Map an objective to the concrete artifact types the user wants to operate on."""
    obj = objective.lower()
    requested: list[str] = []
    type_keywords: dict[str, list[str]] = {
        "orbits": ["orbit", "orbits", "risk orbit"],
        "segments": ["segment", "segments", "network segment"],
        "reach": ["reach", "reachability", "reach board"],
        "arena": ["arena", "nerve arena"],
        "ecosystem": ["ecosystem", "threat ecosystem"],
        "trophy_wall": ["trophy_wall", "trophy", "trophies", "trophy wall"],
        "replay": ["replay", "miss-replay"],
        "arbor": ["arbor", "threat arbor", "tree"],
        "impacts": ["impact", "impacts", "impact gallery"],
        "incidents": ["incident", "incidents"],
        "ledger": ["ledger", "audit", "audit record"],
    }

    for artifact_type, keywords in type_keywords.items():
        if any(_keyword_present(obj, k) for k in keywords):
            requested.append(artifact_type)

    if not requested:
        if re.search(r"\ball\b", obj) or re.search(
            r"\b(generate|regenerate|delete|clear|remove|wipe)\b", obj
        ):
            return ["all"]

    return requested


def _keyword_present(text: str, keyword: str) -> bool:
    """Match a keyword as a whole-phrase boundary to avoid substring false positives."""
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return bool(re.search(pattern, text))
