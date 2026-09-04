"use client";

export const dynamic = "force-dynamic";

import { Suspense } from "react";
import { type Layout } from "react-grid-layout";
import { AppShell } from "@/components/app-shell";
import { useTileAnchor } from "@/components/tiles/use-tile-anchor";
import { TileSkeleton } from "@/components/tiles/tile-shell";
import MissReplayTile from "@/components/tiles/miss-replay-tile";
import NerveArenaTile from "@/components/tiles/nerve-arena-tile";
import ImpactGalleryTile from "@/components/tiles/impact-gallery-tile";
import { TileGrid, useTileLayout, ResetLayoutButton } from "@/components/tile-grid";

const TILE_CONSTRAINTS: Record<string, { minW?: number; minH?: number }> = {
  "miss-replay": { minW: 5, minH: 2 },
  "nerve-arena": { minW: 3, minH: 2 },
  "impact-gallery": { minW: 5, minH: 2 },
};

const DEFAULT_RESPONDER_LAYOUT: Layout = [
  { i: "miss-replay", x: 0, y: 0, w: 8, h: 3, minW: 5, minH: 2 },
  { i: "nerve-arena", x: 8, y: 0, w: 4, h: 3, minW: 3, minH: 2 },
  { i: "impact-gallery", x: 0, y: 3, w: 12, h: 2, minW: 5, minH: 2 },
];

export default function ResponderPage() {
  useTileAnchor();
  const { layout, setLayout, reset } = useTileLayout(
    "responder",
    DEFAULT_RESPONDER_LAYOUT,
    TILE_CONSTRAINTS
  );

  return (
    <AppShell
      title="RESPONDER"
      subtitle="response & remediation"
      live
      right={<ResetLayoutButton onClick={reset} />}
    >
      <div className="h-full p-3">
        <TileGrid layout={layout} onLayoutChange={setLayout} maxRows={5}>
          <div key="miss-replay" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="MISS REPLAY TRACK"
                  subtitle="self-healing timeline scrubber"
                />
              }
            >
              <MissReplayTile />
            </Suspense>
          </div>
          <div key="nerve-arena" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="NERVE ARENA"
                  subtitle="engine voting ring — real-time consensus"
                />
              }
            >
              <NerveArenaTile />
            </Suspense>
          </div>
          <div key="impact-gallery" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="IMPACT TREE GALLERY"
                  subtitle="project-derived affected-asset archive"
                />
              }
            >
              <ImpactGalleryTile />
            </Suspense>
          </div>
        </TileGrid>
      </div>
    </AppShell>
  );
}
