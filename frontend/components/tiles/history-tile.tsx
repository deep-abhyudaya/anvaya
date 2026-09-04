"use client";

import React, { useState } from "react";
import { Tile } from "@/components/tiles/tile-shell";
import { useAgent, AgentExecution } from "@/components/agent/agent-context";
import { useAgentExecutions } from "@/lib/api";
import { Dot } from "@/components/primitives";
import { cn, cleanObjective } from "@/lib/utils";
import { Bot, Clock, Play, Search } from "lucide-react";

export default function HistoryTile() {
  const { loadExecution, newConversation, state } = useAgent();
  const [search, setSearch] = useState("");
  const { data } = useAgentExecutions(undefined, 5000);
  const executions = (data?.items || []) as AgentExecution[];

  const filtered = executions.filter((ex) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      cleanObjective(ex.objective).toLowerCase().includes(q) ||
      ex.incident_id?.toLowerCase().includes(q) ||
      ex.execution_id?.toLowerCase().includes(q) ||
      ex.status?.toLowerCase().includes(q)
    );
  });

  return (
    <Tile
      id="history"
      title="History"
      subtitle="Agent conversation log"
    >
      <div className="flex h-full flex-col p-5">
        <div className="mb-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Search className="h-4 w-4 text-muted" strokeWidth={1.5} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search conversations..."
              className="w-64 border-b border-hairline bg-transparent px-1 py-1 text-[13px] text-primary outline-none focus:border-accent"
            />
          </div>
          <button
            onClick={newConversation}
            className="flex items-center gap-1.5 rounded border border-hairline bg-accent-dim px-3 py-1.5 text-[11px] text-accent transition-colors hover:border-accent/60"
          >
            <Bot className="h-3.5 w-3.5" strokeWidth={1.5} />
            New conversation
          </button>
        </div>

        <div className="flex-1 overflow-y-auto rounded border border-hairline bg-canvas-elevated/30">
          {filtered.length === 0 && (
            <div className="flex h-40 items-center justify-center text-[12px] text-muted">
              No conversations found.
            </div>
          )}

          <div className="divide-y divide-hairline">
            {filtered.map((ex) => {
              const tone =
                ex.status === "completed" ? "success" : ex.status === "failed" ? "critical" : "accent";
              const time = ex.started_at
                ? new Date(ex.started_at).toLocaleString([], {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "";

              return (
                <div
                  key={ex.execution_id}
                  className={cn(
                    "group flex items-start justify-between gap-4 p-4 transition-colors hover:bg-canvas-subtle",
                    state.executionId === ex.execution_id && "bg-accent-dim/20"
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Dot tone={tone as any} pulse={ex.status === "running"} />
                      <span className="truncate text-[13px] text-primary">
                        {cleanObjective(ex.objective) || ex.incident_id || ex.execution_id}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-[10px] text-muted">
                      <span className="font-mono">{ex.execution_id}</span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" strokeWidth={1.5} />
                        {time}
                      </span>
                      {ex.incident_id && <span>incident: {ex.incident_id}</span>}
                      {ex.duration_ms !== undefined && (
                        <span>{Math.round(ex.duration_ms)}ms</span>
                      )}
                    </div>
                  </div>

                  <button
                    onClick={() => loadExecution(ex)}
                    className="flex shrink-0 items-center gap-1.5 rounded border border-hairline px-2.5 py-1.5 text-[10px] text-primary transition-colors hover:border-accent/60 hover:text-accent"
                  >
                    <Play className="h-3 w-3" strokeWidth={1.5} />
                    {state.executionId === ex.execution_id ? "Viewing" : "Open"}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Tile>
  );
}
