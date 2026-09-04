"use client";

import Link from "next/link";
import { ArtifactBuildItem, ArtifactBuildState } from "@/lib/build";
import { cn } from "@/lib/utils";
import AIArtifact from "@/components/smoothui/ai-artifact";

export function BuildStatus({ state }: { state: ArtifactBuildState }) {
  const completed = state.artifacts.filter((a) => a.status === "complete").length;
  const total = state.totalArtifacts || state.artifacts.length;
  const target = state.target || "artifact";
  const isReady = state.status === "completed" && completed === total && total > 0;
  const heading = isReady
    ? state.phase || `${target.charAt(0).toUpperCase() + target.slice(1)} is ready`
    : state.activeName || state.phase || "Building...";

  return (
    <div className="flex flex-col gap-2 rounded border border-hairline bg-canvas-subtle p-4">
      <div className="font-mono text-[10px] uppercase tracking-widest text-muted">
        {isReady ? "READY" : "BUILDING"}
      </div>
      <div className="text-sm font-medium text-primary">{heading}</div>
      {!isReady && (state.activeLiveReason || state.activePurpose || state.activeBuilding) && (
        <div className="text-xs text-secondary">
          {state.activeLiveReason || state.activePurpose || state.activeBuilding}
        </div>
      )}
      {state.activeElementReason && !isReady && (
        <div className="font-mono text-[10px] text-accent">
          {state.activeElementReason}
        </div>
      )}
      {total > 0 && (
        <div className="font-mono text-[10px] text-muted">
          {completed} / {total} artifacts complete
        </div>
      )}
    </div>
  );
}

export function BuildTimeline({ state }: { state: ArtifactBuildState }) {
  return (
    <div className="flex h-full flex-col gap-3 overflow-auto p-4">
      <div className="mt-2 space-y-2">
        {state.artifacts.map((artifact) => (
          <ArtifactRow
            key={artifact.index}
            artifact={artifact}
            active={artifact.index === state.currentIndex}
            target={state.target}
          />
        ))}
        {state.artifacts.length === 0 && (
          <div className="font-mono text-[10px] text-muted">
            Waiting for first artifact...
          </div>
        )}
      </div>
    </div>
  );
}

function ArtifactRow({
  artifact,
  active,
  target,
}: {
  artifact: ArtifactBuildItem;
  active: boolean;
  target: string;
}) {
  const stepId = artifact.stepId || `${target}-${artifact.artifactType}-${artifact.index}`;
  const isRealLink = typeof artifact.route === "string" && artifact.route.startsWith("/");

  const preview = isRealLink ? (
    <Link href={artifact.route} className="text-accent hover:underline">
      Open {artifact.artifactType} → {artifact.name}
    </Link>
  ) : (
    <div className="text-secondary text-[11px]">{artifact.purpose}</div>
  );

  return (
    <div
      id={`build-el-${target}-${artifact.index}`}
      data-step-id={stepId}
      className={cn(
        "transition-colors",
        active ? "opacity-100" : "opacity-80"
      )}
    >
      <AIArtifact
        title={`${String(artifact.index + 1).padStart(2, "0")} ${artifact.name}`}
        preview={preview}
        code={JSON.stringify(artifact, null, 2)}
        copyText={JSON.stringify(artifact, null, 2)}
        className={active ? "border-accent/30" : undefined}
      />
    </div>
  );
}
