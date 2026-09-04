"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function LedgerRedirectPage() {
  return <LegacyRedirect to="/auditor" hash="ledger" />;
}
