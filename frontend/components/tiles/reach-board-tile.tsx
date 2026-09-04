"use client";

import React from "react";
import { useSearchParams } from "next/navigation";
import { Tile } from "./tile-shell";
import { ProjectGuard } from "@/components/project-guard";
import { Bar, Chip, Mono, Segmented } from "@/components/primitives";
import { useProjectArtifactLatest } from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { cn } from "@/lib/utils";
import { BuildTimeline, BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { useArtifactSource } from "@/lib/build";

const STATE_TONE: Record<string, "warning" | "accent" | "muted"> = {
  COMPROMISED: "warning",
  CRITICAL: "warning",
  REACHABLE: "accent",
  NEUTRALIZED: "muted",
};

const ACCENT: Record<string, string> = {
  COMPROMISED: "bg-warning",
  CRITICAL: "bg-accent",
  REACHABLE: "bg-accent",
  NEUTRALIZED: "bg-muted",
};

type ReachAsset = {
  id: string;
  name?: string;
  state?: string;
  hops?: number;
  attackScore?: number;
  defenseScore?: number;
  adjacent?: string[];
  reachable_count?: number;
};

type ReachPayload = { items?: ReachAsset[] };

export default function ReachBoardTile() {
  const params = useSearchParams();
  const buildId = params.get("build") || "";
  const build = useArtifactBuild(buildId || undefined);

  const { state, dispatch } = useAnvaya();
  const mode = state.reach.mode;
  const activeProjectId = state.activeProjectId || "";
  const { data: projectReach, isLoading, isError } = useProjectArtifactLatest(activeProjectId, "reach");

  const payload = (projectReach?.payload as ReachPayload | null | undefined) || null;
  const { data: assets, isBuilding } = useArtifactSource<ReachAsset>(
    build,
    payload?.items,
    isLoading,
    isError,
    "reach"
  );
  const reachable = assets.filter((a: ReachAsset) => a.state === "REACHABLE").length;
  const neutralized = assets.filter((a: ReachAsset) => a.state === "NEUTRALIZED").length;

  const ranked = React.useMemo(
    () =>
      [...assets].sort((a: ReachAsset, b: ReachAsset) =>
        mode === "ATTACK" ? (b.attackScore || 0) - (a.attackScore || 0) : (b.defenseScore || 0) - (a.defenseScore || 0)
      ),
    [assets, mode]
  );

  const selected = assets.find((a: ReachAsset) => a.id === state.reach.selected) ?? null;

  if (isLoading && !isBuilding && assets.length === 0 && !payload) {
    return (
      <Tile id="reach-board" title="REACH DRAFT BOARD" subtitle="ranked asset reachability — attacker and defender viewpoints">
        <ProjectGuard>
          <div className="flex h-full items-center justify-center">
            <Mono className="text-muted">Loading...</Mono>
          </div>
        </ProjectGuard>
      </Tile>
    );
  }

  const showBuildShell = isBuilding;

  return (
    <Tile
      id="reach-board"
      title="REACH DRAFT BOARD"
      subtitle="ranked asset reachability — attacker and defender viewpoints"
      center={
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
          REACHABLE: <span className="tabular-nums text-accent">{reachable}</span> — NEUTRALIZED:{" "}
          <span className="tabular-nums text-secondary">{neutralized}</span>
        </span>
      }
      right={
        <Segmented
          items={["ATTACK", "DEFENSE"]}
          value={mode}
          onChange={(v) => dispatch({ type: "patch", path: "reach", value: { mode: v as "ATTACK" | "DEFENSE" } })}
        />
      }
    >
      <ProjectGuard>
        {build && <BuildStatus state={build} />}
        {showBuildShell ? (
          <div className="bg-grid flex h-full gap-3 p-3">
            <div className="relative min-w-0 flex-1 overflow-auto">
              <div className="ml-[100px] max-w-[1050px] py-6 pr-40">
                {assets.length === 0 ? (
                  <ArtifactState message="Building reach board workspace..." />
                ) : (
                  ranked.map((asset: ReachAsset, idx: number) => <ReachAssetRow key={asset.id} asset={asset} idx={idx} ranked={ranked} mode={mode} />)
                )}
                {assets.length > 0 && (
                  <div className="mt-4 pl-1 font-mono text-[9px] uppercase tracking-wider text-muted">
                    viewpoint: {mode} —{" "}
                    {mode === "ATTACK" ? "ranked by compromisable impact" : "ranked by neutralization opportunity"}
                  </div>
                )}
              </div>
              {selected && <ReachCallout selected={selected} />}
            </div>
            <div className="flex h-full w-[320px] shrink-0 flex-col gap-3">
              {build && <BuildTimeline state={build} />}
            </div>
          </div>
        ) : (
          <div className="bg-grid relative h-full overflow-auto">
            <div className="ml-[100px] max-w-[1050px] py-6 pr-40">
              {ranked.map((asset: ReachAsset, idx: number) => <ReachAssetRow key={asset.id} asset={asset} idx={idx} ranked={ranked} mode={mode} />)}
              <div className="mt-4 pl-1 font-mono text-[9px] uppercase tracking-wider text-muted">
                viewpoint: {mode} —{" "}
                {mode === "ATTACK" ? "ranked by compromisable impact" : "ranked by neutralization opportunity"}
              </div>
            </div>
            {selected && <ReachCallout selected={selected} />}
          </div>
        )}
      </ProjectGuard>
    </Tile>
  );
}

function ReachAssetRow({
  asset,
  idx,
  ranked,
  mode,
}: {
  asset: ReachAsset;
  idx: number;
  ranked: ReachAsset[];
  mode: "ATTACK" | "DEFENSE";
}) {
  const { state, dispatch } = useAnvaya();
  const score = mode === "ATTACK" ? asset.attackScore : asset.defenseScore;
  const isSelected = asset.id === state.reach.selected;
  const isLast = idx === ranked.length - 1;
  const dimmed = asset.state === "NEUTRALIZED";
  return (
    <button
      key={asset.id}
      type="button"
      aria-pressed={isSelected}
      onClick={() => dispatch({ type: "patch", path: "reach", value: { selected: asset.id } })}
      className={cn(
        "row-interactive relative mb-3 flex min-h-[86px] w-full items-center gap-5 border border-hairline bg-canvas-panel/60 px-5 text-left hover:border-hairline-bright",
        dimmed && "opacity-45",
        isSelected && "border-accent glow-accent",
        isLast && "w-[calc(100%+120px)] translate-x-[120px]"
      )}
    >
      <span className={cn("absolute bottom-0 left-0 top-0 w-[3px]", ACCENT[asset.state || ""] || "bg-muted")} />
      <span className="w-10 shrink-0 font-mono text-[28px] tabular-nums text-muted">
        {String(idx + 1).padStart(2, "0")}
      </span>
      <div className="w-56 shrink-0">
        <div className="font-mono text-[15px] text-primary">{asset.name || "—"}</div>
        <div className="mt-1 flex items-center gap-2">
          <Chip tone={STATE_TONE[asset.state || ""] || "muted"}>{asset.state || "—"}</Chip>
          <Mono className="tabular-nums">{asset.hops || 0} hops</Mono>
        </div>
      </div>
      <div className="flex flex-1 flex-col gap-1.5">
        <Mono className="text-[8px]">{mode === "ATTACK" ? "impact score" : "neutralization score"}</Mono>
        <Bar value={score || 0} warning={asset.state === "COMPROMISED"} />
      </div>
      <span
        className={cn(
          "w-12 shrink-0 text-right font-mono text-[13px] tabular-nums",
          asset.state === "COMPROMISED" ? "text-warning" : "text-primary"
        )}
      >
        {(score || 0).toFixed(2)}
      </span>
    </button>
  );
}

function ReachCallout({ selected }: { selected: ReachAsset }) {
  return (
    <div className="absolute right-10 top-[38%] hidden xl:block">
      <div className="mb-1 font-mono text-[10px] tracking-[0.3em] text-accent/30">{">>>"}</div>
      <div className="mb-2 w-16 border-t border-dashed border-accent/40" />
      <div className="border border-dashed border-accent/40 bg-canvas-panel/60 px-3 py-2">
        <Mono className="mb-1 block text-[8px]">adjacent to:</Mono>
        <div className="font-mono text-[11px] text-accent">{(selected as ReachAsset).adjacent?.join(", ") || "—"}</div>
      </div>
    </div>
  );
}

function ArtifactState({ message }: { message: string }) {
  return <div className="flex h-full items-center justify-center p-8 text-center"><Mono className="text-muted">{message}</Mono></div>;
}
