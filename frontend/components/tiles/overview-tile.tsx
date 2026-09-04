"use client";

import Link from "next/link";
import { Tile } from "./tile-shell";
import { Bar, Chip, Dot, Mono, Panel } from "@/components/primitives";
import { useMetrics, useIncidents } from "@/lib/api";
import { useAnvaya, useLiveClock } from "@/lib/store";
import { ecoHealth } from "@/lib/data";

const SEV_TONE: Record<string, "warning" | "accent" | "muted"> = {
  critical: "warning",
  high: "warning",
  medium: "accent",
  low: "muted",
};
const STATUS_TONE: Record<string, "warning" | "accent" | "success" | "muted"> = {
  active: "warning",
  sealed: "accent",
  contained: "success",
  ignored: "muted",
};

export default function OverviewTile() {
  const { state } = useAnvaya();
  const clock = useLiveClock();
  const { data: metrics, isLoading: metricsLoading } = useMetrics(3000);
  const { data: incidentsData, isLoading: incidentsLoading } = useIncidents(3000);

  const incidents = incidentsData?.items || [];
  const active = metrics?.active_incidents || 0;
  const sealed = metrics?.sealed_incidents || 0;
  const cycles = metrics?.miss_patch_catch_cycles || 0;
  const health = ecoHealth(state.eco.mode, state.eco.step);

  const top = [...incidents].slice(0, 8);

  if (metricsLoading || incidentsLoading) {
    return (
      <Tile id="overview" title="OVERVIEW" subtitle="autonomous soc — live posture">
        <div className="flex h-full items-center justify-center">
          <Mono className="text-muted">Loading...</Mono>
        </div>
      </Tile>
    );
  }

  return (
    <Tile
      id="overview"
      title="OVERVIEW"
      subtitle="autonomous soc — live posture"
      right={
        <div className="flex items-center gap-2">
          <Dot tone={state.connected ? "success" : "critical"} pulse={state.connected} />
          <Mono className="tabular-nums text-secondary">{clock}</Mono>
        </div>
      }
    >
      <div className="bg-grid h-full overflow-auto p-5">
        {}
        <div className="mb-5 grid grid-cols-2 gap-3 xl:grid-cols-4">
          <StatPanel label="cycles" value={String(cycles)} sub="MISS → PATCH → CATCH" tone="accent" />
          <StatPanel label="active incidents" value={String(active)} sub="require attention" tone="warning" />
          <StatPanel label="sealed" value={String(sealed)} sub="immutable records" tone="accent" />
          <StatPanel
            label="ecosystem health"
            value={`${health}%`}
            sub={`mode: ${state.eco.mode} — step ${state.eco.step}`}
            tone={health >= 60 ? "success" : "warning"}
          />
        </div>

        {}
        <Panel className="p-4">
          <div className="mb-3 flex items-baseline justify-between">
            <Mono tone="accent">top risk incidents</Mono>
            <Mono className="text-[9px]">top 8 of {incidents.length} tracked</Mono>
          </div>
          <div className="mb-1 grid grid-cols-[90px_110px_90px_110px_1fr] gap-3 border-b border-hairline pb-1">
            {["id", "host", "severity", "status", "risk"].map((h) => (
              <Mono key={h} className="text-[9px]">
                {h}
              </Mono>
            ))}
          </div>
          {top.map((inc: any) => (
            <Link
              key={inc.incident_id}
              href="/sentinel#incidents"
              className="row-interactive grid grid-cols-[90px_110px_90px_110px_1fr] items-center gap-3 border-b border-hairline/50 py-1.5 hover:bg-canvas-subtle"
            >
              <span className="font-mono text-[11px] text-primary">{inc.incident_id}</span>
              <span className="font-mono text-[10px] text-muted">{inc.host || "—"}</span>
              <span>
                <Chip tone={SEV_TONE[inc.severity] || "muted"}>{inc.severity || "—"}</Chip>
              </span>
              <span>
                <Chip tone={STATUS_TONE[inc.status] || "muted"}>{inc.status || "—"}</Chip>
              </span>
              <span className="flex items-center gap-2">
                <Bar value={inc.risk_score || inc.risk || 0} warning={(inc.risk_score || inc.risk || 0) >= 0.75} className="max-w-[220px]" />
                <span className="font-mono text-[10px] tabular-nums text-secondary">{(inc.risk_score || inc.risk || 0).toFixed(2)}</span>
              </span>
            </Link>
          ))}
        </Panel>
      </div>
    </Tile>
  );
}

function StatPanel({ label, value, sub, tone }: { label: string; value: string; sub: string; tone: "accent" | "warning" | "success" }) {
  return (
    <Panel className="p-4">
      <Mono className="mb-2 block">{label}</Mono>
      <div
        className={
          tone === "warning"
            ? "font-mono text-[26px] tabular-nums text-warning"
            : tone === "success"
              ? "font-mono text-[26px] tabular-nums text-success"
              : "font-mono text-[26px] tabular-nums text-accent"
        }
      >
        {value}
      </div>
      <Mono className="mt-1 block text-[9px] normal-case tracking-wider">{sub}</Mono>
    </Panel>
  );
}
