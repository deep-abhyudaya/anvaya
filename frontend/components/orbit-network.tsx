"use client";

import { useMemo, useState } from "react";

export type OrbitPayload = {
  scope?: string;
  dataset_id?: string;
  node_count?: number;
  edge_count?: number;
  top_nodes?: Array<{
    id: string;
    label: string;
    risk: number;
    impact_score: number;
    is_compromised: boolean;
    source_events: number;
    dest_events: number;
  }>;
  top_edges?: Array<{
    source: string;
    target: string;
    count: number;
  }>;
  orbits?: Array<{
    a: string;
    b: string;
    a_to_b_count: number;
    b_to_a_count: number;
    risk_score: number;
  }>;
};

const VB = 800;
const CX = VB / 2;
const CY = VB / 2;
const R = 280;
const RINGS = [
  { label: "LOW", r: R * 0.25 },
  { label: "MEDIUM", r: R * 0.5 },
  { label: "HIGH", r: R * 0.75 },
  { label: "CRITICAL", r: R },
];
const SECTORS = [
  { label: "PAYROLL", angle: -0.9 },
  { label: "CUSTOMER DATA", angle: 0.4 },
  { label: "IDENTITY", angle: 1.7 },
  { label: "INFRA", angle: 2.6 },
];

function hashInt(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

function polar(index: number, total: number, label: string, risk: number): [number, number] {
  const base = (hashInt(label) % 1000) / 1000;
  const angle = (index / Math.max(total, 1)) * Math.PI * 2 + base * Math.PI * 2 - Math.PI / 2;
  const radius = Math.max(R * 0.12, risk * R);
  return [CX + radius * Math.cos(angle), CY + radius * Math.sin(angle)];
}

export function OrbitNetwork({ payload }: { payload: OrbitPayload }) {
  const [hover, setHover] = useState<string | null>(null);

  const nodes = useMemo(() => {
    const top = payload.top_nodes || [];
    return top.slice(0, 24).map((n, i) => {
      const [x, y] = polar(i, top.length, n.label, n.risk);
      return { ...n, x, y };
    });
  }, [payload]);

  const nodeById = useMemo(() => {
    const map: Record<string, (typeof nodes)[number]> = {};
    for (const n of nodes) map[n.id] = n;
    return map;
  }, [nodes]);

  const orbits = useMemo(() => payload.orbits || [], [payload]);

  const stats = useMemo(() => {
    const active = nodes.filter((n) => n.is_compromised || n.risk >= 0.5).length;
    const sealed = nodes.filter((n) => !n.is_compromised && n.risk < 0.5).length;
    const critical = nodes.filter((n) => n.risk >= 0.75).length;
    return { active, sealed, critical };
  }, [nodes]);

  return (
    <div className="relative h-full w-full overflow-hidden border border-hairline bg-canvas-panel/40">
      <svg
        viewBox={`0 0 ${VB} ${VB}`}
        preserveAspectRatio="xMidYMid meet"
        className="h-full w-full"
        role="img"
        aria-label="dataset risk orbits"
      >
        {}
        {RINGS.map((ring) => (
          <g key={ring.label}>
            <circle
              cx={CX}
              cy={CY}
              r={ring.r}
              fill="none"
              stroke="color-mix(in srgb, var(--color-accent) 12%, transparent)"
              strokeWidth={1}
              strokeDasharray={ring.r === R ? undefined : "4 4"}
            />
            <text
              x={CX + 6}
              y={CY - ring.r + 12}
              fontSize={9}
              fontFamily="monospace"
              fill="var(--color-text-muted)"
              className="uppercase tracking-wider"
            >
              {ring.label}
            </text>
          </g>
        ))}
        <line x1={CX} y1={CY - R} x2={CX} y2={CY + R} stroke="color-mix(in srgb, var(--color-accent) 8%, transparent)" strokeWidth={1} />
        <line x1={CX - R} y1={CY} x2={CX + R} y2={CY} stroke="color-mix(in srgb, var(--color-accent) 8%, transparent)" strokeWidth={1} />

        {}
        {SECTORS.map((s) => {
          const x = CX + (R + 32) * Math.cos(s.angle);
          const y = CY + (R + 32) * Math.sin(s.angle);
          return (
            <text
              key={s.label}
              x={x}
              y={y}
              textAnchor="middle"
              fontSize={10}
              fontFamily="monospace"
              fill="var(--color-text-secondary)"
              className="uppercase tracking-widest"
            >
              {s.label}
            </text>
          );
        })}

        {}
        <circle cx={CX} cy={CY} r={R * 0.08} fill="var(--color-surface)" stroke="var(--color-accent)" strokeWidth={1} opacity={0.9} />
        <text
          x={CX}
          y={CY + 3}
          textAnchor="middle"
          fontSize={10}
          fontFamily="monospace"
          fill="var(--color-text-secondary)"
          className="uppercase tracking-widest"
        >
          SAFE
        </text>

        {}
        {orbits.map((o, i) => {
          const s = nodeById[o.a];
          const t = nodeById[o.b];
          if (!s || !t) return null;
          return (
            <g key={`orbit-${i}`} id={`orbit-edge-${o.a}-${o.b}`}>
              <line
                x1={s.x}
                y1={s.y}
                x2={t.x}
                y2={t.y}
                stroke="var(--color-warning)"
                strokeWidth={1.5}
                strokeOpacity={0.6}
                strokeDasharray="4 4"
              />
            </g>
          );
        })}

        {}
        {nodes.map((n) => {
          const total = n.source_events + n.dest_events;
          const r = Math.max(4, Math.min(14, 4 + total / 3));
          const isHot = n.risk >= 0.75;
          const isActive = n.is_compromised || n.risk >= 0.5;

          return (
            <g
              key={n.id}
              id={`orbit-node-${n.id}`}
              onMouseEnter={() => setHover(`${n.label}: risk ${n.risk.toFixed(2)} · ${total} events`)}
              onMouseLeave={() => setHover(null)}
              className="cursor-pointer"
            >
              <circle
                cx={n.x}
                cy={n.y}
                r={r}
                fill={isActive ? (isHot ? "var(--color-surface)" : "var(--color-accent)") : "color-mix(in srgb, var(--color-text-secondary) 65%, transparent)"}
                stroke={isHot ? "var(--color-warning)" : isActive ? "var(--color-accent)" : "color-mix(in srgb, var(--color-text-secondary) 65%, transparent)"}
                strokeWidth={isHot ? 1.5 : 1}
                style={{
                  filter: isActive
                    ? `drop-shadow(0 0 5px ${isHot ? "color-mix(in srgb, var(--color-warning) 60%, transparent)" : "color-mix(in srgb, var(--color-accent) 50%, transparent)"})`
                    : undefined,
                }}
              />
              {n.risk >= 0.75 && (
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={r + 3}
                  fill="none"
                  stroke="var(--color-warning)"
                  strokeWidth={0.8}
                  opacity={0.5}
                />
              )}
            </g>
          );
        })}

        {}
        {(() => {
          const labeled = nodes.filter((n) => n.source_events + n.dest_events > 0);
          const hidden = nodes.filter((n) => n.source_events + n.dest_events === 0);
          return (
            <>
              {labeled.map((n) => {
                const angle = Math.atan2(n.y - CY, n.x - CX);
                const lr = R + 20;
                const lx = CX + lr * Math.cos(angle);
                const ly = CY + lr * Math.sin(angle);
                const anchor =
                  lx < CX - 20 ? "end" : lx > CX + 20 ? "start" : "middle";
                const tx =
                  anchor === "end"
                    ? lx - 4
                    : anchor === "start"
                    ? lx + 4
                    : lx;
                return (
                  <g key={`label-${n.id}`}>
                    <line
                      x1={n.x}
                      y1={n.y}
                      x2={lx}
                      y2={ly}
                      stroke="var(--color-hairline)"
                      strokeWidth={0.5}
                      opacity={0.4}
                    />
                    <text
                      x={tx}
                      y={ly + 3}
                      textAnchor={anchor}
                      fill="var(--color-text-secondary)"
                      style={{ fontSize: 8, fontFamily: "monospace" }}
                    >
                      {n.label}
                    </text>
                  </g>
                );
              })}
              {hidden.length > 0 && (
                <text
                  x={CX}
                  y={CY + 48}
                  textAnchor="middle"
                  fontSize={9}
                  fontFamily="monospace"
                  fill="var(--color-text-muted)"
                  className="uppercase tracking-widest"
                >
                  +{hidden.length} nodes
                </text>
              )}
            </>
          );
        })()}
      </svg>

      {hover && (
        <div className="pointer-events-none absolute bottom-3 left-3 z-20 border border-hairline bg-canvas-elevated/95 px-2.5 py-1.5 font-mono text-[10px] text-primary">
          {hover}
        </div>
      )}

      <div className="absolute right-3 top-3 z-10 w-56 border border-hairline bg-canvas-elevated/95 p-3">
        <p className="font-mono text-[10px] uppercase tracking-wider text-muted">legend</p>
        <div className="mt-2 space-y-1.5 font-mono text-[10px]">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-accent" />
            <span className="text-secondary">active incident</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-muted" />
            <span className="text-secondary">lower severity</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full border border-warning" />
            <span className="text-secondary">density hotspot</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-0 w-4 border-t border-dashed border-warning" />
            <span className="text-secondary">counterfactual</span>
          </div>
        </div>
        <p className="mt-3 font-mono text-[10px] text-accent">
          {stats.active} active · {stats.critical} critical
        </p>
      </div>
    </div>
  );
}
