"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function TrophyWallRedirectPage() {
  return <LegacyRedirect to="/auditor" hash="trophy-wall" />;
}
