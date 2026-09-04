"use client";

import React, { useState } from "react";
import {
  ArrowRight,
  ChevronDown,
  ScrollText,
} from "lucide-react";
import { useAgent } from "./agent-context";
import { Mono } from "@/components/primitives";
import { cn } from "@/lib/utils";
import AIReasoning from "@/components/smoothui/ai-reasoning";
import AITaskList from "@/components/smoothui/ai-task-list";

export function LiveReasoningPanel({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-3", className)}>
      <ReasoningCard />
      <PlanList />
      <ObservationList />
      <ReasoningHistory />
    </div>
  );
}

function ReasoningCard() {
  const { state } = useAgent();
  const isStreaming = ["generating", "thinking", "running"].includes(state.modelStatus || "");

  return (
    <AIReasoning isStreaming={isStreaming}>
      <div className="flex items-center gap-2">
        <ScrollText className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
        <Mono tone="accent">Live reasoning</Mono>
      </div>
      <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-secondary">
        {state.reasoning || (isStreaming ? "Generating reasoning..." : "—")}
      </p>
    </AIReasoning>
  );
}

function PlanList() {
  const { state } = useAgent();
  if (!state.plan.length) return null;

  const tasks = state.plan.map((step, i) => ({
    id: `${step.tool}:${i}`,
    label: step.label || step.tool,
    status: planStatus(step.status),
    note: step.result_summary,
  }));

  return <AITaskList tasks={tasks} label="Plan" className="rounded border border-hairline bg-canvas-panel/60 p-3" />;
}

function planStatus(status: string): "pending" | "running" | "done" | "failed" {
  switch (status) {
    case "completed":
    case "done":
      return "done";
    case "running":
      return "running";
    case "failed":
    case "error":
      return "failed";
    default:
      return "pending";
  }
}

function ObservationList() {
  const { state } = useAgent();
  if (!state.observations.length) return null;

  return (
    <div>
      <Mono tone="muted" className="mb-2 block">Observations</Mono>
      <div className="space-y-2">
        {state.observations.map((obs, i) => (
          <ObservationCard key={`${obs.source}:${obs.step_index}:${i}`} observation={obs} />
        ))}
      </div>
    </div>
  );
}

function ObservationCard({
  observation,
}: {
  observation: { summary: string; facts: Record<string, unknown>; source: string; step_index: number };
}) {
  const entries = Object.entries(observation.facts || {});
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <ArrowRight className="h-3 w-3 text-accent" strokeWidth={1.5} />
        <span className="text-[11px] text-primary">{observation.summary}</span>
      </div>
      <div className="mb-1.5 flex items-center gap-2 text-[9px] text-muted">
        <span className="font-mono">{observation.source}</span>
        {observation.step_index >= 0 && <span>/ step {observation.step_index + 1}</span>}
      </div>
      {entries.length > 0 && (
        <div className="grid grid-cols-2 gap-1.5">
          {entries.map(([key, value]) => (
            <div key={key}>
              <Mono tone="muted" className="block truncate text-[8px]">{key}</Mono>
              <pre className="overflow-x-auto text-[9px] text-secondary">
                {typeof value === "object" ? JSON.stringify(value, null, 2) : String(value)}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ReasoningHistory() {
  const { state } = useAgent();
  const [open, setOpen] = useState(false);

  const reasoningEvents = state.events.filter(
    (e) =>
      e.type === "agent.reasoning_completed" ||
      e.type === "agent.message" ||
      e.type === "agent.plan_updated" ||
      e.type === "artifact.thinking" ||
      e.type === "element.thinking"
  );

  if (!state.reasoning && !reasoningEvents.length) return null;

  return (
    <div className="rounded border border-hairline bg-canvas-panel/60 p-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-[10px] text-muted transition-colors hover:text-primary"
      >
        <span className="font-mono uppercase tracking-wider">Reasoning history</span>
        <ChevronDown
          className={cn("h-3 w-3 transition-transform", open && "rotate-180")}
          strokeWidth={1.5}
        />
      </button>
      {open && (
        <div className="mt-2 space-y-2 border-t border-hairline pt-2">
          {state.reasoning && (
            <div className="text-[11px] leading-relaxed text-secondary">
              {state.reasoning}
            </div>
          )}
          {reasoningEvents.slice(-10).map((e) => {
            const p = e.payload || {};
            const text =
              (p.purpose as string) ||
              (p.reason as string) ||
              (p.summary as string) ||
              (p.message as string) ||
              e.label ||
              e.type;
            return (
              <div key={`${e.execution_id}:${e.sequence}`} className="text-[10px] text-muted">
                <Mono tone="accent">{e.type}</Mono>
                <p className="mt-0.5 text-secondary">{text}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
