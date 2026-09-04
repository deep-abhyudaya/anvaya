"use client";

export const dynamic = "force-dynamic";

import { Suspense } from "react";
import { type Layout } from "react-grid-layout";
import { AppShell } from "@/components/app-shell";
import { useTileAnchor } from "@/components/tiles/use-tile-anchor";
import { TileSkeleton } from "@/components/tiles/tile-shell";
import OverviewTile from "@/components/tiles/overview-tile";
import IncidentsTile from "@/components/tiles/incidents-tile";
import RiskOrbitsTile from "@/components/tiles/risk-orbits-tile";
import { TileGrid, useTileLayout, ResetLayoutButton } from "@/components/tile-grid";

const TILE_CONSTRAINTS: Record<string, { minW?: number; minH?: number }> = {
  overview: { minW: 3, minH: 2 },
  incidents: { minW: 4, minH: 2 },
  "risk-orbits": { minW: 4, minH: 2 },
};

const DEFAULT_SENTINEL_LAYOUT: Layout = [
  { i: "overview", x: 0, y: 0, w: 4, h: 2, minW: 3, minH: 2 },
  { i: "incidents", x: 4, y: 0, w: 8, h: 4, minW: 4, minH: 2 },
  { i: "risk-orbits", x: 0, y: 2, w: 12, h: 2, minW: 4, minH: 2 },
];

export default function SentinelPage() {
  useTileAnchor();
  const { layout, setLayout, reset } = useTileLayout(
    "sentinel",
    DEFAULT_SENTINEL_LAYOUT,
    TILE_CONSTRAINTS
  );

  return (
    <AppShell
      title="SENTINEL"
      subtitle="detection engine"
      live
      right={<ResetLayoutButton onClick={reset} />}
    >
      <div className="h-full p-3">
        <TileGrid layout={layout} onLayoutChange={setLayout} maxRows={5}>
          <div key="overview" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="OVERVIEW"
                  subtitle="autonomous soc — live posture"
                />
              }
            >
              <OverviewTile />
            </Suspense>
          </div>
          <div key="incidents" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="INCIDENTS"
                  subtitle="unified lifecycle — detected → analyzed → simulated → explained → sealed"
                />
              }
            >
              <IncidentsTile />
            </Suspense>
          </div>
          <div key="risk-orbits" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="RISK ORBITS"
                  subtitle="distance from safety · real-time view"
                />
              }
            >
              <RiskOrbitsTile />
            </Suspense>
          </div>
        </TileGrid>
      </div>
    </AppShell>
  );
}
