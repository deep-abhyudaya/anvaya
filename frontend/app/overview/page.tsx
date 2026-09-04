"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function OverviewRedirectPage() {
  return <LegacyRedirect to="/sentinel" hash="overview" />;
}
