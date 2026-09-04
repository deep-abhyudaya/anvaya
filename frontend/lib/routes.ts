
export const ARTIFACT_ROUTE_MAP: Record<string, string> = {
  orbits: "sentinel",
  incidents: "sentinel",
  reach: "pathfinder",
  segments: "pathfinder",
  ecosystem: "pathfinder",
  arbor: "sentinel",
  impacts: "responder",
  replay: "responder",
  arena: "responder",
  trophy_wall: "auditor",
  ledger: "auditor",
};

export function routeForArtifactType(artifactType: string): string {
  return ARTIFACT_ROUTE_MAP[artifactType] ?? artifactType;
}
