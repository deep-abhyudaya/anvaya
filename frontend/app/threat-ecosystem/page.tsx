"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function ThreatEcosystemRedirectPage() {
  return <LegacyRedirect to="/pathfinder" hash="threat-ecosystem" />;
}
