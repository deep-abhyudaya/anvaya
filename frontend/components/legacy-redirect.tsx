"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function LegacyRedirect({
  to,
  hash,
}: {
  to: string;
  hash: string;
}) {
  const router = useRouter();

  useEffect(() => {
    const qs = typeof window !== "undefined" ? window.location.search : "";
    const url = `${to}${qs}${hash ? `#${hash}` : ""}`;
    router.replace(url);
  }, [router, to, hash]);

  return null;
}
