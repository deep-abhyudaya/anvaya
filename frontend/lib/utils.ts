import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { CSSProperties } from "react";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function cssStyle(vars?: Record<string, string>, rest?: CSSProperties): CSSProperties {
  const out: CSSProperties & Record<string, string | number | undefined> = { ...rest };
  for (const [k, v] of Object.entries(vars ?? {})) out[k] = v;
  return out;
}

export function cleanObjective(input?: string | null): string {
  const s = (input ?? "").trim();
  const idx = s.indexOf("\n\nContext:");
  if (idx >= 0) return s.slice(0, idx).trim();
  return s;
}
