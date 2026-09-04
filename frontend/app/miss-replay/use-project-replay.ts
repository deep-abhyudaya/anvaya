"use client";

import { useMemo } from "react";
import { useProjectArtifactLatest } from "@/lib/api";
import type { ReplayEvent } from "@/lib/data";

export interface ReplayData {
  incidentId: string;
  host: string;
  user: string;
  status: string;
  verified: boolean;
  startClock: string;
  duration: number;
  events: ReplayEvent[];
  preNote: { at: number; text: string };
  stages: readonly string[];
}

const STAGE_TONE: Record<string, "muted" | "warning" | "accent"> = {
  "PROCESS SPAWN": "muted",
  MISS: "warning",
  "GROUND TRUTH": "warning",
  "RULE PROPOSED": "warning",
  "RE-RUN": "accent",
  CAUGHT: "accent",
};

export function toReplayData(raw: unknown): ReplayData | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;

  const duration = typeof r.duration === "number" ? r.duration : 320;
  const rawStart = (r.start_time as string) || "14:00:00";
  const startTime = rawStart.includes("T")
    ? rawStart.split("T")[1].split(".")[0]
    : rawStart;
  const stages = ((r.stages as any[]) || []).map((s) => s.name as string);

  const timeline = ((r.timeline as any[]) || []).map((e, i) => {
    const t = typeof e.t === "number" ? e.t : i * (duration / Math.max((r.timeline as any[] | undefined)?.length || 1, 1));
    const label = (e.label || "").toLowerCase();
    const tone = e.tone || (label.includes("caught") || label.includes("re-run") ? "accent" : "warning");
    const lane = e.lane || "both";
    return {
      t,
      label: e.label || "event",
      sub: e.sub,
      tone: tone as ReplayEvent["tone"],
      lane: lane as ReplayEvent["lane"],
      hollow: e.hollow,
    };
  });

  const stageEvents: ReplayEvent[] = stages.map((name, i) => ({
    t: (i / Math.max(stages.length, 1)) * duration,
    label: name.toLowerCase(),
    sub: i === 3 ? ((r.rule_after as string) || "rule proposed") : undefined,
    tone: STAGE_TONE[name] || "muted",
    lane: i >= 4 ? "post" : "both",
  }));

  const combined = [...stageEvents];
  for (const e of timeline) {
    if (!combined.some((c) => c.label === e.label && Math.abs(c.t - e.t) < 1)) {
      combined.push(e);
    }
  }
  combined.sort((a, b) => a.t - b.t);

  return {
    incidentId: (r.incident_id as string) || "INC-0000",
    host: (r.host as string) || "unknown",
    user: (r.user as string) || "unknown",
    status: (r.status as string) || "pending",
    verified: r.verified === true,
    startClock: startTime,
    duration,
    events: combined,
    preNote: (r.pre_note as { at: number; text: string }) || { at: Math.max(0, duration - 20), text: "no detection fired" },
    stages: stages.length ? (stages as readonly string[]) : (["PROCESS SPAWN", "MISS", "GROUND TRUTH", "RULE PROPOSED", "RE-RUN", "CAUGHT"] as const),
  };
}

export function useProjectReplay(projectId: string): ReplayData | null {
  const { data } = useProjectArtifactLatest(projectId, "replay");

  return useMemo(() => {
    const payload = (data?.payload as any) || null;
    const replays = payload?.replays as any[] | undefined;
    if (!replays || replays.length === 0) return null;
    return toReplayData(replays[0]);
  }, [data]);
}
