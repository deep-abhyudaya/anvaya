"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function IncidentsRedirectPage() {
  return <LegacyRedirect to="/sentinel" hash="incidents" />;
}
