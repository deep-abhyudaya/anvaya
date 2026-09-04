"use client";

import { useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Tile } from "./tile-shell";
import { OrbitNetwork } from "@/components/orbit-network";
import { ProjectGuard } from "@/components/project-guard";
import { Mono, Panel } from "@/components/primitives";
import { useProjectArtifactLatest } from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { BuildTimeline, BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { useArtifactSource } from "@/lib/build";

const PERIODS = ["last 24h", "last 7d", "last 30d"];

type OrbitNode = {
  id: string;
  label?: string;
  impact_score?: number;
  is_compromised?: boolean;
  source_events?: number;
  dest_events?: number;
};

type OrbitEdge = {
  orbit_id?: string;
  source: string;
  target: string;
  forward_count?: number;
  reverse_count?: number;
  risk_score?: number;
  event_count?: number;
};

function isOrbitNode(d: unknown): d is OrbitNode {
  if (typeof d !== "object" || d === null) return false;
  const obj = d as Record<string, unknown>;
  return (
    typeof obj.id === "string" &&
    (typeof obj.impact_score === "number" || typeof obj.is_compromised === "boolean")
  );
}

function isOrbitEdge(d: unknown): d is OrbitEdge {
  if (typeof d !== "object" || d === null) return false;
  const obj = d as Record<string, unknown>;
  return typeof obj.source === "string" && typeof obj.target === "string";
}

type OrbitsPayload = {
  node_count?: number;
  edge_count?: number;
  top_nodes?: OrbitNode[];
  orbits?: OrbitEdge[];
  blast_radius?: { affected_count?: number };
};

export default function RiskOrbitsTile() {
  const params = useSearchParams();
  const buildId = params.get("build") || "";
  const build = useArtifactBuild(buildId || undefined);

  const { state } = useAnvaya();
  const projectId = state.activeProjectId || "";
  const [period, setPeriod] = useState(state.orbits.period || PERIODS[0]);
  const { data, isLoading, isError } = useProjectArtifactLatest(projectId, "orbits");
  const payload = (data?.payload as OrbitsPayload | null | undefined) || null;

  const { data: sourceNodes, isBuilding } = useArtifactSource<OrbitNode>(
    build,
    payload?.top_nodes,
    isLoading,
    isError,
    "orbits",
    isOrbitNode
  );
  const { data: sourceOrbits } = useArtifactSource<OrbitEdge>(
    build,
    payload?.orbits,
    isLoading,
    isError,
    "orbits",
    isOrbitEdge
  );

  const networkPayload = useMemo(() => {
    if (sourceNodes.length === 0 && sourceOrbits.length === 0 && !payload) return null;
    const nodes = sourceNodes;
    const orbits = sourceOrbits;

    // Aggregate per-node event totals from the actual orbits. The node "risk"
    // displayed on the map is derived from these totals, not from the backend
    // graph degree (impact_score), so a high-risk node can never show 0 events.
    const totals = new Map<string, { source: number; destination: number }>();
    const allNodeIds = new Set<string>();
    for (const node of nodes) allNodeIds.add(node.id);
    for (const orbit of orbits) {
      allNodeIds.add(orbit.source);
      allNodeIds.add(orbit.target);
      const source = totals.get(orbit.source) || { source: 0, destination: 0 };
      source.source += orbit.forward_count ?? orbit.event_count ?? 0;
      source.destination += orbit.reverse_count ?? 0;
      totals.set(orbit.source, source);
      const target = totals.get(orbit.target) || { source: 0, destination: 0 };
      target.source += orbit.reverse_count ?? 0;
      target.destination += orbit.forward_count ?? orbit.event_count ?? 0;
      totals.set(orbit.target, target);
    }

    const baseNodeById = new Map(nodes.map((node) => [node.id, node]));
    const labelById = new Map<string, string>();
    for (const id of allNodeIds) {
      const node = baseNodeById.get(id);
      labelById.set(id, node?.label || node?.id || id);
    }

    const activeNodes = Array.from(allNodeIds).map((id) => {
      const node = baseNodeById.get(id);
      const impact = typeof node?.impact_score === "number" ? node.impact_score : 0;
      return {
        id,
        label: labelById.get(id) || id,
        impact_score: impact,
        is_compromised: !!node?.is_compromised,
        source_events: totals.get(id)?.source ?? 0,
        dest_events: totals.get(id)?.destination ?? 0,
      };
    });

    const maxTotal = Math.max(
      1,
      ...activeNodes.map((n) => n.source_events + n.dest_events)
    );
    const topNodes = activeNodes.map((node) => ({
      ...node,
      risk: (node.source_events + node.dest_events) / maxTotal,
    }));

    const stats = {
      active: topNodes.filter((n) => n.is_compromised || n.risk >= 0.5).length,
      sealed: topNodes.filter((n) => !n.is_compromised && n.risk < 0.5).length,
      critical: topNodes.filter((n) => n.risk >= 0.75).length,
    };

    return {
      node_count: payload?.node_count ?? allNodeIds.size,
      edge_count: payload?.edge_count ?? orbits.length,
      stats,
      top_nodes: topNodes,
      top_edges: orbits.map((orbit) => ({
        source: labelById.get(orbit.source) || orbit.source,
        target: labelById.get(orbit.target) || orbit.target,
        count:
          (orbit.forward_count ?? 0) + (orbit.reverse_count ?? 0) ||
          orbit.event_count ||
          0,
      })),
      orbits: orbits.map((orbit) => ({
        a: labelById.get(orbit.source) || orbit.source,
        b: labelById.get(orbit.target) || orbit.target,
        a_to_b_count: orbit.forward_count ?? 0,
        b_to_a_count: orbit.reverse_count ?? 0,
        risk_score: orbit.risk_score ?? 0,
      })),
    };
  }, [sourceNodes, sourceOrbits, payload]);

  const showBuildShell = isBuilding;
  const hasNetwork = networkPayload && networkPayload.top_nodes.length > 0;

  const center = networkPayload ? (
    <span className="flex items-center gap-4 text-[10px] uppercase tracking-widest text-muted">
      <span className="text-accent">{networkPayload.stats.active} active</span>
      <span className="text-muted">·</span>
      <span>{networkPayload.stats.sealed} sealed</span>
      <span className="text-muted">·</span>
      <span className="text-warning">critical: {networkPayload.stats.critical}</span>
    </span>
  ) : (
    <span />
  );

  const right = (
    <select
      value={period}
      onChange={(e) => setPeriod(e.target.value)}
      className="h-7 border border-hairline bg-canvas-panel px-2 font-mono text-[10px] text-secondary outline-none focus:border-accent/40"
    >
      {PERIODS.map((p) => (
        <option key={p} value={p}>
          {p}
        </option>
      ))}
    </select>
  );

  return (
    <Tile
      id="risk-orbits"
      title="RISK ORBITS"
      subtitle="distance from safety · real-time view"
      center={center}
      right={right}
    >
      <ProjectGuard>
        {build && <BuildStatus state={build} />}
        <div className="flex h-full w-full gap-3 bg-grid p-3">
          <div className="flex min-w-0 flex-1 flex-col gap-3">
            {showBuildShell && !hasNetwork ? (
              <ArtifactState message="Building orbits workspace..." />
            ) : hasNetwork ? (
              <OrbitNetwork payload={networkPayload} />
            ) : isLoading ? (
              <ArtifactState message="Loading project orbits..." />
            ) : isError || !payload ? (
              <ArtifactState message="No orbits artifact has been generated for this project." />
            ) : (
              <ArtifactState message="This orbits artifact contains no nodes to plot." />
            )}
          </div>
          <div className="flex h-full w-[320px] shrink-0 flex-col gap-3">
            {build && <BuildTimeline state={build} />}
            <Panel className="flex w-full flex-1 flex-col gap-3 p-4">
              <Mono tone="primary">STRONGEST ORBITS</Mono>
              {sourceOrbits.length === 0 ? (
                <Mono>No bidirectional interactions were found.</Mono>
              ) : (
                sourceOrbits.slice(0, 12).map((orbit) => (
                  <div
                    key={orbit.orbit_id || `${orbit.source}-${orbit.target}`}
                    id={`build-el-orbits-edge-${orbit.source}-${orbit.target}`}
                    className="border-b border-hairline pb-2"
                  >
                    <div className="truncate font-mono text-[10px] text-primary">
                      {orbit.source} ↔ {orbit.target}
                    </div>
                    <div className="mt-1 flex justify-between">
                      <Mono>
                        {orbit.forward_count ?? 0} → / {orbit.reverse_count ?? 0} ←
                      </Mono>
                      <Mono tone={(orbit.risk_score ?? 0) >= 0.75 ? "warning" : "accent"}>
                        risk {(orbit.risk_score ?? 0).toFixed(2)}
                      </Mono>
                    </div>
                  </div>
                ))
              )}
              <div className="mt-auto border-t border-hairline pt-3">
                <Mono className="block">edges: {payload?.edge_count ?? networkPayload?.edge_count ?? "—"}</Mono>
                <Mono className="mt-1 block">blast affected: {payload?.blast_radius?.affected_count ?? "—"}</Mono>
              </div>
            </Panel>
          </div>
        </div>
      </ProjectGuard>
    </Tile>
  );
}

function ArtifactState({ message }: { message: string }) {
  return (
    <div className="flex h-full items-center justify-center p-8 text-center">
      <Mono className="text-muted">{message}</Mono>
    </div>
  );
}
