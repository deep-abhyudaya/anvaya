"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { INCIDENTS } from "@/lib/data";
import { AnvayaAPI, useIncidents } from "@/lib/api";

export interface SlimIncident {
  id: string;
  title: string;
  status: string;
  severity: string;
  updatedAt?: string;
  sealedAt?: string;
}

const STATUS_ORDER: Record<string, number> = {
  active: 0,
  detected: 0,
  analyzed: 1,
  simulated: 2,
  explained: 3,
  contained: 4,
  sealed: 5,
  ignored: 6,
};

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  unknown: 4,
};

const DATE_ORDER: Record<string, number> = {
  Today: 0,
  Yesterday: 1,
  "This week": 2,
  Older: 3,
  Unknown: 4,
};

export function normalizeIncident(raw: {
  id?: string;
  incident_id?: string;
  title?: string;
  status?: unknown;
  severity?: unknown;
  updatedAt?: unknown;
  updated_at?: unknown;
  updated?: unknown;
  createdAt?: unknown;
  created_at?: unknown;
  sealedAt?: unknown;
  sealed_at?: unknown;
}): SlimIncident {
  const id = raw.incident_id || raw.id || "unknown";
  const title = raw.title || id;
  const updatedAt =
    (raw.updatedAt as string) ||
    (raw.updated_at as string) ||
    (raw.updated as string) ||
    (raw.createdAt as string) ||
    (raw.created_at as string);
  const sealedAt =
    (raw.sealedAt as string) || (raw.sealed_at as string);
  return {
    id,
    title,
    status: String(raw.status || "active").toLowerCase(),
    severity: String(raw.severity || "medium").toLowerCase(),
    updatedAt,
    sealedAt,
  };
}

export function useIncidentList() {
  const { data } = useIncidents(5000);
  return useMemo(() => {
    const rawItems = (data?.items as Array<Record<string, unknown>> | undefined) || [];
    if (rawItems.length > 0) return rawItems.map(normalizeIncident);
    return INCIDENTS.map(normalizeIncident);
  }, [data]);
}

export function useCreateIncident(onSuccess?: () => void) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (title: string) =>
      AnvayaAPI.createIncident({
        title,
        severity: "medium",
        attack_family: "unknown",
        host: "unknown",
        user: "unknown",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      onSuccess?.();
    },
  });
}

export function openIncident(router: ReturnType<typeof useRouter>, inc: SlimIncident) {
  if (inc.id === "INC-2214") {
    router.push("/responder#miss-replay");
  } else if (inc.status === "sealed") {
    router.push("/auditor#trophy-wall");
  } else {
    router.push("/sentinel#risk-orbits");
  }
}

export function dateBucket(input?: string): string {
  if (!input) return "Unknown";
  const s = input.toLowerCase();
  if (s.includes("today")) return "Today";
  if (s.includes("yesterday")) return "Yesterday";

  const d = new Date(input);
  if (!isNaN(d.getTime())) {
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const days = Math.floor(diff / 86400000);
    if (days <= 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return "This week";
    return "Older";
  }

  if (s.includes("may") || s.includes("apr") || s.includes("jun") || s.includes("jul")) {
    return "Older";
  }

  if (s.match(/^\d{1,2}:\d{2}(:\d{2})?$/)) return "Today";

  return "Unknown";
}

export type GroupByKey = "none" | "status" | "severity" | "date";

export interface GroupedIncidents {
  key: string;
  label: string;
  items: SlimIncident[];
}

function groupLabel(key: string, by: GroupByKey): string {
  if (by === "date") return key;
  return key.charAt(0).toUpperCase() + key.slice(1);
}

export function groupIncidents(
  items: SlimIncident[],
  by: GroupByKey
): GroupedIncidents[] {
  if (by === "none") return [{ key: "all", label: "", items }];

  const map = new Map<string, SlimIncident[]>();
  items.forEach((item) => {
    let key: string;
    switch (by) {
      case "status":
        key = item.status;
        break;
      case "severity":
        key = item.severity;
        break;
      case "date":
        key = dateBucket(item.sealedAt || item.updatedAt);
        break;
      default:
        key = "all";
    }
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(item);
  });

  const order =
    by === "status"
      ? STATUS_ORDER
      : by === "severity"
      ? SEVERITY_ORDER
      : DATE_ORDER;

  const sorted = [...map.entries()].sort(
    ([a], [b]) => (order[a] ?? 99) - (order[b] ?? 99)
  );

  return sorted.map(([key, groupItems]) => ({
    key,
    label: groupLabel(key, by),
    items: groupItems,
  }));
}
