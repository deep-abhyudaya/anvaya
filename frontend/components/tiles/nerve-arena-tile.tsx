"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { BookOpen, ChevronDown, Crosshair, Eye, Shuffle, type LucideIcon } from "lucide-react";
import { Tile } from "@/components/tiles/tile-shell";
import { Mono } from "@/components/primitives";
import { useProjectArtifactLatest } from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { cn } from "@/lib/utils";
import { BuildTimeline, BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { useArtifactSource } from "@/lib/build";

const CX = 210;
const CY = 210;
const RING_R = 150;
const CIRC = 2 * Math.PI * RING_R;
const GAP_DEG = 5;

function polar(r: number, degFromTop: number): [number, number] {
  const a = ((degFromTop - 90) * Math.PI) / 180;
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)];
}

function useAnimatedNumber(target: number, duration = 650): number {
  const [value, setValue] = useState(target);
  const displayed = useRef(target);
  useEffect(() => {
    const from = displayed.current;
    if (from === target) return;
    let raf = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const v = from + (target - from) * eased;
      displayed.current = v;
      setValue(v);
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return value;
}

type EngineKey = "SENTINEL" | "BLASTSCOPE" | "LEDGER" | "WHATIF";

interface EngineMeta {
  key: EngineKey;
  label: string;
  icon: LucideIcon;
  stroke: string;
  width: number;
  glow?: boolean;
  iconClass: string;
  anchor: [number, number];
  corner: string;
}

type ArenaStage = {
  id: string;
  name: string;
  events?: number;
  detection_rate?: number;
};

type ArenaPayload = {
  dataset_id?: string;
  engines?: Record<EngineKey, number>;
  severity?: number;
  consensus?: number;
  stages?: ArenaStage[];
};

const ENGINE_META: EngineMeta[] = [
  { key: "BLASTSCOPE", label: "BLASTSCOPE", icon: Crosshair, stroke: "var(--color-accent)", width: 16, glow: true, iconClass: "text-accent", anchor: [312, 8], corner: "right-0 top-0" },
  { key: "WHATIF", label: "WHAT-IF", icon: Shuffle, stroke: "var(--color-warning)", width: 8, iconClass: "text-warning", anchor: [316, 412], corner: "right-0 bottom-0" },
  { key: "LEDGER", label: "LEDGER", icon: BookOpen, stroke: "color-mix(in srgb, var(--color-accent) 32%, transparent)", width: 8, iconClass: "text-muted", anchor: [104, 412], corner: "left-0 bottom-0" },
  { key: "SENTINEL", label: "SENTINEL", icon: Eye, stroke: "color-mix(in srgb, var(--color-accent) 60%, transparent)", width: 11, iconClass: "text-accent/70", anchor: [112, 8], corner: "left-0 top-0" },
];

const ARC_TRANSITION = "stroke-dasharray 700ms cubic-bezier(0.22,1,0.36,1), stroke-dashoffset 700ms cubic-bezier(0.22,1,0.36,1)";

export default function NerveArenaTile() {
  const params = useSearchParams();
  const buildId = params.get("build") || "";
  const build = useArtifactBuild(buildId || undefined);

  const { state } = useAnvaya();
  const activeProjectId = state.activeProjectId || "";
  const { data: projectArena, isLoading, isError } = useProjectArtifactLatest(activeProjectId, "arena");

  const payload = (projectArena?.payload as ArenaPayload | null | undefined) || null;
  const { data: stages, isBuilding } = useArtifactSource<ArenaStage>(
    build,
    payload?.stages,
    isLoading,
    isError,
    "arena"
  );

  const stageData: ArenaPayload = useMemo(() => {
    const defaultEngines = { SENTINEL: 0, BLASTSCOPE: 0, LEDGER: 0, WHATIF: 0 };
    const base: ArenaPayload = payload || {
      dataset_id: "",
      engines: defaultEngines,
      severity: 0,
      consensus: 0,
      stages: [],
    };
    return { ...base, stages };
  }, [payload, stages]);

  const severity = useAnimatedNumber(stageData.severity || 0);
  const consensus = useAnimatedNumber(stageData.consensus || 0);

  const halo = useMemo(() => {
    let seed = 2214;
    const rand = () => {
      seed = (seed * 1664525 + 1013904223) >>> 0;
      return seed / 4294967296;
    };
    const pts: string[] = [];
    const N = 96;
    for (let i = 0; i < N; i++) {
      const r = 196 + (rand() - 0.5) * 11;
      const [x, y] = polar(r, (i / N) * 360);
      pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    }
    return pts.join(" ");
  }, []);

  const ticks = useMemo(() => Array.from({ length: 24 }, (_, i) => i * 15), []);

  const arcs = useMemo(() => {
    const engines = stageData.engines || { SENTINEL: 0, BLASTSCOPE: 0, LEDGER: 0, WHATIF: 0 };
    const total = ENGINE_META.reduce((s, e) => s + (engines[e.key] || 0), 0);
    let acc = 0;
    return ENGINE_META.map((meta) => {
      const value = engines[meta.key] || 0;
      const share = total > 0 ? value / total : 0;
      const start = acc * 360;
      acc += share;
      return { meta, value, share, start, span: share * 360 };
    });
  }, [stageData]);

  const showBuildShell = isBuilding;

  const center = isLoading && !isBuilding && !stages.length ? (
    <span className="text-muted">Loading...</span>
  ) : (
    <span>
      dataset: <span className="text-secondary">{stageData.dataset_id || "—"}</span>
      <span className="px-1.5 text-muted/50">—</span>
      severity: <span className="tabular-nums">{stageData.severity?.toFixed(2) ?? "—"}</span>
      <span className="px-1.5 text-muted/50">—</span>
      consensus: <span className="tabular-nums text-accent">{stageData.consensus?.toFixed(2) ?? "—"}</span>
    </span>
  );

  const right = (
    <span className="flex items-center gap-1.5 border border-hairline px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest text-muted">
      view: engines <ChevronDown size={10} />
    </span>
  );

  return (
    <Tile
      id="nerve-arena"
      title="NERVE ARENA"
      subtitle="engine voting ring — real-time consensus"
      center={center}
      right={right}
    >
      {build && <BuildStatus state={build} />}
      {showBuildShell && (
        <div className="h-64 shrink-0 overflow-hidden border-b border-hairline">
          {build && <BuildTimeline state={build} />}
        </div>
      )}
      {isLoading && !isBuilding && !stages.length ? (
        <div className="flex h-full items-center justify-center">
          <Mono className="text-muted">Loading...</Mono>
        </div>
      ) : !payload && !isBuilding && !stages.length ? (
        <div className="flex h-full items-center justify-center">
          <Mono>No arena artifact has been generated for this project.</Mono>
        </div>
      ) : (
        <div className="flex h-full w-full flex-col bg-grid">
          {}
          <div className="relative flex flex-1 items-center justify-center overflow-hidden">
            <div className="relative" style={{ width: 560, height: 520 }}>
              <svg
                width={420}
                height={420}
                viewBox="0 0 420 420"
                className="absolute"
                style={{ left: 70, top: 50 }}
                role="img"
                aria-label="engine voting ring"
              >
                {}
                <polygon points={halo} fill="none" stroke="color-mix(in srgb, var(--color-accent) 14%, transparent)" strokeWidth={1} strokeLinejoin="round" />
                {}
                {ticks.map((d) => {
                  const [x1, y1] = polar(203, d);
                  const [x2, y2] = polar(209, d);
                  return <line key={d} x1={x1} y1={y1} x2={x2} y2={y2} stroke="color-mix(in srgb, var(--color-text-primary) 10%, transparent)" strokeWidth={1} />;
                })}
                {}
                <g transform={`rotate(-90 ${CX} ${CY})`}>
                  <circle cx={CX} cy={CY} r={RING_R} fill="none" stroke="color-mix(in srgb, var(--color-text-primary) 6%, transparent)" strokeWidth={18} />
                  {arcs.map(({ meta, share, start, span }) => {
                    if (share <= 0) return null;
                    const len = Math.max(0, ((span - GAP_DEG) / 360) * CIRC);
                    const off = -(((start + GAP_DEG / 2) / 360) * CIRC);
                    return (
                      <circle
                        key={meta.key}
                        cx={CX}
                        cy={CY}
                        r={RING_R}
                        fill="none"
                        stroke={meta.stroke}
                        strokeWidth={meta.width}
                        strokeDasharray={`${len} ${CIRC - len}`}
                        strokeDashoffset={off}
                        style={{
                          transition: ARC_TRANSITION,
                          ...(meta.glow ? { filter: "drop-shadow(0 0 6px color-mix(in srgb, var(--color-accent) 45%, transparent))" } : {}),
                        }}
                      />
                    );
                  })}
                </g>
                {}
                {arcs.map(({ meta, share, start, span }) => {
                  if (share <= 0) return null;
                  const mid = start + span / 2;
                  const [x1, y1] = polar(RING_R + meta.width / 2 + 3, mid);
                  const [x2, y2] = polar(196, mid);
                  const [ax, ay] = meta.anchor;
                  return (
                    <g key={`conn-${meta.key}`}>
                      <polyline
                        points={`${x1.toFixed(1)},${y1.toFixed(1)} ${x2.toFixed(1)},${y2.toFixed(1)} ${ax},${ay}`}
                        fill="none"
                        stroke="color-mix(in srgb, var(--color-accent) 22%, transparent)"
                        strokeWidth={1}
                        style={{ transition: "all 700ms cubic-bezier(0.22,1,0.36,1)" }}
                      />
                      <circle cx={ax} cy={ay} r={1.6} fill="color-mix(in srgb, var(--color-accent) 45%, transparent)" />
                    </g>
                  );
                })}
              </svg>

              {}
              <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                <div className="text-center" aria-live="polite">
                  <Mono>SEVERITY:</Mono>
                  <div
                    className="mt-1 font-mono text-[48px] leading-none tabular-nums text-primary"
                    style={{ textShadow: "0 0 24px color-mix(in srgb, var(--color-accent) 25%, transparent)" }}
                  >
                    {severity.toFixed(2)}
                  </div>
                  <div className="mt-2">
                    <Mono>
                      consensus: <span className="tabular-nums text-secondary">{consensus.toFixed(2)}</span>
                    </Mono>
                  </div>
                </div>
              </div>

              {}
              {arcs.map(({ meta, value, share }) => {
                const Icon = meta.icon;
                return (
                  <div
                    key={meta.key}
                    className={cn("absolute w-[170px] border border-hairline bg-canvas-panel/80 px-2.5 py-2 backdrop-blur-sm", meta.corner)}
                  >
                    <div className="flex items-center gap-1.5">
                      <Icon size={11} className={meta.iconClass} />
                      <Mono tone={meta.key === "WHATIF" ? "warning" : meta.key === "BLASTSCOPE" ? "accent" : "muted"}>{meta.label}</Mono>
                    </div>
                    <div className="mt-1.5 flex items-baseline justify-between">
                      <span className="font-mono text-[13px] tabular-nums text-primary">{value.toFixed(2)}</span>
                      <Mono>{Math.round(share * 100)}%</Mono>
                    </div>
                  </div>
                );
              })}

              <div className="absolute bottom-[64px] right-0 text-right">
                <Mono>
                  what-if contribution: <span className="tabular-nums text-warning">{(stageData.engines?.WHATIF || 0).toFixed(2)}</span>
                  <span className="text-muted/50"> — </span>
                  <span className="tabular-nums text-secondary">{(stageData.stages || []).length}</span> recorded stages
                </Mono>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-center gap-2 pb-6" aria-label="recorded arena stages">
            {(stageData.stages || []).map((stage: ArenaStage) => (
              <div
                key={stage.id}
                className="border border-hairline px-4 py-2 font-mono text-[10px] uppercase tracking-widest text-muted"
              >
                {stage.name} · {(stage.detection_rate ?? 0).toFixed(2)}
              </div>
            ))}
          </div>
        </div>
      )}
    </Tile>
  );
}
