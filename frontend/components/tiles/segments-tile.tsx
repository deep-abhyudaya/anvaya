"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Tile } from "./tile-shell";
import { ProjectGuard } from "@/components/project-guard";
import { GraphCanvas } from "@/lib/graph";
import { useProjectArtifactLatest } from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { Bar, Dot, Mono } from "@/components/primitives";
import { cn } from "@/lib/utils";
import { BuildTimeline, BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { useArtifactSource } from "@/lib/build";
import { useTheme } from "@/components/theme-provider";
import { withAlpha } from "@/lib/themes";

interface SegNode {
  id: string;
  x: number;
  y: number;
  kind: string;
}
interface SegEdge {
  from: string;
  to: string;
  seg?: any;
}

type Segment = {
  id: string;
  from: string;
  to: string;
  rank: number;
  depth: number;
  reach: number;
  traffic: number;
  risk: string;
  neutralized: boolean;
};

type SegmentsPayload = { items?: unknown[] };

const RISK_SEV: Record<string, number> = {
  low: 0.25,
  medium: 0.5,
  high: 0.75,
  critical: 1,
};

const RISK_TONE: Record<string, "critical" | "warning" | "accent" | "muted"> = {
  critical: "critical",
  high: "warning",
  medium: "accent",
  low: "muted",
};

const blastContribution = (seg: { traffic?: number; reach?: number }) =>
  ((seg.traffic ?? 0) * (seg.reach ?? 0)) / 10;

function toNumber(v: unknown, fallback = 0): number {
  return typeof v === "number" && !Number.isNaN(v) ? v : fallback;
}

function toString(v: unknown, fallback = ""): string {
  return typeof v === "string" && v.length > 0 ? v : fallback;
}

function toSegment(raw: unknown, index: number): Segment {
  if (typeof raw !== "object" || raw === null) {
    return {
      id: `SEG-${index + 1}`,
      from: `SRC-${index + 1}`,
      to: `DST-${index + 1}`,
      rank: 0,
      depth: 0,
      reach: 0,
      traffic: 0,
      risk: "low",
      neutralized: false,
    };
  }
  const s = raw as Record<string, unknown>;
  return {
    id: toString(s.id, `SEG-${index + 1}`),
    from: toString(s.from, `SRC-${index + 1}`),
    to: toString(s.to, `DST-${index + 1}`),
    rank: toNumber(s.rank, 0),
    depth: toNumber(s.depth, 0),
    reach: toNumber(s.reach, 0),
    traffic: toNumber(s.traffic, 0),
    risk: toString(s.risk, "low"),
    neutralized: s.neutralized === true,
  };
}

function hexPoints(r: number): string {
  return Array.from({ length: 6 }, (_, i) => {
    const a = (Math.PI / 3) * i - Math.PI / 6;
    return `${(r * Math.cos(a)).toFixed(2)},${(r * Math.sin(a)).toFixed(2)}`;
  }).join(" ");
}

export default function SegmentsTile() {
  return (
    <Tile
      id="segments"
      title="SEGMENTS TRACKED"
      subtitle="network segment topology"
      right={<Mono>sort: blast contribution ▾</Mono>}
    >
      <ProjectGuard>
        <SegmentsBody />
      </ProjectGuard>
    </Tile>
  );
}

function SegmentsBody() {
  const params = useSearchParams();
  const buildId = params.get("build") || "";
  const build = useArtifactBuild(buildId || undefined);

  const { state, dispatch } = useAnvaya();
  const { theme } = useTheme();
  const t = theme.tokens;
  const selectedId = state.segments.selected;
  const positions = state.segments.positions;
  const [hoveredSeg, setHoveredSeg] = useState<string | null>(null);
  const activeProjectId = state.activeProjectId || "";
  const { data: projectSegments, isLoading, isError } = useProjectArtifactLatest(activeProjectId, "segments");

  const projectPayload = (projectSegments?.payload as SegmentsPayload | null | undefined) || null;
  const { data: rawSegments, isBuilding } = useArtifactSource<Record<string, unknown>>(
    build,
    projectPayload?.items as Record<string, unknown>[] | undefined,
    isLoading,
    isError,
    "segments"
  );
  const segments = useMemo(() => rawSegments.map((s, i) => toSegment(s, i)), [rawSegments]);

  const nodes = useMemo<SegNode[]>(() => {
    const map = new Map<string, SegNode>();
    let idx = 0;
    for (const s of segments) {
      if (!map.has(s.from)) {
        map.set(s.from, {
          id: s.from,
          x: 100 + (idx % 5) * 150,
          y: 100 + Math.floor(idx / 5) * 120,
          kind: "host",
        });
        idx++;
      }
      if (!map.has(s.to)) {
        map.set(s.to, {
          id: s.to,
          x: 100 + (idx % 5) * 150,
          y: 100 + Math.floor(idx / 5) * 120,
          kind: "host",
        });
        idx++;
      }
    }
    return Array.from(map.values());
  }, [segments]);

  const edges = useMemo<SegEdge[]>(
    () => [
      ...segments.map((seg: Segment) => ({ from: seg.from, to: seg.to, seg })),
    ],
    [segments]
  );

  const ranked = useMemo(
    () => [...segments].sort((a: Segment, b: Segment) => (a.rank || 0) - (b.rank || 0)),
    [segments]
  );
  const selected = segments.find((s: Segment) => s.id === selectedId) ?? null;

  const showBuildShell = isBuilding;

  if (isLoading && !isBuilding && segments.length === 0 && !projectPayload) {
    return (
      <div className="flex h-full items-center justify-center">
        <Mono className="text-muted">Loading...</Mono>
      </div>
    );
  }

  const setSelected = (id: string | null) =>
    dispatch({ type: "patch", path: "segments", value: { selected: id } });

  const onGraphSelect = (id: string | null) => {
    if (!id) {
      setSelected(null);
      return;
    }
    const connected = segments
      .filter((s: Segment) => s.from === id || s.to === id)
      .sort((a: Segment, b: Segment) => (b.traffic || 0) - (a.traffic || 0));
    setSelected(connected.length ? connected[0].id : null);
  };

  const main = (
    <div className="flex h-full w-full">
      {}
      <div className="bg-grid relative h-full min-w-0 flex-1">
        {showBuildShell && segments.length === 0 ? (
          <ArtifactState message="Building segments workspace..." />
        ) : (
          <GraphCanvas<SegNode, SegEdge>
            nodes={nodes}
            edges={edges}
            viewW={900}
            viewH={640}
            positions={positions}
            onNodePos={(id, pos) =>
              dispatch({
                type: "patch",
                path: "segments",
                value: { positions: { ...positions, [id]: pos } },
              })
            }
            selected={null}
            onSelect={onGraphSelect}
            ariaLabel="tracked network segment topology"
            renderEdge={(e, ctx) => {
              if (!e.seg) {
                return (
                <line
                  x1={ctx.from.x}
                  y1={ctx.from.y}
                  x2={ctx.to.x}
                  y2={ctx.to.y}
                  stroke={t.border}
                  strokeWidth={1}
                />
              );
              }
              const seg = e.seg;
              const isSel = seg.id === selectedId;
              const isHov = seg.id === hoveredSeg;
              const dim = !!(selectedId || hoveredSeg) && !isSel && !isHov;
              const w = 1 + seg.traffic * 2;
              const color = isSel
                ? t.accent
                : seg.neutralized
                  ? t.textMuted
                  : seg.rank === 1
                    ? t.warning
                    : t.accent;
              return (
                <g opacity={dim ? 0.15 : seg.neutralized ? 0.55 : 1} className="transition-opacity">
                  {isSel && (
                    <line
                      x1={ctx.from.x}
                      y1={ctx.from.y}
                      x2={ctx.to.x}
                      y2={ctx.to.y}
                      stroke={t.accent}
                      strokeWidth={w + 6}
                      strokeLinecap="round"
                      opacity={0.16}
                    />
                  )}
                  <line
                    x1={ctx.from.x}
                    y1={ctx.from.y}
                    x2={ctx.to.x}
                    y2={ctx.to.y}
                    stroke={color}
                    strokeWidth={w}
                    strokeLinecap="round"
                    strokeDasharray={seg.neutralized ? "4 5" : undefined}
                    opacity={isSel || isHov ? 1 : 0.55}
                  />
                  {}
                  <line
                    x1={ctx.from.x}
                    y1={ctx.from.y}
                    x2={ctx.to.x}
                    y2={ctx.to.y}
                    stroke="transparent"
                    strokeWidth={14}
                    className="cursor-pointer"
                    onClick={(ev) => {
                      ev.stopPropagation();
                      setSelected(isSel ? null : seg.id);
                    }}
                    onPointerEnter={() => setHoveredSeg(seg.id)}
                    onPointerLeave={() => setHoveredSeg(null)}
                  />
                </g>
              );
            }}
            renderNode={(n, ctx) => {
              const touchesSel = !!selected && (selected.from === n.id || selected.to === n.id);
              const color = touchesSel ? t.accent : ctx.hovered ? t.textPrimary : withAlpha(t.textPrimary, 0.45);
              return (
                <g transform={`translate(${ctx.pos.x},${ctx.pos.y})`} {...ctx.dragProps} className="cursor-pointer">
                  <title>{n.id}</title>
                  {(touchesSel || ctx.hovered) && (
                    <circle r={13} fill="none" stroke={color} strokeWidth={0.5} opacity={0.5} />
                  )}
                  <NodeGlyph kind={n.kind} color={color} />
                  <text
                    y={22}
                    textAnchor="middle"
                    fontSize={9}
                    fontFamily="monospace"
                    fill={touchesSel ? t.accent : t.textMuted}
                  >
                    {n.id}
                  </text>
                </g>
              );
            }}
            renderOverlay={({ pos }) => {
              if (!selected) return null;
              const p = pos(selected.from);
              const bx = p.x + 18;
              const by = p.y - 62;
              return (
                <g className="pointer-events-none">
                  <line
                    x1={p.x}
                    y1={p.y - 10}
                    x2={bx}
                    y2={by + 56}
                    stroke={t.accent}
                    strokeWidth={0.5}
                    strokeDasharray="2 3"
                    opacity={0.5}
                  />
                  <rect
                    x={bx}
                    y={by}
                    width={186}
                    height={60}
                    fill={t.surface}
                    stroke={t.accentGlow}
                    strokeWidth={1}
                  />
                  <text x={bx + 8} y={by + 14} fontSize={9.5} fontFamily="monospace" fill={t.textPrimary}>
                    {selected.from} → {selected.to}
                  </text>
                  <text x={bx + 8} y={by + 28} fontSize={9} fontFamily="monospace" fill={t.textMuted}>
                    traffic <tspan fill={t.accent}>{(selected.traffic ?? 0).toFixed(2)}</tspan>
                  </text>
                  <text x={bx + 8} y={by + 41} fontSize={9} fontFamily="monospace" fill={t.textMuted}>
                    avg severity: <tspan fill={t.accent}>{(RISK_SEV[selected.risk] ?? 0).toFixed(2)}</tspan>
                  </text>
                  <text x={bx + 8} y={by + 54} fontSize={9} fontFamily="monospace" fill={t.textMuted}>
                    blast contribution{" "}
                    <tspan fill={selected.rank === 1 ? t.warning : t.accent}>
                      {blastContribution(selected).toFixed(2)}
                    </tspan>
                  </text>
                </g>
              );
            }}
          />
        )}

        {}
        <div className="pointer-events-none absolute bottom-12 left-3 z-10 flex flex-col gap-1.5 border border-hairline bg-canvas-elevated/80 px-3 py-2 backdrop-blur-sm">
          <span className="flex items-center gap-2">
            <span
              className="inline-block h-0 w-7 border-t-2 border-accent"
              style={{ boxShadow: "0 0 6px var(--color-accent-glow)" }}
            />
            <Mono className="text-[9px]">hot segment (active)</Mono>
          </span>
          <span className="flex items-center gap-2">
            <span className="inline-block h-0 w-7 border-t border-muted" />
            <Mono className="text-[9px]">baseline segment</Mono>
          </span>
        </div>
      </div>

      {}
      <aside className="flex h-full w-[420px] shrink-0 flex-col border-l border-hairline bg-canvas-elevated/40">
        {showBuildShell && (
          <div className="h-64 shrink-0 overflow-hidden">
            {build && <BuildTimeline state={build} />}
          </div>
        )}
        <div className="grid grid-cols-[32px_1fr_auto_96px] items-center gap-3 border-b border-hairline px-3 py-2">
          <Mono className="text-[9px]">rank</Mono>
          <Mono className="text-[9px]">segment</Mono>
          <Mono className="text-right text-[9px]">depth — reach</Mono>
          <Mono className="text-right text-[9px]">risk</Mono>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {ranked.map((seg) => {
            const isSel = seg.id === selectedId;
            const isHov = seg.id === hoveredSeg;
            return (
              <button
                key={seg.id}
                type="button"
                aria-pressed={isSel}
                onClick={() => setSelected(isSel ? null : seg.id)}
                onMouseEnter={() => setHoveredSeg(seg.id)}
                onMouseLeave={() => setHoveredSeg(null)}
                className={cn(
                  "row-interactive grid w-full grid-cols-[32px_1fr_auto_96px] items-center gap-3 border-b border-l-2 border-b-hairline px-3 py-2.5 text-left",
                  isSel
                    ? "border-l-accent bg-accent-dim"
                    : "border-l-transparent hover:bg-canvas-subtle",
                  isHov && !isSel && "bg-canvas-subtle/70",
                  seg.neutralized && "opacity-50"
                )}
              >
                <span
                  className={cn(
                    "font-mono text-[11px] tabular-nums",
                    isSel ? "text-accent" : "text-muted"
                  )}
                >
                  #{seg.rank}
                </span>

                <span className="min-w-0">
                  <span className="block truncate font-mono text-[11px] text-primary">
                    {seg.from} → {seg.to}
                  </span>
                  <span className="mt-1.5 flex items-center gap-2">
                    <Mono className="shrink-0 text-[8px]">traffic score</Mono>
                    <Bar value={seg.traffic} warning={seg.rank === 1} className="w-20 shrink-0" />
                    <span className="font-mono text-[9px] tabular-nums text-secondary">
                      {(seg.traffic ?? 0).toFixed(2)}
                    </span>
                  </span>
                </span>

                <span className="text-right font-mono text-[9px] leading-tight tabular-nums text-muted">
                  depth {seg.depth} — reaches
                  <br />
                  {seg.reach} systems
                </span>

                <span className="flex items-center justify-end gap-1.5">
                  <Dot
                    tone={RISK_TONE[seg.risk] ?? "muted"}
                    pulse={seg.risk === "critical" && !seg.neutralized}
                  />
                  <Mono
                    tone={seg.neutralized ? "muted" : (RISK_TONE[seg.risk] ?? "muted")}
                    className="text-[8px]"
                  >
                    {seg.neutralized ? "neutralized" : "exposed"}
                  </Mono>
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center justify-between border-t border-hairline px-3 py-2">
          <Mono className="tabular-nums">{segments.length} segments tracked</Mono>
          <Mono className="tabular-nums">
            {segments.filter((s: Segment) => s.neutralized).length} neutralized — top blast{" "}
            {blastContribution(ranked[0] || { traffic: 0, reach: 0 }).toFixed(2)}
          </Mono>
        </div>
      </aside>
    </div>
  );

  return (
    <>
      {build && <BuildStatus state={build} />}
      {main}
    </>
  );
}

function NodeGlyph({ kind, color }: { kind: string; color: string }) {
  const { theme } = useTheme();
  const common = { fill: theme.tokens.surface, stroke: color, strokeWidth: 1.2 };
  switch (kind) {
    case "user":
      return <circle r={7} {...common} />;
    case "edge":
      return <polygon points={hexPoints(8)} {...common} />;
    case "server":
      return <rect x={-7} y={-7} width={14} height={14} {...common} />;
    case "db":
      return <rect x={-7} y={-7} width={14} height={14} rx={4} {...common} />;
    default:
      return <rect x={-6.5} y={-6.5} width={13} height={13} {...common} />;
  }
}

function ArtifactState({ message }: { message: string }) {
  return <div className="flex h-full min-h-32 items-center justify-center p-8 text-center"><Mono className="text-muted">{message}</Mono></div>;
}
