"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function RiskOrbitsRedirectPage() {
  return <LegacyRedirect to="/sentinel" hash="risk-orbits" />;
}
