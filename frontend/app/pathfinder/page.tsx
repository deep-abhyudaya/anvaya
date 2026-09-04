"use client";

export const dynamic = "force-dynamic";

import { Suspense } from "react";
import { type Layout } from "react-grid-layout";
import { AppShell } from "@/components/app-shell";
import { useTileAnchor } from "@/components/tiles/use-tile-anchor";
import { TileSkeleton } from "@/components/tiles/tile-shell";
import ReachBoardTile from "@/components/tiles/reach-board-tile";
import SegmentsTile from "@/components/tiles/segments-tile";
import ThreatEcosystemTile from "@/components/tiles/threat-ecosystem-tile";
import { TileGrid, useTileLayout, ResetLayoutButton } from "@/components/tile-grid";

const TILE_CONSTRAINTS: Record<string, { minW?: number; minH?: number }> = {
  "threat-ecosystem": { minW: 4, minH: 2 },
  "reach-board": { minW: 5, minH: 2 },
  segments: { minW: 5, minH: 2 },
};

const DEFAULT_PATHFINDER_LAYOUT: Layout = [
  { i: "threat-ecosystem", x: 0, y: 0, w: 12, h: 2, minW: 4, minH: 2 },
  { i: "reach-board", x: 0, y: 2, w: 6, h: 3, minW: 5, minH: 2 },
  { i: "segments", x: 6, y: 2, w: 6, h: 3, minW: 5, minH: 2 },
];

export default function PathfinderPage() {
  useTileAnchor();
  const { layout, setLayout, reset } = useTileLayout(
    "pathfinder",
    DEFAULT_PATHFINDER_LAYOUT,
    TILE_CONSTRAINTS
  );

  return (
    <AppShell
      title="PATHFINDER"
      subtitle="attack surface & graph traversal"
      right={<ResetLayoutButton onClick={reset} />}
    >
      <div className="h-full p-3">
        <TileGrid layout={layout} onLayoutChange={setLayout} maxRows={5}>
          <div key="threat-ecosystem" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="THREAT ECOSYSTEM"
                  subtitle="predator-prey-defender network simulation"
                />
              }
            >
              <ThreatEcosystemTile />
            </Suspense>
          </div>
          <div key="reach-board" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="REACH DRAFT BOARD"
                  subtitle="ranked asset reachability — attacker and defender viewpoints"
                />
              }
            >
              <ReachBoardTile />
            </Suspense>
          </div>
          <div key="segments" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="SEGMENTS TRACKED"
                  subtitle="network segment topology"
                />
              }
            >
              <SegmentsTile />
            </Suspense>
          </div>
        </TileGrid>
      </div>
    </AppShell>
  );
}
