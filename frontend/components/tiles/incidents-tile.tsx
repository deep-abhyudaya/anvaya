"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Tile } from "./tile-shell";
import { ProjectGuard } from "@/components/project-guard";
import { Bar, Chip, Mono, Tabs } from "@/components/primitives";
import { AnvayaAPI, useProjectArtifactLatest } from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { BuildTimeline, BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { useArtifactSource } from "@/lib/build";

const STATUS_FILTERS = ["ALL", "ACTIVE", "SEALED", "CONTAINED", "IGNORED"];
const SEV_TONE: Record<string, "warning" | "accent" | "muted"> = {
  critical: "warning", high: "warning", medium: "accent", low: "muted",
};
const STATUS_TONE: Record<string, "warning" | "accent" | "success" | "muted"> = {
  active: "warning", sealed: "accent", contained: "success", ignored: "muted",
};

type Incident = {
  incident_id: string;
  title?: string;
  severity?: string;
  status?: string;
  host?: string;
  user?: string;
  attack_family?: string;
  event_count?: number;
  first_seen?: string;
  last_seen?: string;
  blast_radius_score?: number;
  risk_score?: number;
};

export default function IncidentsTile() {
  return (
    <Tile
      id="incidents"
      title="INCIDENTS"
      subtitle="unified lifecycle — detected → analyzed → simulated → explained → sealed"
    >
      <ProjectGuard>
        <IncidentsBody />
      </ProjectGuard>
    </Tile>
  );
}

function IncidentsBody() {
  const params = useSearchParams();
  const buildId = params.get("build") || "";
  const build = useArtifactBuild(buildId || undefined);

  const { state } = useAnvaya();
  const [filter, setFilter] = useState("ALL");
  const [liveRows, setLiveRows] = useState<Incident[]>([]);
  const projectId = state.activeProjectId || "";
  const { data, isLoading, isError } = useProjectArtifactLatest(projectId, "incidents");
  const payload = data?.payload as { incidents?: Incident[] } | null | undefined;

  const { data: incidents, isBuilding } = useArtifactSource<Incident>(
    build,
    payload?.incidents,
    isLoading,
    isError,
    "incidents"
  );

  useEffect(() => {
    let cancelled = false;
    const fetchLive = async () => {
      try {
        const res = (await AnvayaAPI.incidents()) as {
          items: Array<Record<string, unknown>>;
        };
        if (cancelled) return;
        const mapped: Incident[] = res.items.map((item) => ({
          incident_id: String(item.incident_id),
          title: item.title ? String(item.title) : undefined,
          severity: item.severity ? String(item.severity) : undefined,
          status: item.status ? String(item.status) : undefined,
          host: item.host ? String(item.host) : undefined,
          user: item.user ? String(item.user) : undefined,
          attack_family: item.attack_family ? String(item.attack_family) : undefined,
          first_seen: item.created_at ? String(item.created_at) : undefined,
          last_seen: item.updated_at ? String(item.updated_at) : undefined,
          risk_score: typeof item.risk_score === "number" ? item.risk_score : undefined,
          event_count: typeof item.event_count === "number" ? item.event_count : undefined,
        }));
        setLiveRows(mapped);
      } catch {
      }
    };
    fetchLive();
    const id = setInterval(fetchLive, 4000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const displayRows = useMemo(() => {
    const byId = new Map<string, Incident>();
    for (const inc of [...liveRows, ...incidents]) {
      if (!inc?.incident_id) continue;
      if (!byId.has(inc.incident_id)) {
        byId.set(inc.incident_id, inc);
      }
    }
    return Array.from(byId.values());
  }, [liveRows, incidents]);

  const rows = displayRows.filter((incident) =>
    filter === "ALL" ? true : incident.status?.toLowerCase() === filter.toLowerCase()
  );

  const showBuildShell = isBuilding;

  return (
    <>
      {build && <BuildStatus state={build} />}
      {showBuildShell ? (
        <div className="flex h-full flex-col gap-3">
          <div className="bg-grid flex h-full flex-col">
            <div className="flex items-center justify-between border-b border-hairline px-6 py-2.5">
              <Tabs items={STATUS_FILTERS} value={filter} onChange={setFilter} />
              <Mono className="tabular-nums">{rows.length} records</Mono>
            </div>
            <div className="flex min-h-0 flex-1 gap-3 overflow-hidden p-3">
              <div className="flex min-w-0 flex-1 flex-col overflow-auto">
                {rows.length === 0 ? (
                  <ArtifactState message="Building incidents workspace..." />
                ) : (
                  <IncidentTable rows={rows} />
                )}
              </div>
              <div className="flex h-full w-[320px] shrink-0 flex-col gap-3">
                {build && <BuildTimeline state={build} />}
              </div>
            </div>
          </div>
        </div>
      ) : isLoading && incidents.length === 0 ? (
        <ArtifactState message="Loading project incidents..." />
      ) : isError || (!payload && incidents.length === 0) ? (
        <ArtifactState message="No incidents artifact has been generated for this project." />
      ) : (
        <div className="bg-grid flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-hairline px-6 py-2.5">
            <Tabs items={STATUS_FILTERS} value={filter} onChange={setFilter} />
            <Mono className="tabular-nums">{rows.length} records</Mono>
          </div>
          <div className="flex-1 overflow-auto px-6 py-3">
            <IncidentTable rows={rows} />
            {rows.length === 0 && (
              <ArtifactState
                message={
                  incidents.length
                    ? `No incidents match ${filter.toLowerCase()}.`
                    : "This incidents artifact contains no incidents."
                }
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}

function IncidentTable({ rows }: { rows: Incident[] }) {
  return (
    <table className="mt-2 w-full border-collapse">
      <thead>
        <tr className="border-b border-hairline text-left">
          {["id", "title", "host", "user", "category", "severity", "status", "events", "risk", "first seen"].map((heading) => (
            <th key={heading} className="pb-2 pr-4 font-mono text-[9px] font-normal uppercase tracking-wider text-muted">{heading}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((incident) => {
          const risk = typeof incident.risk_score === "number" ? incident.risk_score : 0;
          return (
            <tr
              key={incident.incident_id}
              id={`build-el-incidents-${incident.incident_id}`}
              className="border-b border-hairline/50"
            >
              <td className="py-2 pr-4 font-mono text-[11px] text-primary">{incident.incident_id}</td>
              <td className="py-2 pr-4 font-mono text-[10px] lowercase tracking-wider text-secondary">{incident.title || "—"}</td>
              <td className="py-2 pr-4 font-mono text-[10px] text-muted">{incident.host || "—"}</td>
              <td className="py-2 pr-4 font-mono text-[10px] text-muted">{incident.user || "—"}</td>
              <td className="py-2 pr-4 font-mono text-[10px] uppercase tracking-wider text-muted">{incident.attack_family || "—"}</td>
              <td className="py-2 pr-4"><Chip tone={SEV_TONE[incident.severity || ""] || "muted"}>{incident.severity || "—"}</Chip></td>
              <td className="py-2 pr-4"><Chip tone={STATUS_TONE[incident.status || ""] || "muted"}>{incident.status || "—"}</Chip></td>
              <td className="py-2 pr-4 font-mono text-[10px] tabular-nums text-muted">{incident.event_count ?? "—"}</td>
              <td className="py-2 pr-4">
                <div className="flex w-32 items-center gap-2">
                  <Bar value={risk} warning={risk >= 0.75} />
                  <span className="font-mono text-[10px] tabular-nums text-secondary">{risk.toFixed(2)}</span>
                </div>
              </td>
              <td className="py-2 font-mono text-[10px] tabular-nums text-muted">{incident.first_seen ? new Date(incident.first_seen).toLocaleString() : "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ArtifactState({ message }: { message: string }) {
  return <div className="flex h-full min-h-32 items-center justify-center p-8 text-center"><Mono className="text-muted">{message}</Mono></div>;
}
