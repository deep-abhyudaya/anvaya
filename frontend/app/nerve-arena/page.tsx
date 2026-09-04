"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function NerveArenaRedirectPage() {
  return <LegacyRedirect to="/responder" hash="nerve-arena" />;
}
