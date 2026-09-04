"use client";

import { BuildStatus, BuildTimeline } from "./build-timeline";
import { useArtifactBuild } from "./use-artifact-build";

export function BuildPanel({
  executionId,
}: {
  executionId: string;
}) {
  const build = useArtifactBuild(executionId);

  if (!build) return null;

  return (
    <div className="space-y-2 border-b border-hairline bg-canvas-subtle p-4">
      <BuildStatus state={build} />
      {build.artifacts.length > 0 && <BuildTimeline state={build} />}
    </div>
  );
}
