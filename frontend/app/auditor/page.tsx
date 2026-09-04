"use client";

export const dynamic = "force-dynamic";

import { Suspense } from "react";
import { type Layout } from "react-grid-layout";
import { AppShell } from "@/components/app-shell";
import { useTileAnchor } from "@/components/tiles/use-tile-anchor";
import { TileSkeleton } from "@/components/tiles/tile-shell";
import TrophyWallTile from "@/components/tiles/trophy-wall-tile";
import LedgerTile from "@/components/tiles/ledger-tile";
import HistoryTile from "@/components/tiles/history-tile";
import { TileGrid, useTileLayout, ResetLayoutButton } from "@/components/tile-grid";

const TILE_CONSTRAINTS: Record<string, { minW?: number; minH?: number }> = {
  "trophy-wall": { minW: 4, minH: 2 },
  ledger: { minW: 3, minH: 2 },
  history: { minW: 4, minH: 2 },
};

const DEFAULT_AUDITOR_LAYOUT: Layout = [
  { i: "trophy-wall", x: 0, y: 0, w: 8, h: 3, minW: 4, minH: 2 },
  { i: "ledger", x: 8, y: 0, w: 4, h: 3, minW: 3, minH: 2 },
  { i: "history", x: 0, y: 3, w: 12, h: 2, minW: 4, minH: 2 },
];

export default function AuditorPage() {
  useTileAnchor();
  const { layout, setLayout, reset } = useTileLayout(
    "auditor",
    DEFAULT_AUDITOR_LAYOUT,
    TILE_CONSTRAINTS
  );

  return (
    <AppShell
      title="AUDITOR"
      subtitle="record-keeping & compliance"
      right={<ResetLayoutButton onClick={reset} />}
    >
      <div className="h-full p-3">
        <TileGrid layout={layout} onLayoutChange={setLayout} maxRows={5}>
          <div key="trophy-wall" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="SEALED TROPHY WALL"
                  subtitle="project-derived incident trophies and computed rarity"
                />
              }
            >
              <TrophyWallTile />
            </Suspense>
          </div>
          <div key="ledger" className="h-full w-full">
            <Suspense
              fallback={
                <TileSkeleton
                  title="LEDGER"
                  subtitle="project-scoped generation audit records"
                />
              }
            >
              <LedgerTile />
            </Suspense>
          </div>
          <div key="history" className="h-full w-full">
            <Suspense
              fallback={<TileSkeleton title="HISTORY" subtitle="Agent conversation log" />}
            >
              <HistoryTile />
            </Suspense>
          </div>
        </TileGrid>
      </div>
    </AppShell>
  );
}
