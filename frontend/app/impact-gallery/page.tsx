"use client";

export const dynamic = "force-dynamic";

import { LegacyRedirect } from "@/components/legacy-redirect";

export default function ImpactGalleryRedirectPage() {
  return <LegacyRedirect to="/responder" hash="impact-gallery" />;
}
