"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { RefreshCw, X } from "lucide-react";
import { Tile } from "@/components/tiles/tile-shell";
import { ProjectGuard } from "@/components/project-guard";
import { Chip, Mono, Tabs } from "@/components/primitives";
import { useProjectArtifactLatest } from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { cn } from "@/lib/utils";
import { BuildTimeline, BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { useArtifactSource } from "@/lib/build";
import { useTheme } from "@/components/theme-provider";

type Impact = {
  id: string;
  incident_id: string;
  category?: string;
  affected_assets?: string[];
  affected_count?: number;
  severity?: string;
};
type ImpactsPayload = { impacts?: Impact[] };

const SEV_TONE: Record<string, "critical" | "warning" | "accent" | "muted"> = {
  critical: "critical", high: "warning", medium: "accent", low: "muted",
};

export default function ImpactGalleryTile() {
  return (
    <Tile id="impact-gallery" title="IMPACT TREE GALLERY" subtitle="project-derived affected-asset archive">
      <ProjectGuard>
        <ImpactGalleryBody />
      </ProjectGuard>
    </Tile>
  );
}

function ImpactGalleryBody() {
  const params = useSearchParams();
  const buildId = params.get("build") || "";
  const build = useArtifactBuild(buildId || undefined);

  const { state, dispatch } = useAnvaya();
  const projectId = state.activeProjectId || "";
  const { data, isLoading, isError, isFetching, refetch } = useProjectArtifactLatest(projectId, "impacts");
  const payload = data?.payload as ImpactsPayload | null | undefined;

  const { data: impacts, isBuilding } = useArtifactSource<Impact>(
    build,
    payload?.impacts,
    isLoading,
    isError,
    "impacts"
  );
  const categories = useMemo(() => ["ALL", ...Array.from(new Set(impacts.map((impact) => impact.category).filter(Boolean) as string[]))], [impacts]);
  const [localFilter, setLocalFilter] = useState("ALL");
  const filter = categories.includes(state.impact.filter) ? state.impact.filter : localFilter;
  const visible = filter === "ALL" ? impacts : impacts.filter((impact) => impact.category === filter);
  const selected = impacts.find((impact) => impact.id === state.impact.selected) || null;
  const setFilter = (value: string) => {
    setLocalFilter(value);
    dispatch({ type: "patch", path: "impact", value: { filter: value } });
  };

  const showBuildShell = isBuilding;

  return (
    <>
      {build && <BuildStatus state={build} />}
      {showBuildShell ? (
        <div className="bg-grid flex h-full flex-col gap-3 p-3">
          <div className="flex h-full gap-3">
            <div className="flex min-w-0 flex-1 flex-col">
              <div className="flex items-center justify-between border-b border-hairline px-4 py-2">
                <Tabs items={categories} value={filter} onChange={setFilter} />
                <Mono className="tabular-nums">{visible.length} of {impacts.length} impacts</Mono>
              </div>
              {selected && (
                <div className="flex items-center gap-3 border-b border-hairline bg-canvas-elevated/70 px-4 py-1.5">
                  <Mono tone="primary">{selected.id}</Mono><Mono>{selected.incident_id}</Mono><Mono>{selected.affected_count ?? selected.affected_assets?.length ?? 0} affected assets</Mono>
                  <button type="button" aria-label="clear selection" onClick={() => dispatch({ type: "patch", path: "impact", value: { selected: null } })} className="ml-auto text-muted hover:text-accent"><X className="h-3 w-3" /></button>
                </div>
              )}
              <div className="min-h-0 flex-1 overflow-auto p-3">
                {visible.length === 0 ? (
                  <ArtifactState message={impacts.length ? `No impacts match ${filter}.` : "Building impact gallery workspace..."} />
                ) : (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    {visible.map((impact) => <ImpactCard key={impact.id} impact={impact} selected={impact.id === state.impact.selected} onSelect={() => dispatch({ type: "patch", path: "impact", value: { selected: impact.id } })} />)}
                  </div>
                )}
              </div>
              <div className="border-t border-hairline bg-canvas-elevated/50 px-4 py-2"><Mono>showing {visible.length} of {impacts.length} — filter: {filter}</Mono></div>
            </div>
            <div className="flex h-full w-[320px] shrink-0 flex-col gap-3">
              {build && <BuildTimeline state={build} />}
            </div>
          </div>
        </div>
      ) : isLoading && impacts.length === 0 ? (
        <ArtifactState message="Loading project impacts..." />
      ) : isError || (!payload && impacts.length === 0) ? (
        <ArtifactState message="No impacts artifact has been generated for this project." />
      ) : (
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-hairline px-4 py-2">
            <Tabs items={categories} value={filter} onChange={setFilter} />
            <button type="button" onClick={() => refetch()} disabled={isFetching} className="flex items-center gap-2 border border-hairline px-2.5 py-1 font-mono text-[9px] uppercase tracking-wider text-muted hover:border-accent/40 hover:text-accent disabled:opacity-50">
              <RefreshCw className={cn("h-3 w-3", isFetching && "animate-spin")} /> refresh artifact
            </button>
          </div>
          {selected && (
            <div className="flex items-center gap-3 border-b border-hairline bg-canvas-elevated/70 px-4 py-1.5">
              <Mono tone="primary">{selected.id}</Mono><Mono>{selected.incident_id}</Mono><Mono>{selected.affected_count ?? selected.affected_assets?.length ?? 0} affected assets</Mono>
              <button type="button" aria-label="clear selection" onClick={() => dispatch({ type: "patch", path: "impact", value: { selected: null } })} className="ml-auto text-muted hover:text-accent"><X className="h-3 w-3" /></button>
            </div>
          )}
          <div className="min-h-0 flex-1 overflow-auto p-3">
            {visible.length === 0 ? (
              <ArtifactState message={impacts.length ? `No impacts match ${filter}.` : "This impacts artifact contains no impact records."} />
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {visible.map((impact) => <ImpactCard key={impact.id} impact={impact} selected={impact.id === state.impact.selected} onSelect={() => dispatch({ type: "patch", path: "impact", value: { selected: impact.id } })} />)}
              </div>
            )}
          </div>
          <div className="border-t border-hairline bg-canvas-elevated/50 px-4 py-2"><Mono>showing {visible.length} of {impacts.length} — filter: {filter}</Mono></div>
        </div>
      )}
    </>
  );
}

function ImpactCard({ impact, selected, onSelect }: { impact: Impact; selected: boolean; onSelect: () => void }) {
  const { theme } = useTheme();
  const t = theme.tokens;
  const assets = impact.affected_assets || [];
  const shown = assets.slice(0, 12);
  return (
    <button type="button" aria-pressed={selected} onClick={onSelect} className={cn("row-interactive flex min-h-52 flex-col border bg-canvas-panel/60 p-3 text-left", selected ? "glow-accent border-accent/60" : "border-hairline hover:border-hairline-bright")}>
      <div className="flex items-start justify-between gap-2">
        <div><div className="font-mono text-[10px] text-primary">{impact.id}</div><div className="font-mono text-[9px] text-muted">{impact.incident_id}</div></div>
        <Chip tone={SEV_TONE[impact.severity || ""] || "muted"}>{impact.severity || "—"}</Chip>
      </div>
      <svg viewBox="0 0 100 90" className="my-2 min-h-28 w-full flex-1" role="img" aria-label={`${impact.incident_id} affected asset tree`}>
        {shown.map((asset, index) => {
          const angle = (index / Math.max(shown.length, 1)) * Math.PI * 2 - Math.PI / 2;
          const x = 50 + Math.cos(angle) * 35;
          const y = 45 + Math.sin(angle) * 32;
          return <g key={`${asset}-${index}`}><line x1="50" y1="45" x2={x} y2={y} stroke={t.accent} strokeWidth="0.6" opacity="0.55" /><circle cx={x} cy={y} r="1.8" fill={t.bg} stroke={t.accent} strokeWidth="0.7" /></g>;
        })}
        <circle cx="50" cy="45" r="2.6" fill={t.accent} />
      </svg>
      <div className="flex items-center justify-between font-mono text-[9px] uppercase tracking-wider text-muted"><span>{impact.category || "uncategorized"}</span><span>{impact.affected_count ?? assets.length} affected</span></div>
    </button>
  );
}

function ArtifactState({ message }: { message: string }) {
  return <div className="flex h-full min-h-32 items-center justify-center p-8 text-center"><Mono className="text-muted">{message}</Mono></div>;
}
