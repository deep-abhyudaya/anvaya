"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function HistoryRedirectPage() {
  return <LegacyRedirect to="/auditor" hash="history" />;
}
