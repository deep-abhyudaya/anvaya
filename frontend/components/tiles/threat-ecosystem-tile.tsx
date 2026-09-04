"use client";

import { useRef, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { Tile } from "./tile-shell";
import { ProjectGuard } from "@/components/project-guard";
import { GraphCanvas, type EdgeCtx, type NodeCtx } from "@/lib/graph";
import { useEcosystem } from "@/lib/api";
import { useAnvaya, useLiveClock, useTicker } from "@/lib/store";
import { Mono, Scrubber, Segmented, TransportBtn } from "@/components/primitives";
import { cn, cssStyle } from "@/lib/utils";
import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { BuildTimeline, BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { useArtifactSource } from "@/lib/build";

const SPEEDS = [1, 2, 4];
const MAX_STEP = 8;

const HEX = "11,0 5.5,9.53 -5.5,9.53 -11,0 -5.5,-9.53 5.5,-9.53";

type EcoNode = {
  id: string;
  kind: "attacker" | "asset" | "defender";
  x: number;
  y: number;
  compromised?: boolean;
};

type EcoEdge = {
  from: string;
  to: string;
  attack?: boolean;
  deviation?: number;
  kind?: string;
  blocked?: boolean;
};

type EcosystemPayload = {
  nodes?: EcoNode[];
  edges?: EcoEdge[];
  health?: number;
  compromised?: string[];
  blockedEdges?: string[];
  liveAttacks?: string[];
  note?: string;
  viewW?: number;
  viewH?: number;
};

function isEcoNode(d: unknown): d is EcoNode {
  if (typeof d !== "object" || d === null) return false;
  const obj = d as Record<string, unknown>;
  return (
    typeof obj.id === "string" &&
    (obj.kind === "attacker" || obj.kind === "asset" || obj.kind === "defender") &&
    typeof obj.x === "number" &&
    typeof obj.y === "number"
  );
}

function isEcoEdge(d: unknown): d is EcoEdge {
  if (typeof d !== "object" || d === null) return false;
  const obj = d as Record<string, unknown>;
  return typeof obj.from === "string" && typeof obj.to === "string";
}

export default function ThreatEcosystemTile() {
  const params = useSearchParams();
  const buildId = params.get("build") || "";
  const build = useArtifactBuild(buildId || undefined);

  const { state, dispatch } = useAnvaya();
  const eco = state.eco;
  const clock = useLiveClock("14:05:22");
  const activeProjectId = state.activeProjectId || "";
  const { data, isLoading, isError } = useEcosystem(eco.mode, eco.step, activeProjectId);

  const payload = (data as EcosystemPayload) || null;
  const { data: nodes } = useArtifactSource<EcoNode>(
    build,
    payload?.nodes,
    isLoading,
    isError,
    "ecosystem",
    isEcoNode
  );
  const { data: edges, isBuilding } = useArtifactSource<EcoEdge>(
    build,
    payload?.edges,
    isLoading,
    isError,
    "ecosystem",
    isEcoEdge
  );

  const compromised: string[] = useMemo(
    () => nodes.filter((n) => n.compromised).map((n) => n.id),
    [nodes]
  );

  const blockedEdges: string[] = useMemo(
    () =>
      edges
        .filter((e) => e.kind === "blocked_by" || e.blocked)
        .map((e) => `${e.from}->${e.to}`),
    [edges]
  );

  const liveAttacks: string[] = useMemo(
    () =>
      edges
        .filter((e) => e.attack || e.kind === "attacks")
        .map((e) => `${e.from}->${e.to}`),
    [edges]
  );

  const rawNote = payload?.note || build?.activeElementReason || undefined;
  const note =
    activeProjectId && rawNote && rawNote.includes("Select a project")
      ? undefined
      : rawNote;

  const health: number = useMemo(() => {
    const assets = nodes.filter((n) => n.kind === "asset");
    const compromisedCount = nodes.filter((n) => n.compromised).length;
    const defendedCount = blockedEdges.length;
    return Math.max(
      0,
      Math.min(
        99,
        Math.round(
          ((assets.length - compromisedCount) / Math.max(assets.length, 1)) * 74 +
            defendedCount * 3
        )
      )
    );
  }, [nodes, blockedEdges]);

  const viewW = payload?.viewW ?? 1280;
  const viewH = payload?.viewH ?? 640;

  const sim = {
    compromised,
    blockedEdges,
    liveAttacks,
    note,
  };

  const stepRef = useRef(eco.step);
  stepRef.current = eco.step;
  const accRef = useRef(0);

  const patch = (value: Partial<typeof eco>) =>
    dispatch({ type: "patch", path: "eco", value });

  useTicker(eco.playing, eco.speed, (dt) => {
    accRef.current += dt * 0.5;
    if (accRef.current < 1) return;
    const adv = Math.floor(accRef.current);
    accRef.current -= adv;
    const ns = Math.min(MAX_STEP, stepRef.current + adv);
    if (ns >= MAX_STEP) patch({ step: MAX_STEP, playing: false });
    else patch({ step: ns });
  });

  const setStep = (s: number) => {
    accRef.current = 0;
    patch({ step: Math.max(0, Math.min(MAX_STEP, Math.round(s))), playing: false });
  };
  const cycleSpeed = () => {
    const i = SPEEDS.indexOf(eco.speed);
    patch({ speed: SPEEDS[(i + 1) % SPEEDS.length] });
  };

  const showBuildShell = isBuilding;

  if (isLoading && !isBuilding && !nodes.length && !payload) {
    return (
      <Tile id="threat-ecosystem" title="THREAT ECOSYSTEM" subtitle="predator-prey-defender network simulation">
        <ProjectGuard>
          <div className="flex h-full items-center justify-center">
            <Mono className="text-muted">Loading...</Mono>
          </div>
        </ProjectGuard>
      </Tile>
    );
  }

  return (
    <Tile
      id="threat-ecosystem"
      title="THREAT ECOSYSTEM"
      subtitle="predator-prey-defender network simulation"
      center={
        <span
          className={cn(
            "font-mono text-[10px] uppercase tracking-widest",
            health >= 70 ? "text-accent" : health >= 40 ? "text-warning" : "text-critical"
          )}
        >
          ecosystem health: {health}% defended
        </span>
      }
      right={
        <Segmented
          items={["IGNORE", "CONTAIN"]}
          value={eco.mode}
          onChange={(v) => patch({ mode: v as "IGNORE" | "CONTAIN" })}
        />
      }
    >
      <ProjectGuard>
        {build && <BuildStatus state={build} />}
        {showBuildShell && nodes.length === 0 ? (
          <ArtifactState message="Building threat ecosystem workspace..." />
        ) : !showBuildShell && nodes.length === 0 ? (
          <ArtifactState message="No ecosystem simulation has been generated for this project. Generate one from the Agent console." />
        ) : (
          <div className="flex h-full w-full gap-3">
            <div className="bg-grid relative min-h-0 flex-1 flex-col">
              <GraphCanvas
                nodes={nodes}
                edges={edges}
                viewW={viewW}
                viewH={viewH}
                positions={eco.positions}
                onNodePos={(id, pos) =>
                  patch({ positions: { ...eco.positions, [id]: pos } })
                }
                selected={eco.selected}
                onSelect={(id) => patch({ selected: id })}
                ariaLabel="threat ecosystem simulation"
                renderEdge={(e: any, ctx: EdgeCtx) => <EcoEdgeGlyph e={e} ctx={ctx} sim={sim} />}
                renderNode={(n: any, ctx: NodeCtx) => <EcoNodeGlyph n={n} ctx={ctx} sim={sim} />}
                renderOverlay={({ pos }) => (
                  <EcoTooltip pos={pos} sim={sim} selected={eco.selected} nodes={nodes} edges={edges} />
                )}
              />

              {sim.note && (
                <div className="pointer-events-none absolute bottom-4 left-4 z-10 border border-warning/40 bg-canvas-panel/90 px-2.5 py-1.5 font-mono text-[9px] uppercase tracking-wider text-warning glow-warning">
                  {sim.note}
                </div>
              )}

              <div className="pointer-events-none absolute right-4 top-3 z-10 flex items-center gap-4 border border-hairline bg-canvas-elevated/70 px-3 py-1.5 backdrop-blur-sm">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rotate-45 border border-warning" />
                  <Mono>attacker</Mono>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full border border-accent" />
                  <Mono>asset</Mono>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 border border-accent" style={{ clipPath: "polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%)" }} />
                  <Mono>defender</Mono>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full bg-warning" />
                  <Mono>compromised</Mono>
                </span>
              </div>
            </div>
            {showBuildShell && (
              <div className="flex h-full w-[320px] shrink-0 flex-col gap-3">
                {build && <BuildTimeline state={build} />}
              </div>
            )}
          </div>
        )}

        {nodes.length > 0 && (
          <div className="flex items-center gap-3 border-t border-hairline bg-canvas-elevated/60 px-4 py-2.5">
            <Mono>
              simulation step {eco.step}/{MAX_STEP}
            </Mono>
            <div className="flex items-center gap-1">
              <TransportBtn label="step back" onClick={() => setStep(eco.step - 1)}>
                <ChevronLeft className="h-3 w-3" />
              </TransportBtn>
              <TransportBtn
                label={eco.playing ? "pause" : "play"}
                active={eco.playing}
                onClick={() => {
                  if (!eco.playing && eco.step >= MAX_STEP) patch({ step: 0, playing: true });
                  else patch({ playing: !eco.playing });
                }}
              >
                {eco.playing ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
              </TransportBtn>
              <TransportBtn label="step forward" onClick={() => setStep(eco.step + 1)}>
                <ChevronRight className="h-3 w-3" />
              </TransportBtn>
            </div>
            <Scrubber
              label="simulation step"
              value={eco.step / MAX_STEP}
              onChange={(v) => setStep(v * MAX_STEP)}
            />
            <span className="whitespace-nowrap font-mono text-[10px] tabular-nums text-secondary">
              {clock}
            </span>
            <button
              type="button"
              onClick={cycleSpeed}
              className="border border-hairline px-2.5 py-1 font-mono text-[10px] tabular-nums text-muted transition-colors hover:border-accent/40 hover:text-accent"
            >
              {eco.speed.toFixed(1)}x
            </button>
          </div>
        )}
      </ProjectGuard>
    </Tile>
  );
}

function EcoEdgeGlyph({ e, ctx, sim }: { e: any; ctx: EdgeCtx; sim: any }) {
  const { from, to, active, dimmed } = ctx;
  const id = `${e.from}->${e.to}`;
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2;

  if (e.attack) {
    const blocked = sim.blockedEdges?.includes(id) || false;
    const live = sim.liveAttacks?.includes(id) || false;
    return (
      <g opacity={dimmed ? 0.08 : 1} className="transition-opacity">
        <line
          x1={from.x}
          y1={from.y}
          x2={to.x}
          y2={to.y}
          stroke="var(--color-warning)"
          strokeWidth={live ? 1.5 : 1}
          strokeDasharray="4 6"
          opacity={blocked ? 0.35 : 0.8}
          className={live ? "edge-flow" : undefined}
          style={
            live
              ? { filter: "drop-shadow(0 0 4px color-mix(in srgb, var(--color-warning) 60%, transparent))" }
              : undefined
          }
        />
        {blocked && (
          <text
            x={mx}
            y={my + 3}
            textAnchor="middle"
            fontSize={10}
            fontFamily="monospace"
            className="fill-accent"
          >
            ✕
          </text>
        )}
        {e.deviation !== undefined && (
          <text
            x={mx}
            y={my - 8}
            textAnchor="middle"
            fontSize={8.5}
            fontFamily="monospace"
            opacity={0.9}
            className={blocked ? "fill-muted" : "fill-warning"}
          >
            deviation: {Number(e.deviation).toFixed(2)}
          </text>
        )}
      </g>
    );
  }

  return (
    <line
      x1={from.x}
      y1={from.y}
      x2={to.x}
      y2={to.y}
      stroke={active ? "var(--color-accent)" : "color-mix(in srgb, var(--color-accent) 28%, transparent)"}
      strokeWidth={active ? 1.4 : 0.8}
      opacity={dimmed ? 0.08 : 1}
      className="transition-all duration-200"
    />
  );
}

function EcoNodeGlyph({ n, ctx, sim }: { n: any; ctx: NodeCtx; sim: any }) {
  const { pos, selected, hovered, dragging, dragProps } = ctx;
  const compromised = sim.compromised?.includes(n.id) || false;
  const blockedAttacker =
    n.kind === "attacker" && sim.blockedEdges?.some((id: string) => id.startsWith(`${n.id}->`));
  const liveAttacker =
    n.kind === "attacker" && sim.liveAttacks?.some((id: string) => id.startsWith(`${n.id}->`));

  return (
    <g
      transform={`translate(${pos.x},${pos.y})`}
      {...dragProps}
      className={cn("cursor-grab", dragging && "cursor-grabbing")}
      opacity={blockedAttacker ? 0.3 : 1}
      style={{ transition: "opacity 200ms ease" }}
    >
      {selected && (
        <circle
          r={16}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth={1}
          opacity={0.9}
          style={{ filter: "drop-shadow(0 0 6px color-mix(in srgb, var(--color-accent) 80%, transparent))" }}
        />
      )}
      {hovered && !selected && (
        <circle r={14} fill="none" stroke="var(--color-accent)" strokeWidth={0.7} opacity={0.5} />
      )}

      {n.kind === "attacker" && (
        <rect
          x={-7}
          y={-7}
          width={14}
          height={14}
          transform="rotate(45)"
          fill={liveAttacker ? "var(--color-warning)" : "var(--color-surface)"}
          stroke="var(--color-warning)"
          strokeWidth={1.2}
          style={
            liveAttacker
              ? { filter: "drop-shadow(0 0 6px color-mix(in srgb, var(--color-warning) 80%, transparent))" }
              : undefined
          }
        />
      )}

      {n.kind === "asset" && (
        <circle
          r={6.5}
          fill={compromised ? "var(--color-warning)" : "var(--color-surface)"}
          stroke={compromised ? "var(--color-warning)" : "color-mix(in srgb, var(--color-text-primary) 80%, transparent)"}
          strokeWidth={1}
          style={
            compromised
              ? { filter: "drop-shadow(0 0 7px color-mix(in srgb, var(--color-warning) 80%, transparent))" }
              : undefined
          }
        />
      )}

      {n.kind === "defender" && (
        <>
          {n.id === "D-01" && (
            <>
              <circle
                r={18}
                fill="none"
                stroke="var(--color-accent)"
                strokeWidth={0.8}
                opacity={0.45}
                style={{ filter: "drop-shadow(0 0 8px color-mix(in srgb, var(--color-accent) 90%, transparent))" }}
              />
              <circle
                r={13}
                fill="none"
                stroke="var(--color-accent)"
                strokeWidth={1}
                className="pulse-ring"
                style={cssStyle({ "--pulse-r0": "13px", "--pulse-r1": "22px" })}
              />
            </>
          )}
          <polygon
            points={HEX}
            fill={n.id === "D-01" ? "color-mix(in srgb, var(--color-accent) 10%, transparent)" : "var(--color-surface)"}
            stroke="var(--color-accent)"
            strokeWidth={1.1}
          />
        </>
      )}

      <text
        x={16}
        y={3}
        fontSize={9}
        fontFamily="monospace"
        className={cn("uppercase", n.id === "D-01" ? "fill-accent" : "fill-muted")}
        style={{ letterSpacing: "0.08em" }}
      >
        {n.id}
      </text>
    </g>
  );
}

function EcoTooltip({
  pos,
  sim,
  selected,
  nodes,
  edges,
}: {
  pos: (id: string) => { x: number; y: number };
  sim: any;
  selected: string | null;
  nodes: any[];
  edges: any[];
}) {
  if (!selected) return null;
  const n = nodes.find((x: any) => x.id === selected);
  if (!n) return null;
  const p = pos(selected);

  const name = n.name || n.id;
  const blocks = sim.blockedEdges?.filter((id: string) => id.startsWith(`${n.id}->`)).length || 0;

  let lines: string[];
  if (n.kind === "defender") {
    lines = [`${name} — role: defender`, `blocks ${blocks} paths — added 14:03`];
  } else if (n.kind === "asset") {
    lines = [
      `${name} — asset`,
      `status: ${sim.compromised?.includes(n.id) ? "compromised" : "clean"}`,
    ];
  } else {
    const dev = edges.find((e: any) => e.from === n.id && e.attack)?.deviation;
    lines = [`${name} — attacker`, `deviation: ${dev !== undefined ? Number(dev).toFixed(2) : "—"}`];
  }

  const w = Math.max(...lines.map((l) => l.length)) * 5.6 + 16;
  const h = lines.length * 13 + 12;
  const bx = p.x + 18 + w > 1280 ? p.x - 18 - w : p.x + 18;
  const by = p.y - h - 14 < 0 ? p.y + 18 : p.y - h - 14;

  return (
    <g className="pointer-events-none">
      <line
        x1={p.x}
        y1={p.y}
        x2={bx + 8}
        y2={by + h}
        stroke="color-mix(in srgb, var(--color-accent) 40%, transparent)"
        strokeWidth={0.7}
      />
      <rect
        x={bx}
        y={by}
        width={w}
        height={h}
        fill="var(--color-surface)"
        stroke="color-mix(in srgb, var(--color-accent) 35%, transparent)"
        strokeWidth={0.8}
      />
      {lines.map((l, i) => (
        <text
          key={i}
          x={bx + 8}
          y={by + 15 + i * 13}
          fontSize={9}
          fontFamily="monospace"
          className={i === 0 ? "fill-accent" : "fill-secondary"}
        >
          {l}
        </text>
      ))}
    </g>
  );
}

function ArtifactState({ message }: { message: string }) {
  return <div className="flex h-full items-center justify-center p-8 text-center"><Mono className="text-muted">{message}</Mono></div>;
}
