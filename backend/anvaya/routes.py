"""Artifact type → frontend route mapping.

This is the single source of truth for where each high-level artifact type is
rendered in the Next.js dashboard. The backend uses it for navigation events and
can embed it in build-event payloads; the frontend mirrors the same map in
`frontend/lib/routes.ts`.
"""

from __future__ import annotations

ARTIFACT_ROUTE_MAP: dict[str, str] = {
    "orbits": "risk-orbits",
    "reach": "reach-board",
    "segments": "segments",
    "arbor": "",
    "trophy_wall": "trophy-wall",
    "arena": "nerve-arena",
    "ecosystem": "threat-ecosystem",
    "incidents": "incidents",
    "impacts": "impact-gallery",
    "replay": "miss-replay",
    "ledger": "ledger",
}


def route_for_artifact_type(artifact_type: str) -> str:
    """Return the frontend route for an artifact type, without leading slash."""
    return ARTIFACT_ROUTE_MAP.get(artifact_type, artifact_type)
