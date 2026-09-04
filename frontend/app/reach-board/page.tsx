"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function ReachBoardRedirectPage() {
  return <LegacyRedirect to="/pathfinder" hash="reach-board" />;
}
