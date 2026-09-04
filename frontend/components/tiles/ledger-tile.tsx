"use client";

import { useSearchParams } from "next/navigation";
import { Tile } from "@/components/tiles/tile-shell";
import { ProjectGuard } from "@/components/project-guard";
import { Mono, Panel } from "@/components/primitives";
import { useProjectArtifactLatest } from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { BuildTimeline, BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { useArtifactSource } from "@/lib/build";

type LedgerRecord = {
  record_id: string;
  action?: string;
  subject?: string;
  dataset_id?: string;
  fingerprint?: string;
  artifact_count?: number;
  rows?: number;
  entities?: number;
  incidents?: number;
  timestamp?: string;
};
type LedgerPayload = { fingerprint?: string; records?: LedgerRecord[] };

export default function LedgerTile() {
  return (
    <Tile
      id="ledger"
      title="LEDGER"
      subtitle="project-scoped generation audit records"
    >
      <ProjectGuard>
        <LedgerBody />
      </ProjectGuard>
    </Tile>
  );
}

function LedgerBody() {
  const params = useSearchParams();
  const buildId = params.get("build") || "";
  const build = useArtifactBuild(buildId || undefined);

  const { state } = useAnvaya();
  const projectId = state.activeProjectId || "";
  const { data, isLoading, isError } = useProjectArtifactLatest(projectId, "ledger");
  const payload = data?.payload as LedgerPayload | null | undefined;

  const { data: records, isBuilding } = useArtifactSource<LedgerRecord>(
    build,
    payload?.records,
    isLoading,
    isError,
    "ledger"
  );

  const showBuildShell = isBuilding;

  return (
    <>
      {build && <BuildStatus state={build} />}
      {showBuildShell ? (
        <div className="bg-grid flex h-full gap-3 p-3">
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="flex items-center gap-4 border-b border-hairline px-6 py-2.5">
              <Mono className="tabular-nums">{records.length} audit records</Mono>
              {payload?.fingerprint && <Mono className="ml-auto max-w-[50%] truncate tabular-nums">dataset fingerprint: {payload.fingerprint}</Mono>}
            </div>
            <div className="flex-1 overflow-auto px-6 py-3">
              {records.length === 0 ? (
                <ArtifactState message="Building ledger workspace..." />
              ) : (
                <Panel>
                  <LedgerTable records={records} />
                </Panel>
              )}
            </div>
          </div>
          <div className="flex h-full w-[320px] shrink-0 flex-col gap-3">
            {build && <BuildTimeline state={build} />}
          </div>
        </div>
      ) : isLoading && records.length === 0 ? (
        <ArtifactState message="Loading project ledger..." />
      ) : isError || (!payload && records.length === 0) ? (
        <ArtifactState message="No ledger artifact has been generated for this project." />
      ) : (
        <div className="bg-grid flex h-full flex-col">
          <div className="flex items-center gap-4 border-b border-hairline px-6 py-2.5">
            <Mono className="tabular-nums">{records.length} audit records</Mono>
            {payload?.fingerprint && <Mono className="ml-auto max-w-[50%] truncate tabular-nums">dataset fingerprint: {payload.fingerprint}</Mono>}
          </div>
          <div className="flex-1 overflow-auto px-6 py-3">
            {records.length === 0 ? (
              <ArtifactState message="This ledger artifact contains no audit records." />
            ) : (
              <Panel>
                <LedgerTable records={records} />
              </Panel>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function LedgerTable({ records }: { records: LedgerRecord[] }) {
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-hairline text-left">
          {["seq", "record", "action", "subject", "details", "timestamp", "fingerprint"].map((heading) => (
            <th key={heading} className="px-4 py-2 font-mono text-[9px] font-normal uppercase tracking-wider text-muted">{heading}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {records.map((record, index) => {
          const details = [
            record.artifact_count !== undefined && `${record.artifact_count} artifacts`,
            record.rows !== undefined && `${record.rows} rows`,
            record.entities !== undefined && `${record.entities} entities`,
            record.incidents !== undefined && `${record.incidents} incidents`,
          ].filter(Boolean).join(" · ");
          return (
            <tr key={record.record_id} className="border-b border-hairline/50">
              <td className="px-4 py-2 font-mono text-[10px] tabular-nums text-muted">{String(index + 1).padStart(3, "0")}</td>
              <td className="px-4 py-2 font-mono text-[11px] text-primary">{record.record_id}</td>
              <td className="px-4 py-2 font-mono text-[10px] uppercase tracking-wider text-accent">{record.action || "—"}</td>
              <td className="px-4 py-2 font-mono text-[10px] text-secondary">{record.subject || record.dataset_id || "—"}</td>
              <td className="px-4 py-2 font-mono text-[10px] text-muted">{details || "—"}</td>
              <td className="px-4 py-2 font-mono text-[10px] tabular-nums text-muted">{record.timestamp ? new Date(record.timestamp).toLocaleString() : "—"}</td>
              <td className="max-w-48 truncate px-4 py-2 font-mono text-[10px] tracking-wider text-muted">{record.fingerprint || "—"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ArtifactState({ message }: { message: string }) {
  return <div className="flex h-full items-center justify-center p-8 text-center"><Mono className="text-muted">{message}</Mono></div>;
}
