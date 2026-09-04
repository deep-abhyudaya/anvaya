"use client";

import React, { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth/auth-provider";
import {
  AnvayaAPI,
  useProject,
  useProjectDatasets,
  useProjectGenerations,
  type Dataset,
  type Generation,
} from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { useAgent } from "@/components/agent/agent-context";
import { cn } from "@/lib/utils";
import { Upload, Play, FileText, CheckCircle, AlertCircle, Loader2 } from "lucide-react";

const ARTIFACT_TYPES = [
  "incidents",
  "arbor",
  "impacts",
  "reach",
  "replay",
  "ecosystem",
  "arena",
  "orbits",
  "segments",
  "trophy_wall",
  "ledger",
];

export default function ProjectPage() {
  const params = useParams<{ projectId: string }>();
  const { projectId } = params;
  const { dispatch } = useAnvaya();
  const { attachExecution } = useAgent();
  const { activeOrganization } = useAuth();
  const { data: project, isLoading: projectLoading, refetch } = useProject(projectId);

  useEffect(() => {
    if (projectId) {
      dispatch({ type: "set-active-project", value: projectId });
    }
  }, [projectId, dispatch]);
  const { data: datasetsData, isLoading: datasetsLoading, refetch: refetchDatasets } =
    useProjectDatasets(projectId);
  const { data: generationsData, isLoading: generationsLoading, refetch: refetchGenerations } =
    useProjectGenerations(projectId);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedArtifacts, setSelectedArtifacts] = useState<string[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [generating, setGenerating] = useState(false);

  const datasets: Dataset[] = (datasetsData?.items || []) as Dataset[];
  const generations: Generation[] = (generationsData?.items || []) as Generation[];
  const artifactCounts = (project?.artifact_counts || {}) as Record<string, number>;

  const toggleArtifact = (type: string) => {
    setSelectedArtifacts((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  };

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await AnvayaAPI.createDataset(projectId, file);
      refetchDatasets();
      refetch();
    } catch (err) {
      console.error(err);
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleGenerate = async () => {
    if (selectedArtifacts.length === 0) return;
    setGenerating(true);
    try {
      // One build session for ALL selected artifacts: the backend mints a single
      // execution and runs the builders sequentially under it, so the Agent
      // Panel shows one continuous narration stream across every artifact.
      const data = (await AnvayaAPI.createBuildSession(projectId, {
        prompt: `Generate ${selectedArtifacts.join(", ")}`,
        targets: selectedArtifacts,
        dataset_id: selectedDataset || undefined,
      })) as { execution_id: string };
      setSelectedArtifacts([]);
      refetchGenerations();
      refetch();
      if (data.execution_id) {
        await attachExecution(data.execution_id);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <AppShell
      title={project?.name || "Project"}
      subtitle={activeOrganization?.name || "No organization"}
    >
      <div className="h-full overflow-auto bg-canvas p-6">
        {projectLoading ? (
          <p className="font-mono text-[11px] text-muted">Loading project...</p>
        ) : (
          <>
            <div className="mb-6 rounded border border-hairline bg-canvas-panel p-5">
              <h2 className="font-mono text-sm font-semibold uppercase tracking-widest text-primary">
                {project?.name}
              </h2>
              <p className="mt-1 font-mono text-[11px] text-muted">
                {project?.description || "No description"}
              </p>
              <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
                {ARTIFACT_TYPES.map((type) => (
                  <div
                    key={type}
                    className="rounded border border-hairline bg-canvas-subtle px-3 py-2 text-center"
                  >
                    <p className="font-mono text-[10px] uppercase tracking-wider text-muted">
                      {type.replace(/_/g, " ")}
                    </p>
                    <p className="font-mono text-lg font-semibold text-accent">
                      {artifactCounts[type] || 0}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="mb-6 grid gap-6 lg:grid-cols-2">
              <div className="rounded border border-hairline bg-canvas-panel p-5">
                <h3 className="mb-4 font-mono text-[11px] font-semibold uppercase tracking-widest text-primary">
                  Datasets
                </h3>
                <div className="mb-4">
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleUpload}
                    className="hidden"
                    accept=".csv,.json,.jsonl,.parquet"
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                    className={cn(
                      "flex w-full items-center justify-center gap-2 rounded border border-dashed border-hairline py-4 font-mono text-[11px] uppercase text-muted transition-colors hover:border-accent/40 hover:text-accent",
                      uploading && "opacity-50"
                    )}
                  >
                    {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                    {uploading ? "Uploading..." : "Upload dataset"}
                  </button>
                </div>

                {datasetsLoading ? (
                  <p className="font-mono text-[11px] text-muted">Loading datasets...</p>
                ) : datasets.length === 0 ? (
                  <p className="font-mono text-[11px] text-muted">No datasets yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {datasets.map((d) => (
                      <li
                        key={d.dataset_id}
                        className="flex items-center justify-between rounded border border-hairline bg-canvas-subtle px-3 py-2"
                      >
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-accent" />
                          <span className="font-mono text-[11px] text-primary">{d.filename}</span>
                          <span
                            className={cn(
                              "rounded px-1.5 py-0.5 font-mono text-[9px] uppercase",
                              d.status === "ready"
                                ? "bg-success/10 text-success"
                                : d.status === "error"
                                ? "bg-critical/10 text-critical"
                                : "bg-warning/10 text-warning"
                            )}
                          >
                            {d.status}
                          </span>
                        </div>
                        <span className="font-mono text-[10px] text-muted">{d.size} B</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="rounded border border-hairline bg-canvas-panel p-5">
                <h3 className="mb-4 font-mono text-[11px] font-semibold uppercase tracking-widest text-primary">
                  Generate Artifacts
                </h3>

                <div className="mb-4">
                  <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
                    Base dataset
                  </label>
                  <select
                    value={selectedDataset}
                    onChange={(e) => setSelectedDataset(e.target.value)}
                    className="w-full rounded border border-hairline bg-canvas-subtle px-3 py-2 text-sm text-primary outline-none focus:border-accent"
                  >
                    <option value="">None (global distribution)</option>
                    {datasets.map((d) => (
                      <option key={d.dataset_id} value={d.dataset_id}>
                        {d.filename}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="mb-4 grid grid-cols-2 gap-2">
                  {ARTIFACT_TYPES.map((type) => (
                    <label
                      key={type}
                      className={cn(
                        "flex cursor-pointer items-center gap-2 rounded border px-2 py-1.5 font-mono text-[10px] uppercase transition-colors",
                        selectedArtifacts.includes(type)
                          ? "border-accent/40 bg-accent-dim text-accent"
                          : "border-hairline bg-canvas-subtle text-muted hover:text-primary"
                      )}
                    >
                      <input
                        type="checkbox"
                        className="hidden"
                        checked={selectedArtifacts.includes(type)}
                        onChange={() => toggleArtifact(type)}
                      />
                      {type.replace(/_/g, " ")}
                    </label>
                  ))}
                </div>

                <button
                  onClick={handleGenerate}
                  disabled={generating || selectedArtifacts.length === 0}
                  className={cn(
                    "flex w-full items-center justify-center gap-2 rounded bg-accent py-2 font-mono text-[11px] font-medium uppercase text-black hover:bg-accent/90",
                    (generating || selectedArtifacts.length === 0) && "opacity-50"
                  )}
                >
                  {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  {generating ? "Generating..." : "Generate"}
                </button>
              </div>
            </div>

            <div className="rounded border border-hairline bg-canvas-panel p-5">
              <h3 className="mb-4 font-mono text-[11px] font-semibold uppercase tracking-widest text-primary">
                Generations
              </h3>
              {generationsLoading ? (
                <p className="font-mono text-[11px] text-muted">Loading generations...</p>
              ) : generations.length === 0 ? (
                <p className="font-mono text-[11px] text-muted">No generations yet.</p>
              ) : (
                <ul className="space-y-2">
                  {generations.map((g) => (
                    <li
                      key={g.generation_id}
                      className="flex items-center justify-between rounded border border-hairline bg-canvas-subtle px-3 py-2"
                    >
                      <div className="flex items-center gap-2">
                        {g.status === "completed" ? (
                          <CheckCircle className="h-4 w-4 text-success" />
                        ) : g.status === "error" ? (
                          <AlertCircle className="h-4 w-4 text-critical" />
                        ) : (
                          <Loader2 className="h-4 w-4 animate-spin text-warning" />
                        )}
                        <span className="font-mono text-[11px] text-primary">{g.generation_id}</span>
                        <span className="font-mono text-[10px] text-muted">
                          {JSON.parse(g.requested_artifacts_json || "[]").join(", ")}
                        </span>
                      </div>
                      <span className="font-mono text-[10px] text-muted">
                        {g.created_at ? new Date(g.created_at).toLocaleString() : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
}
