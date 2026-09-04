"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function SegmentsRedirectPage() {
  return <LegacyRedirect to="/pathfinder" hash="segments" />;
}
