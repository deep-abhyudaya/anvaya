"use client";

import React, { useCallback, useMemo, useState } from "react";
import {
  AnvayaAPI,
  SubagentExecution,
  SubagentProfile,
  useSubagentProfiles,
  useSubagents,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { Bot, CheckCircle, Loader2, Pause, Play, RotateCcw, Search, Terminal, Users } from "lucide-react";
import { Chip, Dot, Mono } from "@/components/primitives";

const STATUS_TONE: Record<string, "accent" | "success" | "critical" | "warning" | "muted"> = {
  pending: "muted",
  running: "accent",
  completed: "success",
  failed: "critical",
  cancelled: "warning",
  parked: "warning",
};

const PROFILE_TONE: Record<string, string> = {
  success: "text-success border-success/50",
  accent: "text-accent border-accent/50",
  warning: "text-warning border-warning/60",
};

function statusTone(status: string) {
  return STATUS_TONE[status] || "muted";
}

function profileIcon(id: string) {
  if (id === "explore") return Search;
  if (id === "tester") return CheckCircle;
  return Bot;
}

function formatDuration(ms?: number) {
  if (ms === undefined || ms === 0) return "—";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function SubagentPanel({
  parentExecutionId,
  incidentId,
  onOpenChild,
}: {
  parentExecutionId?: string;
  incidentId?: string;
  onOpenChild?: (executionId: string) => void;
}) {
  const { data: profilesData } = useSubagentProfiles();
  const { data: subagentsData, isLoading } = useSubagents(parentExecutionId, 3000);

  const [task, setTask] = useState("");
  const [profileId, setProfileId] = useState("general");
  const [mode, setMode] = useState<"foreground" | "background">("background");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "active" | "done">("all");

  const profiles = useMemo(() => profilesData?.items || [], [profilesData?.items]);
  const all = useMemo(() => (subagentsData?.items || []) as SubagentExecution[], [subagentsData?.items]);

  const filtered = useMemo(() => {
    if (filter === "active") return all.filter((s) => s.status === "pending" || s.status === "running");
    if (filter === "done") return all.filter((s) => ["completed", "failed", "cancelled"].includes(s.status));
    return all;
  }, [all, filter]);

  const activeCount = useMemo(
    () => all.filter((s) => s.status === "pending" || s.status === "running").length,
    [all]
  );

  const spawn = useCallback(async () => {
    if (!parentExecutionId || !task.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await AnvayaAPI.spawnSubagent({
        task: task.trim(),
        profile_id: profileId,
        mode,
        parent_execution_id: parentExecutionId,
        incident_id: incidentId || "",
      });
      setTask("");
    } catch (err: any) {
      setError(err?.message || "Failed to spawn subagent");
    } finally {
      setSubmitting(false);
    }
  }, [parentExecutionId, task, profileId, mode, incidentId]);

  const cancel = useCallback(async (sub: SubagentExecution) => {
    try {
      await AnvayaAPI.cancelSubagent(sub.subagent_id);
    } catch (err: any) {
      setError(err?.message || "Failed to cancel subagent");
    }
  }, []);

  const resume = useCallback(async (sub: SubagentExecution) => {
    try {
      await AnvayaAPI.resumeSubagent(sub.subagent_id, sub.task);
    } catch (err: any) {
      setError(err?.message || "Failed to resume subagent");
    }
  }, []);

  const selectedProfile = profiles.find((p) => p.id === profileId);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-hairline px-3 py-2">
        <div className="flex items-center gap-2">
          <Users className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
          <span className="text-[11px] font-medium text-primary">Subagents</span>
          {activeCount > 0 && (
            <Chip tone="accent">{activeCount} active</Chip>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <FilterPill label="all" active={filter === "all"} onClick={() => setFilter("all")} />
          <FilterPill label="active" active={filter === "active"} onClick={() => setFilter("active")} />
          <FilterPill label="done" active={filter === "done"} onClick={() => setFilter("done")} />
        </div>
      </div>

      <div className="border-b border-hairline p-3">
        <div className="mb-2 flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-muted">
          <Terminal className="h-3 w-3" strokeWidth={1.5} />
          New subagent
        </div>
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          placeholder="Delegate a focused task..."
          className="mb-2 h-16 w-full resize-none rounded border border-hairline bg-canvas-elevated px-2 py-1.5 text-[11px] text-primary outline-none placeholder:text-muted focus:border-accent/60"
        />
        <div className="mb-2 flex items-center gap-2">
          <select
            value={profileId}
            onChange={(e) => setProfileId(e.target.value)}
            className="h-7 rounded border border-hairline bg-canvas-elevated px-2 text-[10px] text-primary outline-none focus:border-accent/60"
          >
            {profiles.map((p: SubagentProfile) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <SegmentedMode value={mode} onChange={setMode} />
          <button
            onClick={spawn}
            disabled={!task.trim() || submitting || !parentExecutionId}
            className={cn(
              "ml-auto flex h-7 items-center gap-1 rounded border px-2 text-[10px] font-medium transition-colors",
              !task.trim() || submitting || !parentExecutionId
                ? "border-hairline bg-canvas-elevated text-muted"
                : "border-accent/50 bg-accent-dim/20 text-accent hover:bg-accent-dim/40"
            )}
          >
            {submitting ? (
              <Loader2 className="h-3 w-3 animate-spin" strokeWidth={1.5} />
            ) : (
              <Play className="h-3 w-3" strokeWidth={1.5} />
            )}
            Spawn
          </button>
        </div>
        {selectedProfile && (
          <div className="text-[9px] leading-relaxed text-muted">
            {selectedProfile.description}
          </div>
        )}
        {error && <div className="mt-2 text-[10px] text-critical">{error}</div>}
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {isLoading && !all.length ? (
          <div className="py-4 text-center text-[10px] text-muted">Loading subagents...</div>
        ) : filtered.length === 0 ? (
          <div className="py-4 text-center text-[10px] text-muted">
            {all.length === 0 ? "No subagents yet" : "No subagents match this filter"}
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((sub) => (
              <SubagentRow
                key={sub.subagent_id}
                sub={sub}
                profiles={profiles}
                onCancel={cancel}
                onResume={resume}
                onOpenChild={onOpenChild}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function FilterPill({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded px-1.5 py-0.5 text-[9px] uppercase tracking-wider transition-colors",
        active
          ? "bg-accent-dim/50 text-accent border border-accent/30"
          : "border border-hairline text-muted hover:border-accent/60"
      )}
    >
      {label}
    </button>
  );
}

function SegmentedMode({
  value,
  onChange,
}: {
  value: "foreground" | "background";
  onChange: (v: "foreground" | "background") => void;
}) {
  return (
    <div className="flex border border-hairline">
      {(["foreground", "background"] as const).map((it) => {
        const active = it === value;
        return (
          <button
            key={it}
            onClick={() => onChange(it)}
            className={cn(
              "px-2 py-1 text-[9px] font-mono uppercase tracking-wider transition-colors",
              active ? "bg-accent-dim text-accent" : "text-muted hover:text-secondary"
            )}
            title={it === "foreground" ? "Blocking until complete" : "Runs in parallel"}
          >
            {it}
          </button>
        );
      })}
    </div>
  );
}

function SubagentRow({
  sub,
  profiles,
  onCancel,
  onResume,
  onOpenChild,
}: {
  sub: SubagentExecution;
  profiles: SubagentProfile[];
  onCancel: (sub: SubagentExecution) => void;
  onResume: (sub: SubagentExecution) => void;
  onOpenChild?: (executionId: string) => void;
}) {
  const profile = profiles.find((p) => p.id === sub.profile_id);
  const Icon = profile ? profileIcon(profile.id) : Bot;
  const accent = profile ? profile.accent : "accent";
  const running = sub.status === "running" || sub.status === "pending";

  return (
    <div
      className={cn(
        "rounded border p-2 text-[10px] transition-colors",
        running ? "border-accent/30 bg-accent-dim/10" : "border-hairline bg-canvas-elevated/60"
      )}
    >
      <div className="mb-1.5 flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon className={cn("h-3.5 w-3.5", PROFILE_TONE[accent]?.split(" ")[0] || "text-accent")} strokeWidth={1.5} />
          <div>
            <div className="text-[11px] font-medium text-primary line-clamp-1">{sub.title}</div>
            <div className="flex items-center gap-1.5 text-[9px] text-muted">
              <Mono tone={statusTone(sub.status)}>
                <Dot tone={statusTone(sub.status)} pulse={running} className="mr-1" />
                {sub.status}
              </Mono>
              <span>/</span>
              <span>{sub.mode}</span>
              <span>/</span>
              <span>{sub.tool_calls_count} tools</span>
              <span>/</span>
              <span>{formatDuration(sub.duration_ms)}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {running && (
            <ActionBtn onClick={() => onCancel(sub)} title="Cancel" tone="warning">
              <Pause className="h-3 w-3" strokeWidth={1.5} />
            </ActionBtn>
          )}
          {(!running || sub.status === "cancelled") && (
            <ActionBtn onClick={() => onResume(sub)} title="Resume" tone="success">
              <RotateCcw className="h-3 w-3" strokeWidth={1.5} />
            </ActionBtn>
          )}
          {sub.child_execution_id && (
            <ActionBtn
              onClick={() => onOpenChild?.(sub.child_execution_id!)}
              title="Open child execution"
              tone="accent"
            >
              <Terminal className="h-3 w-3" strokeWidth={1.5} />
            </ActionBtn>
          )}
        </div>
      </div>
      {sub.result_summary && (
        <div className="mb-1.5 line-clamp-2 text-[10px] text-secondary">{sub.result_summary}</div>
      )}
      {sub.error_message && (
        <div className="mb-1.5 line-clamp-2 text-[10px] text-critical">{sub.error_message}</div>
      )}
      <div className="flex flex-wrap gap-1">
        <Chip tone={statusTone(sub.status)}>{sub.profile_id}</Chip>
        {sub.mode === "background" && <Chip tone="muted">bg</Chip>}
      </div>
    </div>
  );
}

function ActionBtn({
  children,
  onClick,
  title,
  tone = "muted",
}: {
  children: React.ReactNode;
  onClick: () => void;
  title: string;
  tone?: "accent" | "success" | "warning" | "critical" | "muted";
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={cn(
        "flex h-6 w-6 items-center justify-center rounded border transition-colors",
        tone === "accent" && "border-accent/40 text-accent hover:bg-accent-dim/20",
        tone === "success" && "border-success/40 text-success hover:bg-success/10",
        tone === "warning" && "border-warning/40 text-warning hover:bg-warning-dim/20",
        tone === "critical" && "border-critical/40 text-critical hover:bg-critical-dim/10",
        tone === "muted" && "border-hairline text-muted hover:text-primary"
      )}
    >
      {children}
    </button>
  );
}
