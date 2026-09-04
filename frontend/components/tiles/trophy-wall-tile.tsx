"use client";

import { useSearchParams } from "next/navigation";
import { Lock, X } from "lucide-react";
import { Tile } from "@/components/tiles/tile-shell";
import { ProjectGuard } from "@/components/project-guard";
import { Chip, Mono, Panel, Tabs } from "@/components/primitives";
import { useProjectArtifactLatest } from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { cn } from "@/lib/utils";
import { BuildTimeline, BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { useArtifactSource } from "@/lib/build";

const FILTERS = ["ALL", "MYTHIC", "RARE", "COMMON"];
const RARITY_RANK: Record<string, number> = { MYTHIC: 0, RARE: 1, COMMON: 2 };
const SEVERITY_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

type Trophy = {
  trophy_id: string;
  incident_id: string;
  title?: string;
  description?: string;
  rarity?: string;
  score?: number;
  sealed_at?: string;
  evidence?: {
    event_count?: number;
    hops?: number;
    counterfactual_count?: number;
    blast_radius?: number;
    severity?: string;
    host?: string;
    user?: string;
    status?: string;
    started?: string;
    engines?: Record<string, number>;
  };
};
type TrophyPayload = { trophies?: Trophy[]; trophy_count?: number };

function rarityFrame(rarity: string) {
  if (rarity === "MYTHIC") return "border-2 border-accent glow-accent";
  if (rarity === "RARE") return "border-[1.5px] border-accent/50";
  return "border border-hairline";
}

export default function TrophyWallTile() {
  const params = useSearchParams();
  const buildId = params.get("build") || "";
  const build = useArtifactBuild(buildId || undefined);

  const { state, dispatch } = useAnvaya();
  const projectId = state.activeProjectId || "";
  const { data, isLoading, isError } = useProjectArtifactLatest(projectId, "trophy_wall");
  const payload = data?.payload as TrophyPayload | null | undefined;

  const { data: trophies, isBuilding } = useArtifactSource<Trophy>(
    build,
    payload?.trophies,
    isLoading,
    isError,
    "trophy_wall"
  );
  const filter = FILTERS.includes(state.trophy.filter) ? state.trophy.filter : "ALL";
  const filtered = [...trophies]
    .filter((trophy) => filter === "ALL" || (trophy.rarity || "COMMON").toUpperCase() === filter)
    .sort((a, b) =>
      state.trophy.sort === "rarity"
        ? (RARITY_RANK[(a.rarity || "COMMON").toUpperCase()] ?? 9) - (RARITY_RANK[(b.rarity || "COMMON").toUpperCase()] ?? 9)
        : state.trophy.sort === "severity"
          ? (SEVERITY_RANK[a.evidence?.severity || ""] ?? 9) - (SEVERITY_RANK[b.evidence?.severity || ""] ?? 9)
          : (b.sealed_at || "").localeCompare(a.sealed_at || "")
    );
  const selected = trophies.find((trophy) => trophy.trophy_id === state.trophy.selected || trophy.incident_id === state.trophy.selected) || null;
  const maxHops = trophies.reduce((max, trophy) => Math.max(max, trophy.evidence?.hops ?? 0), 0);

  const showBuildShell = isBuilding;

  return (
    <Tile
      id="trophy-wall"
      title="SEALED TROPHY WALL"
      subtitle="project-derived incident trophies and computed rarity"
      right={<Mono>{trophies.length} trophies — max {maxHops} hops</Mono>}
    >
      <ProjectGuard>
        {build && <BuildStatus state={build} />}
        {showBuildShell ? (
          <div className="bg-grid flex h-full gap-3 p-3">
            <div className="relative flex min-w-0 flex-1 flex-col">
              <div className="flex items-center justify-between border-b border-hairline px-6 py-2.5">
                <Tabs items={FILTERS} value={filter} onChange={(value) => dispatch({ type: "patch", path: "trophy", value: { filter: value } })} />
                <div className="flex items-center gap-1">
                  <Mono className="mr-1">sort</Mono>
                  {(["recent", "rarity", "severity"] as const).map((sort) => (
                    <button key={sort} type="button" onClick={() => dispatch({ type: "patch", path: "trophy", value: { sort } })} className={cn("border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider", state.trophy.sort === sort ? "border-accent/50 text-accent" : "border-hairline text-muted")}>{sort}</button>
                  ))}
                </div>
              </div>
              <div className="flex-1 overflow-auto px-6 py-4 pb-16">
                {filtered.length === 0 ? (
                  <ArtifactState message={trophies.length ? `No ${filter.toLowerCase()} trophies are present.` : "Building trophy wall workspace..."} />
                ) : (
                  <div className="flex flex-wrap gap-3">
                    {filtered.map((trophy) => <TrophyCard key={trophy.trophy_id} trophy={trophy} selected={selected?.trophy_id === trophy.trophy_id} onSelect={() => dispatch({ type: "patch", path: "trophy", value: { selected: trophy.trophy_id } })} />)}
                  </div>
                )}
              </div>
              {selected && <TrophyDetail trophy={selected} />}
              <div className="absolute inset-x-0 bottom-0 flex h-9 items-center justify-center border-t border-hairline bg-canvas-elevated/70"><Mono className="text-[9px]">Rarity and score are displayed as recorded in the generated trophy artifact.</Mono></div>
            </div>
            <div className="flex h-full w-[320px] shrink-0 flex-col gap-3">
              {build && <BuildTimeline state={build} />}
            </div>
          </div>
        ) : isLoading && trophies.length === 0 ? (
          <ArtifactState message="Loading project trophy wall..." />
        ) : isError || (!payload && trophies.length === 0) ? (
          <ArtifactState message="No trophy wall artifact has been generated for this project." />
        ) : (
          <div className="bg-grid relative flex h-full flex-col">
            <div className="flex items-center justify-between border-b border-hairline px-6 py-2.5">
              <Tabs items={FILTERS} value={filter} onChange={(value) => dispatch({ type: "patch", path: "trophy", value: { filter: value } })} />
              <div className="flex items-center gap-1">
                <Mono className="mr-1">sort</Mono>
                {(["recent", "rarity", "severity"] as const).map((sort) => (
                  <button key={sort} type="button" onClick={() => dispatch({ type: "patch", path: "trophy", value: { sort } })} className={cn("border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider", state.trophy.sort === sort ? "border-accent/50 text-accent" : "border-hairline text-muted")}>{sort}</button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-auto px-6 py-4 pb-16">
              {filtered.length === 0 ? <ArtifactState message={trophies.length ? `No ${filter.toLowerCase()} trophies are present.` : "This trophy wall artifact contains no trophies."} /> : (
                <div className="flex flex-wrap gap-3">
                  {filtered.map((trophy) => <TrophyCard key={trophy.trophy_id} trophy={trophy} selected={selected?.trophy_id === trophy.trophy_id} onSelect={() => dispatch({ type: "patch", path: "trophy", value: { selected: trophy.trophy_id } })} />)}
                </div>
              )}
            </div>
            {selected && <TrophyDetail trophy={selected} />}
            <div className="absolute inset-x-0 bottom-0 flex h-9 items-center justify-center border-t border-hairline bg-canvas-elevated/70"><Mono className="text-[9px]">Rarity and score are displayed as recorded in the generated trophy artifact.</Mono></div>
          </div>
        )}
      </ProjectGuard>
    </Tile>
  );
}

function TrophyCard({ trophy, selected, onSelect }: { trophy: Trophy; selected: boolean; onSelect: () => void }) {
  const rarity = (trophy.rarity || "COMMON").toUpperCase();
  const engines = trophy.evidence?.engines || {};
  return (
    <button type="button" onClick={onSelect} aria-pressed={selected} className={cn("row-interactive w-[230px] shrink-0 bg-canvas-panel/60 p-3 text-left", rarityFrame(rarity), selected && "-translate-y-0.5 border-accent glow-accent")}>
      <div className="mb-2 flex items-center justify-between"><span className="font-mono text-[11px] text-primary">{trophy.incident_id}</span><Chip tone={rarity === "COMMON" ? "muted" : "accent"}>{rarity}</Chip></div>
      <div className="truncate font-mono text-[10px] text-secondary">{trophy.title || trophy.trophy_id}</div>
      <div className="mt-2 font-mono text-[9px] text-muted">score {(trophy.score ?? 0).toFixed(2)} — {trophy.evidence?.hops ?? 0} hops</div>
      <div className="mt-2 flex gap-1" aria-label="recorded engine scores">{["sentinel", "blastscope", "whatif", "ledger"].map((engine) => <span key={engine} className={cn("h-1.5 w-1.5 rounded-full", (engines[engine] ?? 0) > 0 ? "bg-accent" : "bg-white/10")} />)}</div>
    </button>
  );
}

function TrophyDetail({ trophy }: { trophy: Trophy }) {
  const { dispatch } = useAnvaya();
  const engines = trophy.evidence?.engines || {};
  const close = () => dispatch({ type: "patch", path: "trophy", value: { selected: "" } });

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4"
      onClick={close}
      role="dialog"
      aria-modal="true"
    >
      <div onClick={(e) => e.stopPropagation()}>
        <Panel
          glow={(trophy.rarity || "").toUpperCase() === "MYTHIC" ? "accent" : undefined}
          className="relative w-[440px] !bg-canvas-elevated p-4 shadow-2xl"
        >
          <button
            type="button"
            onClick={close}
            className="absolute right-2 top-2 text-muted hover:text-primary"
            aria-label="Close trophy details"
          >
            <X className="h-4 w-4" />
          </button>
          <div className="flex items-center justify-between pr-5">
            <Mono tone="primary">{trophy.trophy_id}</Mono>
            <Chip tone="accent">{trophy.rarity || "COMMON"} — {trophy.score ?? 0}</Chip>
          </div>
          <div className="mt-2 font-mono text-[10px] text-muted">{trophy.description || trophy.title || "—"}</div>
          <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[10px]">
            <span className="text-muted">host</span><span>{trophy.evidence?.host || "—"}</span>
            <span className="text-muted">user</span><span>{trophy.evidence?.user || "—"}</span>
            <span className="text-muted">blast radius</span><span>{trophy.evidence?.blast_radius ?? "—"}</span>
            <span className="text-muted">sealed at</span><span>{trophy.sealed_at ? new Date(trophy.sealed_at).toLocaleString() : "—"}</span>
          </div>
          <div className="mt-3 grid grid-cols-4 gap-2 border-t border-hairline pt-2">
            {["sentinel", "blastscope", "whatif", "ledger"].map((engine) => (
              <div key={engine}>
                <Mono className="block text-[8px]">{engine}</Mono>
                <span className="font-mono text-[11px] text-accent">{(engines[engine] ?? 0).toFixed(2)}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-1.5 border-t border-hairline pt-2">
            <Lock className="h-3 w-3 text-muted" />
            <Mono className="text-[8px]">sealed {trophy.sealed_at ? "in generated artifact" : "timestamp unavailable"}</Mono>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function ArtifactState({ message }: { message: string }) {
  return <div className="flex h-full min-h-32 items-center justify-center p-8 text-center"><Mono className="text-muted">{message}</Mono></div>;
}
