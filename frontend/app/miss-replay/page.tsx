"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function MissReplayRedirectPage() {
  return <LegacyRedirect to="/responder" hash="miss-replay" />;
}
