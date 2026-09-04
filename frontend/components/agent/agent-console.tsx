"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  Cpu,
  History,
  LoaderCircle,
  Pin,
  PinOff,
  Play,
  Plus,
  ScrollText,
  Search,
  Shield,
  Sparkles,
  Users,
  XCircle,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useAgent, Incident, AgentExecution, AgentAction, AgentCurrentAction, AgentMode, ModelConfig, CONSOLE_MAX_WIDTH } from "./agent-context";
import { AgentEvent, useAgentProviders, useIncidents, ProviderStatus, AnvayaAPI } from "@/lib/api";
import { useProjectReplay } from "@/app/miss-replay/use-project-replay";
import { Mono, Chip, Dot, Tabs } from "@/components/primitives";
import { cn, cleanObjective } from "@/lib/utils";
import { SubagentPanel } from "./subagent-panel";
import { LiveReasoningPanel } from "./live-reasoning";
import { ProfilePicker } from "./profile-picker";
import { MinimalInputBar } from "./minimal-input-bar";
import { BuildPanel } from "@/components/build/build-panel";
import { AssistantMessage } from "./assistant-message";
import { MarkdownRenderer } from "./markdown-renderer";
import AIReasoning from "@/components/smoothui/ai-reasoning";
import AIToolCall from "@/components/smoothui/ai-tool-call";
import AICitation from "@/components/smoothui/ai-citation";
import AISources from "@/components/smoothui/ai-sources";
import SiriOrb from "@/components/smoothui/siri-orb";
import AIDiff from "@/components/smoothui/ai-diff";
import AIApproval from "@/components/smoothui/ai-approval";
import { type AIState } from "@/components/smoothui/ai-core";
import { AIBranch, AIBranchMessages, AIBranchSelector, AIBranchPrevious, AIBranchNext, AIBranchPage } from "@/components/smoothui/ai-branch";

export function AgentConsoleTrigger({ className }: { className?: string }) {
  const { state, dispatch } = useAgent();
  const { data: incidentsData } = useIncidents(30000);

  const activeIncident = useMemo(() => {
    const items = (incidentsData?.items || []) as Incident[];
    return items.find((i) => i.incident_id === state.incidentId);
  }, [incidentsData, state.incidentId]);

  const orbColors = useMemo(
    () => getOrbColors(state.mode, activeIncident?.severity, state.model),
    [state.mode, activeIncident?.severity, state.model]
  );

  const orbState: AIState = state.executing
    ? "thinking"
    : state.status === "completed"
    ? "done"
    : state.status === "failed"
    ? "error"
    : "idle";

  return (
    <button
      type="button"
      onClick={() => dispatch({ type: "toggle" })}
      className={cn(
        "group flex h-8 items-center gap-1.5 rounded border border-hairline bg-canvas-elevated/60 px-2 text-secondary transition-colors hover:border-accent/60 hover:text-accent",
        state.open && "border-accent/60 text-accent",
        className
      )}
      title={state.open ? "Close agent" : "Open agent"}
      aria-label={state.open ? "Close agent" : "Open agent"}
      aria-pressed={state.open}
    >
      <SiriOrb size="20px" state={orbState} colors={orbColors} />
      <span className="text-[11px] font-medium">AI</span>
    </button>
  );
}

export function AgentConsole() {
  const {
    state,
    dispatch,
    start,
    chatStream,
    sendFollowUp,
    cancelExecution,
    seed,
    loadExecution,
    newConversation,
  } = useAgent();
  const [input, setInput] = useState(state.objective);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const [activeTab, setActiveTab] = useState<"console" | "subagents">("console");
  const [chatImages, setChatImages] = useState<string[]>([]);
  const [pending, setPending] = useState<{
    objective: string;
    incidentId?: string;
    executionId?: string;
    targets: string[];
    kind: "delete" | "overwrite";
    isContinue: boolean;
  } | null>(null);

  useEffect(() => {
    setInput(state.objective);
  }, [state.objective]);

  useEffect(() => {
    const clamp = () => {
      const max = Math.min(CONSOLE_MAX_WIDTH, window.innerWidth - 16);
      if (state.width > max) dispatch({ type: "setWidth", value: max });
    };
    clamp();
    window.addEventListener("resize", clamp);
    return () => window.removeEventListener("resize", clamp);
  }, [state.width, dispatch]);

  useEffect(() => {
    if (!scrollRef.current || userScrolledUp) return;
    const el = scrollRef.current;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (nearBottom) {
      el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
    }
  }, [state.events, state.streamingMessage, userScrolledUp]);

  const prevModeRef = useRef<AgentMode | undefined>(undefined);
  useEffect(() => {
    if (
      prevModeRef.current !== undefined &&
      prevModeRef.current !== state.mode &&
      state.events.length > 0
    ) {
      const now = Date.now();
      dispatch({
        type: "appendEvents",
        value: [
          {
            execution_id: state.executionId || "panel",
            sequence: -now,
            type: "mode.switched",
            timestamp: new Date().toISOString(),
            payload: { mode: state.mode },
          } as AgentEvent,
        ],
      });
    }
    prevModeRef.current = state.mode;
  }, [state.mode, state.events.length, state.executionId, dispatch]);

  const onScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setUserScrolledUp(!nearBottom);
  };

  const runTavily = async (indicator: string) => {
    const started: AgentEvent = {
      execution_id: state.executionId || "tavily",
      sequence: 0,
      type: "tool.started",
      timestamp: new Date().toISOString(),
      tool_name: "threat_intelligence_lookup",
      provider: "tavily",
      label: "threat_intelligence_lookup",
      payload: { inputs: { indicator }, provider: "tavily" },
    };
    dispatch({ type: "appendEvents", value: [started] });

    try {
      const result = await AnvayaAPI.tavilyLookup(indicator, undefined, state.incidentId || undefined);
      const completed: AgentEvent = {
        execution_id: started.execution_id,
        sequence: 1,
        type: "tool.completed",
        timestamp: new Date().toISOString(),
        tool_name: "threat_intelligence_lookup",
        provider: result.provider || "tavily",
        label: "threat_intelligence_lookup",
        payload: {
          ...result,
          inputs: { indicator },
          duration_ms: 0,
          output_summary: result.source === "tavily"
            ? `Tavily returned ${(result.records || []).length} record(s) for ${indicator}`
            : `Local fixture for ${indicator}`,
        },
      };
      dispatch({ type: "appendEvents", value: [completed] });
    } catch (err: any) {
      const failed: AgentEvent = {
        execution_id: started.execution_id,
        sequence: 1,
        type: "tool.failed",
        timestamp: new Date().toISOString(),
        tool_name: "threat_intelligence_lookup",
        provider: "tavily",
        label: "threat_intelligence_lookup",
        error_message: err instanceof Error ? err.message : "Tavily lookup failed",
        payload: { inputs: { indicator } },
      };
      dispatch({ type: "appendEvents", value: [failed] });
    }
    clearInputAfterSend();
  };

  const run = async () => {
    const message = input.trim() || (state.contextText ? "Investigate with context." : "");
    if (!message) return;

    const contextSuffix = state.contextText ? `\n\nContext: ${state.contextText}` : "";
    const composed = message + contextSuffix;

    if (state.mode === "agentic" && state.executing) {
      const ok = await sendFollowUp(composed);
      if (ok) clearInputAfterSend();
      return;
    }

    const hasIncidentHint = /\bINC-[A-Z0-9\-]+\b/i.test(message);

    const tavilyMatch = message.match(/^\s*(?:tavily|lookup|look up|search)\s+(.+)$/i);
    if (tavilyMatch) {
      await runTavily(tavilyMatch[1].trim());
      return;
    }

    const artifactActionPattern =
      /\b(generate|generating|regenerate|regen|re-generate|build|create|run|refresh|make|delete|remove|clear|wipe|update|produce)\b/i;
    const artifactTypePattern =
      /\b(risk orbit|risk orbits|orbit|orbits|reach board|reachability|reach|network segment|segment|segments|nerve arena|arena|threat ecosystem|ecosystem|trophy wall|trophy|trophies|miss-replay|miss replay|replay|threat arbor|arbor|tree|impact gallery|impact|impacts|incident|incidents|control ledger|ledger|all|artifact|artifacts)\b/i;
    const artifactTypePatternAll = new RegExp(artifactTypePattern.source, "gi");
    const isArtifactCommand =
      artifactActionPattern.test(message) && artifactTypePattern.test(message);

    const deletePattern = /\b(delete|remove|clear|wipe|drop|purge|erase)\b/i;
    const overwritePattern = /\b(overwrite|replace|regenerate|regen|re-generate|update)\b/i;

    const continueId =
      state.executionId && !state.executing ? state.executionId : undefined;

    let ok = false;
    if (isArtifactCommand) {
      if (deletePattern.test(message) || overwritePattern.test(message)) {
        const matches = Array.from(
          new Set(Array.from(message.matchAll(artifactTypePatternAll), (m) => m[0]))
        );
        setPending({
          objective: composed,
          incidentId: state.incidentId || undefined,
          executionId: continueId,
          targets: matches.length ? matches : ["artifacts"],
          kind: deletePattern.test(message) ? "delete" : "overwrite",
          isContinue: Boolean(continueId),
        });
        return;
      }

      ok = await start(composed, "", continueId);
    } else if (state.mode === "chat" || (!state.incidentId && !hasIncidentHint)) {
      ok = await chatStream(message, chatImages, state.contextText, continueId);
    } else {
      ok = await start(composed, state.incidentId || undefined, continueId);
    }

    if (ok) {
      setChatImages([]);
      clearInputAfterSend();
    }
  };

  const clearInputAfterSend = () => {
    setInput("");
    setChatImages([]);
    dispatch({ type: "setObjective", value: "" });
    dispatch({ type: "setContextText", value: "" });
  };

  const handleImageUpload = async (files: FileList | null) => {
    if (!files) return;
    const encoded: string[] = [];
    for (const file of Array.from(files).slice(0, 4)) {
      const buffer = await file.arrayBuffer();
      const base64 = btoa(String.fromCharCode(...new Uint8Array(buffer)));
      encoded.push(`data:${file.type || "image/png"};base64,${base64}`);
    }
    setChatImages((prev) => [...prev, ...encoded].slice(0, 4));
  };

  const openChildExecution = async (executionId: string) => {
    try {
      const execution = (await AnvayaAPI.agentExecution(executionId)) as AgentExecution;
      if (execution) {
        await loadExecution(execution);
        setActiveTab("console");
      }
    } catch {
    }
  };

  const completed = state.status === "completed";
  const failed = state.status === "failed";
  const running = state.executing;

  if (!state.open) {
    return null;
  }

  const startResize = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = state.width;

    const onMove = (ev: MouseEvent) => {
      const delta = startX - ev.clientX;
      const next = startWidth + delta;
      if (next < 140) {
        dispatch({ type: "setOpen", value: false });
        dispatch({ type: "setWidth", value: 400 });
      } else {
        dispatch({ type: "setWidth", value: next });
      }
    };

    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  return (
    <aside
      style={{ width: state.width }}
      className="fixed right-0 top-14 z-50 h-[calc(100vh-3.5rem)] max-w-[calc(100vw-1rem)] border-l border-hairline bg-canvas-elevated/95 shadow-2xl backdrop-blur-md flex flex-col"
      aria-label="Agent console"
    >
      <div
        onMouseDown={startResize}
        className="absolute left-0 top-0 z-10 h-full w-2 -translate-x-1/2 cursor-col-resize transition-colors hover:bg-accent/20"
        aria-label="Resize agent console"
      />
      {}
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-hairline px-4">
        <div className="flex items-center gap-2.5">
          <AgentOrbButton />
          <div className="flex items-baseline gap-1.5">
            <span className="text-[11px] font-medium text-primary">Anvaya AI</span>
            <span className="text-[10px] text-muted">/</span>
            <span className="text-[10px] text-secondary/60">
              {state.mode === "chat" ? "Ask" : "Agent"}
            </span>
          </div>
        </div>
      </div>

      {}
      <ConversationBar
        executions={state.executions.filter((e) => !state.closedExecutionIds.includes(e.execution_id))}
        active={state.executionId}
        onSelect={loadExecution}
        onNew={newConversation}
        dispatch={dispatch}
      />

      {}
      <div className="flex items-center border-b border-hairline px-4 py-1.5">
        <Tabs
          items={["console", "subagents"]}
          value={activeTab}
          onChange={(v) => setActiveTab(v as any)}
        />
      </div>

      {activeTab === "console" ? (
        <>
          {}
          {state.mode === "agentic" && (
            <div className="flex items-center gap-2 border-b border-hairline px-4 py-2">
              {state.build?.target ? (
                <>
                  <Mono tone="muted">building</Mono>
                  <Mono tone="accent">{state.build.target}</Mono>
                </>
              ) : state.incidentId ? (
                <>
                  <Mono tone="muted">incident</Mono>
                  <Mono tone="accent">{state.incidentId}</Mono>
                </>
              ) : state.projectId ? (
                <>
                  <Mono tone="muted">project</Mono>
                  <Mono tone="accent">{state.projectId}</Mono>
                </>
              ) : (
                <>
                  <Mono tone="muted">context</Mono>
                  <Mono tone="muted">auto-detect from page</Mono>
                </>
              )}
            </div>
          )}

          {}
          <div ref={scrollRef} onScroll={onScroll} className="relative flex-1 overflow-y-auto space-y-3">
            {state.executionId && state.events.some((e) => e.type === "generation.started") && (
              <BuildPanel executionId={state.executionId} />
            )}
            <div className="space-y-3 p-4">
            {pending && (
              <PendingActionGate
                pending={pending}
                onApprove={async () => {
                  const { objective, incidentId, executionId, isContinue } = pending;
                  setPending(null);
                  const ok = isContinue
                    ? await start(objective, "", executionId)
                    : await start(objective, incidentId || "", executionId);
                  if (ok) {
                    setChatImages([]);
                    clearInputAfterSend();
                  }
                }}
                onReject={() => {
                  setPending(null);
                }}
              />
            )}
            {state.mode === "agentic" && (state.executing || state.events.length > 0) && (
              <LiveReasoningPanel />
            )}
            {state.mode === "agentic" && state.projectId && (
              <ReplayBranchPanel projectId={state.projectId} />
            )}
            {state.events.length === 0 && !state.executing && (
              <div className="text-center text-[11px] text-muted">
                {state.mode === "chat"
                  ? "No messages yet. Ask a question or attach an image."
                  : "No active execution. Enter an objective and run, or seed a demo."}
              </div>
            )}
            {state.events.length === 0 && state.executing && !state.streamingMessage && (
              <div className="flex flex-col items-center gap-2 py-6 text-muted">
                <LoaderCircle className="h-4 w-4 animate-spin text-accent" strokeWidth={1.5} />
                <Mono tone="muted">Starting agent...</Mono>
              </div>
            )}
            {state.events.length > 0 && (
              <TraceTimeline
                key={state.executionId || "none"}
                events={state.events}
                executionId={state.executionId}
                status={state.status}
                executing={state.executing}
                modelStatus={state.modelStatus}
                currentAction={state.currentAction}
              />
            )}
            {state.streamingMessage && (
              <ChatAssistantCard
                isStreaming
                event={{
                  execution_id: state.executionId || "",
                  sequence: 0,
                  type: "chat.assistant",
                  timestamp: new Date().toISOString(),
                  payload: { message: state.streamingMessage, model: state.streamingMessageModel },
                }}
              />
            )}
            {userScrolledUp && (
              <button
                onClick={() => {
                  setUserScrolledUp(false);
                  if (scrollRef.current) {
                    scrollRef.current.scrollTo({
                      top: scrollRef.current.scrollHeight,
                      behavior: "smooth",
                    });
                  }
                }}
                className="absolute bottom-6 right-4 z-10 rounded border border-hairline bg-canvas-panel px-2 py-1 text-[10px] text-accent shadow-lg transition-colors hover:border-accent/60"
              >
                Jump to latest
              </button>
            )}
            </div>
          </div>

          {}
          {state.error && (
            <div className="border-t border-hairline px-4 py-2">
              <div className="flex items-center gap-2 text-[10px] text-critical">
                <CircleAlert className="h-3.5 w-3.5" strokeWidth={1.5} />
                {state.error}
              </div>
            </div>
          )}

          {}
          <div className="shrink-0 border-t border-hairline p-3 space-y-2">
            {state.contextText && (
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1.5 rounded border border-accent/30 bg-accent-dim/10 px-2 py-1 text-[10px] text-accent">
                  <span className="max-w-[200px] truncate" title={state.contextText}>
                    Context: {state.contextText.length > 80 ? `${state.contextText.slice(0, 80)}…` : state.contextText}
                  </span>
                  <button
                    onClick={() => dispatch({ type: "setContextText", value: "" })}
                    className="rounded p-0.5 text-accent hover:bg-accent/10"
                    aria-label="Clear context"
                    title="Clear context"
                  >
                    <XCircle className="h-3 w-3" strokeWidth={1.5} />
                  </button>
                </div>
              </div>
            )}
            <MinimalInputBar
              value={input}
              onChange={setInput}
              onSubmit={run}
              onImageSelect={handleImageUpload}
              onCancel={state.mode === "agentic" ? cancelExecution : undefined}
              images={chatImages}
              onRemoveImage={(i) => setChatImages((prev) => prev.filter((_, idx) => idx !== i))}
              running={running}
              disabled={state.executing && state.mode === "chat"}
            />

            {}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
              <div className="flex flex-wrap items-center gap-2">
                {state.mode === "agentic" && <ProfilePicker />}
                {state.mode === "agentic" && <IncidentSelector />}
              </div>
              {state.mode === "agentic" && (
                <button
                  onClick={async () => {
                    const id = await seed();
                    if (id) setInput(`Investigate ${id}`);
                  }}
                  disabled={state.executing}
                  className="rounded border border-hairline px-2 py-1.5 text-[10px] text-muted transition-colors hover:border-warning/60 hover:text-warning disabled:opacity-40"
                >
                  seed demo
                </button>
              )}
            </div>
          </div>
        </>
      ) : (
        <SubagentPanel
          parentExecutionId={state.executionId}
          incidentId={state.incidentId}
          onOpenChild={openChildExecution}
        />
      )}
    </aside>
  );
}

const RISK_GRADIENT = "var(--color-risk-gradient)";

function incidentFactorScore(inc: Incident, factor: string): number {
  switch (factor) {
    case "severity":
      return inc.severity === "high" ? 0.95 : inc.severity === "medium" ? 0.6 : 0.3;
    case "status":
      return inc.status === "detected"
        ? 0.9
        : inc.status === "analyzed"
          ? 0.75
          : inc.status === "simulated"
            ? 0.6
            : inc.status === "explained"
              ? 0.5
              : inc.status === "sealed"
                ? 0.15
                : 0.5;
    case "blast":
      return inc.attack_family === "lateral_movement"
        ? 0.85
        : inc.attack_family === "data_exfiltration"
          ? 0.9
          : inc.attack_family === "privilege_escalation"
            ? 0.7
            : inc.attack_family === "persistence"
              ? 0.55
              : inc.attack_family === "credential_abuse"
                ? 0.75
                : 0.5;
    case "self-corr":
      return inc.self_correction_status === "caught"
        ? 0.35
        : inc.self_correction_status === "missed"
          ? 0.95
          : inc.self_correction_status === "watching"
            ? 0.55
            : 0.6;
    default:
      return 0.5;
  }
}

function IncidentRiskSlider({ incident }: { incident: Incident }) {
  const factors = [
    { id: "severity", label: "Severity" },
    { id: "status", label: "Status" },
    { id: "blast", label: "Blast" },
    { id: "self-corr", label: "Self-corr" },
  ];
  const [selectedFactor, setSelectedFactor] = useState("severity");
  const score = incidentFactorScore(incident, selectedFactor);
  const pct = Math.round(score * 100);

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between text-[9px] uppercase tracking-wider text-muted">
        <span>Risk</span>
        <span className="normal-case tracking-normal">
          {factors.find((f) => f.id === selectedFactor)?.label} impact
        </span>
      </div>

      <div className="text-center text-[10px] font-medium text-primary">
        {incident.incident_id}
      </div>

      <div className="relative h-1.5 w-full rounded-full" style={{ background: RISK_GRADIENT }}>
        <div
          className="absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full border border-black/30 bg-white shadow transition-all duration-300"
          style={{ left: `calc(${pct}% - 5px)` }}
        />
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {factors.map((f) => {
          const active = f.id === selectedFactor;
          const fit = incidentFactorScore(incident, f.id);
          return (
            <button
              key={f.id}
              onClick={() => setSelectedFactor(f.id)}
              className={cn(
                "rounded border px-1.5 py-1 text-left transition-colors",
                active
                  ? "border-critical/50 bg-critical/10"
                  : "border-hairline bg-canvas-subtle/60 hover:border-critical/40"
              )}
            >
              <div className="truncate text-[8px] uppercase tracking-wider text-muted">
                {f.label}
              </div>
              <div className="font-mono text-[9px] text-primary">{Math.round(fit * 100)}%</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function IncidentMark({ severity }: { severity: string }) {
  const color =
    severity === "high"
      ? "bg-critical/20 text-critical border-critical/40"
      : severity === "medium"
        ? "bg-warning/20 text-warning border-warning/40"
        : severity === "low"
          ? "bg-success/20 text-success border-success/40"
          : "bg-canvas-subtle text-muted border-hairline";
  return (
    <span
      className={cn(
        "flex h-6 w-6 shrink-0 items-center justify-center rounded border text-[10px] font-semibold uppercase",
        color
      )}
    >
      {severity?.slice(0, 1) || "?"}
    </span>
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

function IncidentSelector() {
  const { state, dispatch } = useAgent();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [hovered, setHovered] = useState<Incident | null>(null);
  const [pinned, setPinned] = useState<string[]>([]);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("anvaya.agent.pinned-incidents");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) setPinned(parsed);
      } catch {}
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("anvaya.agent.pinned-incidents", JSON.stringify(pinned));
  }, [pinned]);

  const togglePin = (incidentId: string) => {
    setPinned((prev) =>
      prev.includes(incidentId) ? prev.filter((id) => id !== incidentId) : [...prev, incidentId]
    );
  };

  const { data } = useIncidents(30000);
  const incidents = useMemo(() => (data?.items || []) as Incident[], [data]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setHovered(null);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setHovered(null);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return incidents.filter((inc) => {
      const matchesSearch =
        !q ||
        inc.incident_id.toLowerCase().includes(q) ||
        inc.title.toLowerCase().includes(q) ||
        (inc.attack_family || "").toLowerCase().includes(q) ||
        (inc.host || "").toLowerCase().includes(q);

      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "active" && inc.status !== "sealed") ||
        (statusFilter === "sealed" && inc.status === "sealed") ||
        inc.status === statusFilter;

      const matchesSeverity =
        severityFilter === "all" || inc.severity === severityFilter;

      return matchesSearch && matchesStatus && matchesSeverity;
    });
  }, [incidents, search, statusFilter, severityFilter]);

  const [pinnedItems, otherItems] = useMemo(() => {
    const pinnedSet = new Set(pinned);
    const p: Incident[] = [];
    const o: Incident[] = [];
    for (const inc of filtered) {
      if (pinnedSet.has(inc.incident_id)) p.push(inc);
      else o.push(inc);
    }
    return [p, o];
  }, [filtered, pinned]);

  const active = state.incidentId;
  const detail = hovered;

  const selectIncident = (inc: Incident) => {
    dispatch({ type: "setIncidentId", value: inc.incident_id });
    dispatch({ type: "setObjective", value: `Investigate ${inc.incident_id}` });
    setOpen(false);
    setHovered(null);
  };

  const renderRow = (inc: Incident) => {
    const isCurrent = inc.incident_id === active;
    const isPinned = pinned.includes(inc.incident_id);
    return (
      <button
        key={inc.incident_id}
        onClick={() => selectIncident(inc)}
        onMouseEnter={() => setHovered(inc)}
        onFocus={() => setHovered(inc)}
        className={cn(
          "flex w-full items-center gap-2.5 rounded px-2 py-2 text-left transition-colors",
          isCurrent ? "bg-accent-dim/40" : "hover:bg-canvas-subtle"
        )}
      >
        <IncidentMark severity={inc.severity} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-[11px] font-medium text-primary">
              {inc.incident_id}
            </span>
            {isPinned && <Pin className="h-2.5 w-2.5 shrink-0 text-accent" strokeWidth={2} />}
          </div>
          <div className="truncate text-[9px] text-muted">{inc.title}</div>
        </div>
        <Dot tone={severityTone(inc.severity)} pulse={false} />
      </button>
    );
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded border border-hairline px-2 py-1.5 text-[10px] text-primary transition-colors hover:border-accent/60"
        aria-label="Select incident"
      >
        <Search className="h-3 w-3 text-muted" strokeWidth={1.5} />
        <span className="max-w-[80px] truncate uppercase tracking-wider">
          {active || "incident"}
        </span>
        <ChevronDown className="h-3 w-3 text-muted" strokeWidth={1.5} />
      </button>

      {open && (
        <div
          className="absolute bottom-full right-0 z-50 mb-1 flex overflow-hidden rounded border border-hairline bg-canvas-panel shadow-xl"
          onMouseLeave={() => setHovered(null)}
        >
          {}
          {detail && (
            <div className="w-60 shrink-0 border-r border-hairline bg-canvas-subtle/40 p-3">
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <IncidentMark severity={detail.severity} />
                  <div>
                    <div className="text-[11px] font-medium text-primary">
                      {detail.incident_id}
                    </div>
                    <div className="text-[9px] uppercase tracking-wider text-muted">
                      {detail.attack_family || detail.status}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => togglePin(detail.incident_id)}
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded transition-colors",
                    pinned.includes(detail.incident_id)
                      ? "text-accent"
                      : "text-muted hover:text-primary"
                  )}
                  aria-label={
                    pinned.includes(detail.incident_id) ? "Unpin incident" : "Pin incident"
                  }
                  title={pinned.includes(detail.incident_id) ? "Unpin" : "Pin"}
                >
                  {pinned.includes(detail.incident_id) ? (
                    <Pin className="h-3.5 w-3.5" strokeWidth={1.5} />
                  ) : (
                    <PinOff className="h-3.5 w-3.5" strokeWidth={1.5} />
                  )}
                </button>
              </div>

              <div className="mb-2 flex items-center gap-2 text-[9px] text-muted">
                <Chip tone={severityTone(detail.severity)}>{detail.severity}</Chip>
                <span>{detail.status}</span>
                {detail.host && <span>, {detail.host}</span>}
              </div>

              <p className="mb-3 line-clamp-3 text-[10px] leading-relaxed text-secondary">
                {detail.description || detail.title}
              </p>

              <IncidentRiskSlider incident={detail} />

              <div className="mt-3 text-[9px] text-muted">
                self-correction:{" "}
                <span className="text-secondary">{detail.self_correction_status}</span>
              </div>
            </div>
          )}

          <div className="w-72 p-2">
            <div className="mb-2 flex items-center gap-1.5 rounded border border-hairline px-2 py-1.5">
              <Search className="h-3 w-3 text-muted" strokeWidth={1.5} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search all incidents"
                className="w-full bg-transparent text-[11px] text-primary outline-none"
              />
            </div>

            <div className="mb-2 flex items-center gap-1.5">
              <FilterPill
                label="all"
                active={statusFilter === "all"}
                onClick={() => setStatusFilter("all")}
              />
              <FilterPill
                label="active"
                active={statusFilter === "active"}
                onClick={() => setStatusFilter("active")}
              />
              <FilterPill
                label="sealed"
                active={statusFilter === "sealed"}
                onClick={() => setStatusFilter("sealed")}
              />
            </div>

            <div className="mb-2 flex items-center gap-1.5">
              <FilterPill
                label="high"
                active={severityFilter === "high"}
                onClick={() => setSeverityFilter("high")}
              />
              <FilterPill
                label="medium"
                active={severityFilter === "medium"}
                onClick={() => setSeverityFilter("medium")}
              />
              <FilterPill
                label="low"
                active={severityFilter === "low"}
                onClick={() => setSeverityFilter("low")}
              />
              <FilterPill
                label="all"
                active={severityFilter === "all"}
                onClick={() => setSeverityFilter("all")}
              />
            </div>

            <div className="max-h-80 space-y-0.5 overflow-y-auto pr-0.5">
              <button
                onClick={() => {
                  dispatch({ type: "setIncidentId", value: "" });
                  dispatch({ type: "setObjective", value: "" });
                  setOpen(false);
                  setHovered(null);
                }}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded px-2 py-2 text-left transition-colors",
                  !active ? "bg-accent-dim/40" : "hover:bg-canvas-subtle"
                )}
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded border border-hairline bg-canvas-subtle text-[10px] text-muted">
                  A
                </span>
                <div className="min-w-0 flex-1">
                  <span className="text-[11px] font-medium text-primary">
                    Auto-detect from page
                  </span>
                  <div className="truncate text-[9px] text-muted">
                    Use the incident on the current page
                  </div>
                </div>
              </button>

              {pinnedItems.length > 0 && (
                <>
                  <div className="px-2 pb-1 pt-2 text-[9px] uppercase tracking-wider text-accent">
                    Pinned
                  </div>
                  {pinnedItems.map(renderRow)}
                </>
              )}
              {otherItems.length > 0 && (
                <>
                  <div className="px-2 pb-1 pt-2 text-[9px] uppercase tracking-wider text-muted">
                    All incidents
                  </div>
                  {otherItems.map(renderRow)}
                </>
              )}

              {filtered.length === 0 && (
                <div className="py-4 text-center text-[10px] text-muted">No incidents match</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}



function getOrbColors(
  mode: "agentic" | "chat",
  severity: string | undefined,
  model: ModelConfig | null
) {
  const chat = "#3B82F6";
  const agentic = "#F97316";
  const high = "#DC2626";
  const medium = "#F59E0B";
  const low = "#22C55E";
  const modelAvailable = "#0EA5E9";
  const modelConfigured = "#F59E0B";
  const modelUnavailable = "#6B7280";

  const modeColor = mode === "chat" ? chat : agentic;
  const severityColor =
    severity === "high"
      ? high
      : severity === "medium"
      ? medium
      : severity === "low"
      ? low
      : modeColor;
  const modelColor =
    model?.availability === "available"
      ? modelAvailable
      : model?.availability === "configured"
      ? modelConfigured
      : model?.availability === "unavailable"
      ? modelUnavailable
      : modeColor;

  const shade = (color: string, weight: number, mix: "white" | "black") =>
    `color-mix(in srgb, ${color} ${weight}%, ${mix})`;

  return {
    bg: "var(--color-surface)",
    c1: shade(modeColor, 75, "white"),
    c2: modeColor,
    c3: severityColor,
    c4: modelColor,
  };
}

function AgentOrbButton() {
  const [open, setOpen] = useState(false);
  const [pulse, setPulse] = useState<AIState | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const skipPulse = useRef(true);
  const pulseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { data: providersData } = useAgentProviders();
  const { data: incidentsData } = useIncidents(30000);
  const { state: agentState } = useAgent();

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  // Pulse the orb whenever the user toggles ask mode, changes model, or picks a different incident.
  useEffect(() => {
    if (skipPulse.current) {
      skipPulse.current = false;
      return;
    }
    setPulse("listening");
    if (pulseTimer.current) clearTimeout(pulseTimer.current);
    pulseTimer.current = setTimeout(() => setPulse(null), 650);
    return () => {
      if (pulseTimer.current) clearTimeout(pulseTimer.current);
    };
  }, [agentState.mode, agentState.model?.id, agentState.incidentId]);

  const providers = providersData?.items || [];
  const activeCount = providers.filter(
    (p: ProviderStatus) => p.availability === "available" || p.availability === "configured"
  ).length;

  const activeIncident = useMemo(() => {
    const items = (incidentsData?.items || []) as Incident[];
    return items.find((i) => i.incident_id === agentState.incidentId);
  }, [incidentsData, agentState.incidentId]);
  const severity = activeIncident?.severity;

  const orbColors = useMemo(
    () => getOrbColors(agentState.mode, severity, agentState.model),
    [agentState.mode, severity, agentState.model]
  );

  const baseOrbState: AIState = agentState.executing
    ? "thinking"
    : agentState.status === "completed"
    ? "done"
    : agentState.status === "failed"
    ? "error"
    : "idle";

  const orbState = pulse ?? baseOrbState;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex h-7 w-7 items-center justify-center rounded border border-hairline text-secondary transition-colors hover:border-accent/60 hover:text-accent"
        aria-label="Provider status"
        title="Provider status"
      >
        <SiriOrb size="20px" state={orbState} colors={orbColors} />
      </button>
      {activeCount > 0 && (
        <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-accent" />
      )}

      {open && <ProviderStatusPanel providers={providers} onClose={() => setOpen(false)} />}
    </div>
  );
}

function ProviderStatusPanel({
  providers,
  onClose,
}: {
  providers: ProviderStatus[];
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute left-0 top-9 z-50 w-72 rounded border border-hairline bg-canvas-panel p-2 shadow-xl"
    >
      <div className="mb-2 flex items-center justify-between border-b border-hairline pb-1.5">
        <span className="text-[10px] font-medium uppercase tracking-wider text-primary">
          Provider status
        </span>
        <button onClick={onClose} className="text-[10px] text-muted hover:text-primary">
          close
        </button>
      </div>
      <div className="max-h-72 space-y-1 overflow-y-auto">
        {providers.length === 0 && (
          <div className="py-2 text-center text-[10px] text-muted">No provider status</div>
        )}
        {providers.map((p: ProviderStatus) => {
          const tone =
            p.availability === "available"
              ? "success"
              : p.availability === "configured"
              ? "accent"
              : p.availability === "unavailable"
              ? "warning"
              : "muted";
          const Icon = p.kind === "model" ? Cpu : p.provider === "tavily" ? Search : Zap;
          return (
            <div
              key={`${p.provider}-${p.name}`}
              className="flex items-start gap-2 rounded p-1.5 transition-colors hover:bg-canvas-subtle"
            >
              <Icon className="mt-0.5 h-3.5 w-3.5 text-muted" strokeWidth={1.5} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] font-medium text-primary">{p.name}</span>
                  <Mono tone={tone} className="shrink-0 text-[9px]">
                    {p.availability}
                  </Mono>
                </div>
                <div className="text-[9px] text-muted">
                  {p.configured ? (p.healthy ? "configured, healthy" : "configured") : "not configured"}
                </div>
                {p.fallback_message && (
                  <div className="mt-0.5 text-[9px] text-warning">{p.fallback_message}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function severityTone(severity: string): "critical" | "warning" | "success" | "muted" {
  switch (severity) {
    case "high":
      return "critical";
    case "medium":
      return "warning";
    case "low":
      return "success";
    default:
      return "muted";
  }
}

function ConversationBar({
  executions,
  active,
  onSelect,
  onNew,
  dispatch,
}: {
  executions: AgentExecution[];
  active: string | undefined;
  onSelect: (execution: AgentExecution) => void;
  onNew: () => void;
  dispatch: React.Dispatch<AgentAction>;
}) {
  const [menu, setMenu] = useState<{ x: number; y: number; ex: AgentExecution } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => {
      if (e.button !== 0) return;
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenu(null);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(null);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  const openContextMenu = (e: React.MouseEvent, ex: AgentExecution) => {
    e.preventDefault();
    e.stopPropagation();
    setMenu({ x: e.clientX, y: e.clientY, ex });
  };

  const onTabMouseDown = (e: React.MouseEvent, ex: AgentExecution) => {
    if (e.button === 2) {
      e.preventDefault();
      e.stopPropagation();
      setMenu({ x: e.clientX, y: e.clientY, ex });
    }
  };

  return (
    <div className="shrink-0 flex h-9 items-center gap-2 border-b border-hairline px-2 py-1">
      <button
        onClick={onNew}
        className="flex shrink-0 items-center gap-1 rounded border border-hairline px-2 py-1 text-[9px] text-primary transition-colors hover:border-accent/60 hover:text-accent"
        aria-label="New conversation"
      >
        <Plus className="h-3 w-3" strokeWidth={1.5} />
        New
      </button>

      <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        {executions.length === 0 && (
          <span className="shrink-0 px-1 text-[9px] text-muted">No conversations</span>
        )}

        {executions.map((ex) => {
          const isActive = ex.execution_id === active;
          const tone =
            ex.status === "completed" ? "success" : ex.status === "failed" ? "critical" : "accent";
          const label = cleanObjective(ex.objective) || ex.incident_id || ex.execution_id;
          return (
            <button
              key={ex.execution_id}
              onClick={() => onSelect(ex)}
              onMouseDown={(e) => onTabMouseDown(e, ex)}
              onContextMenu={(e) => openContextMenu(e, ex)}
              title={label}
              className={cn(
                "flex shrink-0 max-w-[140px] items-center gap-1.5 rounded border px-2 py-1 text-[9px] transition-colors",
                isActive
                  ? "border-accent/40 bg-accent-dim/40 text-accent"
                  : "border-hairline text-primary hover:bg-canvas-subtle"
              )}
            >
              <Dot tone={tone as any} pulse={ex.status === "running"} className="shrink-0" />
              <span className="truncate">{label}</span>
            </button>
          );
        })}
      </div>

      <Link
        href="/history"
        className="flex shrink-0 items-center justify-center rounded border border-hairline p-1.5 text-primary transition-colors hover:border-accent/60 hover:text-accent"
        title="Conversation history"
        aria-label="Conversation history"
      >
        <History className="h-3.5 w-3.5" strokeWidth={1.5} />
      </Link>

      {menu &&
        typeof window !== "undefined" &&
        createPortal(
          <div
            ref={menuRef}
            style={{
              left: Math.max(8, Math.min(menu.x, window.innerWidth - 190)),
              top: Math.max(8, Math.min(menu.y, window.innerHeight - 160)),
            }}
            className="fixed z-[9999] w-44 rounded border border-hairline bg-canvas-panel py-1 shadow-xl"
          >
            <ContextMenuItem
              label="Close this"
              onClick={() => {
                dispatch({ type: "closeExecution", executionId: menu.ex.execution_id });
                setMenu(null);
              }}
            />
            <ContextMenuItem
              label="Close to the right"
              onClick={() => {
                dispatch({ type: "closeExecutionsToRight", executionId: menu.ex.execution_id });
                setMenu(null);
              }}
            />
            <ContextMenuItem
              label="Close to the left"
              onClick={() => {
                dispatch({ type: "closeExecutionsToLeft", executionId: menu.ex.execution_id });
                setMenu(null);
              }}
            />
            <div className="my-1 border-t border-hairline" />
            <ContextMenuItem
              label="Close all"
              onClick={() => {
                dispatch({ type: "closeAllExecutions" });
                setMenu(null);
              }}
            />
          </div>,
          document.body
        )}
    </div>
  );
}

function ContextMenuItem({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full px-3 py-1.5 text-left text-[11px] text-primary transition-colors hover:bg-canvas-subtle"
    >
      {label}
    </button>
  );
}

function EventCard({ event }: { event: AgentEvent }) {
  switch (event.type) {
    case "agent.message":
      return <MessageCard event={event} />;
    case "chat.user":
      return <ChatUserCard event={event} />;
    case "chat.assistant":
      return <ChatAssistantCard event={event} isStreaming={false} />;
    case "tool.started":
    case "tool.progress":
    case "tool.completed":
    case "tool.failed":
      return <ToolCard event={event} />;
    case "artifact.created":
      return <ArtifactCard event={event} />;
    case "agent.reasoning_delta":
    case "agent.reasoning_started":
      return null;
    case "agent.reasoning_completed":
      return <ReasoningEventCard event={event} />;
    case "agent.decision_started":
    case "agent.tool_requested":
      return <DecisionEventCard event={event} />;
    case "agent.observation_created":
      return <ObservationEventCard event={event} />;
    case "agent.plan_updated":
      return <PlanUpdatedCard event={event} />;
    case "agent.execution_interrupted":
      return <InterruptedEventCard event={event} />;
    case "agent.started":
    case "agent.plan_created":
    case "agent.completed":
    case "agent.failed":
    case "incident.updated":
      return <StatusCard event={event} />;
    case "subagent.spawned":
    case "subagent.started":
    case "subagent.completed":
    case "subagent.failed":
    case "subagent.cancelled":
      return <SubagentCard event={event} />;
    case "mode.switched":
      return <ModeSwitchCard event={event} />;
    default:
      return null;
  }
}

function MessageCard({ event }: { event: AgentEvent }) {
  const msg = ((event.payload?.message as string | undefined) || event.label || "").trim();
  if (!msg) return null;
  return (
    <div className="px-1 py-2">
      {/\bINC-[A-Z0-9\-]+\b/i.test(msg) ? <CitedText text={msg} /> : <MarkdownRenderer content={msg} />}
    </div>
  );
}

function CitedText({ text }: { text: string }) {
  const parts = text.split(/(\bINC-[A-Z0-9\-]+\b)/gi);
  return (
    <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-secondary">
      {parts.map((part, i) => {
        if (/^INC-[A-Z0-9\-]+$/i.test(part)) {
          return (
            <AICitation
              key={i}
              label={part}
              title={`Incident ${part}`}
              url={`/incidents?highlight=${encodeURIComponent(part)}`}
              description="Open incident record"
            />
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}

function ModeSwitchCard({ event }: { event: AgentEvent }) {
  const mode = (event.payload?.mode as string) || "chat";
  return (
    <div className="flex justify-center py-2 text-[10px] text-muted">
      <Mono tone="muted">— switched to {mode === "chat" ? "Ask" : "Agent"} mode —</Mono>
    </div>
  );
}

function ChatUserCard({ event }: { event: AgentEvent }) {
  const msg = (event.payload?.message as string) || event.label;
  const context = (event.payload?.context_text as string) || "";
  const images = (event.payload?.images as number) || 0;
  return (
    <div className="ml-auto max-w-[85%] space-y-1">
      {context && (
        <p className="text-right text-[9px] text-accent">Context: {context}</p>
      )}
      <div className="rounded rounded-tr-none border border-accent/30 bg-accent-dim/20 p-2.5">
        <p className="text-[12px] leading-relaxed text-primary">{msg}</p>
        {images > 0 && (
          <p className="mt-1 text-[9px] text-accent">{images} image(s) attached</p>
        )}
      </div>
    </div>
  );
}

function ChatAssistantCard({
  event,
  isStreaming,
}: {
  event: AgentEvent;
  isStreaming?: boolean;
}) {
  const msg = ((event.payload?.message as string | undefined) || event.label || "").trim();
  const model = (event.payload?.model as string) || event.provider || "model";
  if (!msg) return null;
  return (
    <div className="max-w-[90%]">
      <AssistantMessage message={msg} model={model} isStreaming={isStreaming} />
    </div>
  );
}

function ToolCard({ event }: { event: AgentEvent }) {
  const { tool_name, provider, payload, label } = event;
  const duration = payload?.duration_ms as number | undefined;
  const outputSummary = payload?.output_summary as string | undefined;
  const fallback = payload?.fallback_used as boolean;
  const fallbackReason = payload?.fallback_reason as string;
  const inputs = payload?.inputs as Record<string, unknown> | undefined;

  const running = event.type === "tool.started" || event.type === "tool.progress";
  const failed = event.type === "tool.failed";
  const completed = event.type === "tool.completed";

  const status = running ? "running" : failed ? "error" : completed ? "success" : "pending";

  const summary = [
    provider,
    duration !== undefined ? `${Math.round(duration)}ms` : undefined,
    outputSummary,
  ]
    .filter(Boolean)
    .join(" · ");

  const argsNode =
    inputs && Object.keys(inputs).length > 0 ? (
      <pre className="overflow-x-auto rounded bg-canvas-subtle p-1.5 font-mono text-[9px] text-secondary">
        {JSON.stringify(inputs, null, 2)}
      </pre>
    ) : undefined;

  const resultNode = (
    <div className="space-y-1.5">
      {outputSummary && <div className="text-[10px] text-secondary">{outputSummary}</div>}
      {(payload?.note as string) && (
        <div className="text-[9px] text-warning">{(payload?.note as string)}</div>
      )}
      {fallback && fallbackReason && (
        <div className="flex items-center gap-1 text-[9px] text-warning">
          <span>↳</span>
          <span>{fallbackReason}</span>
        </div>
      )}
      {failed && event.error_message && (
        <div className="text-[10px] text-critical">{event.error_message}</div>
      )}
      {event.tool_call_id && (
        <div className="font-mono text-[9px] text-muted">call: {event.tool_call_id}</div>
      )}
      {event.artifact_ref && typeof event.payload?.link === "string" && (event.payload.link as string).startsWith("/") && (
        <Link
          href={event.payload.link as string}
          onClick={(e) => e.stopPropagation()}
          className="block text-accent hover:underline"
        >
          open {event.artifact_type} → {event.artifact_ref}
        </Link>
      )}
      {tool_name === "threat_intelligence_lookup" && Array.isArray(payload?.records) && (
        <TavilySources records={payload.records as any[]} />
      )}
    </div>
  );

  return (
    <AIToolCall
      name={label || tool_name || "tool"}
      status={status as any}
      summary={summary}
      args={argsNode}
      result={resultNode}
      className="border-0 bg-transparent rounded-none"
    />
  );
}

function TavilySources({ records }: { records: any[] }) {
  const sources = records
    .filter((r) => r.url || r.title)
    .map((r, i) => ({
      id: `${r.url || i}`,
      title: r.title || "Source",
      url: r.url || "#",
      snippet: r.summary || r.content || r.value || "",
    }));
  if (sources.length === 0) return null;
  return <AISources label="Sources" sources={sources} defaultOpen={sources.length <= 3} />;
}

function ArtifactCard({ event }: { event: AgentEvent }) {
  const link = event.payload?.link as string | undefined;
  const isRealLink = typeof link === "string" && link.startsWith("/");
  const card = (
    <div className="flex items-center justify-between rounded border border-warning/30 bg-canvas-panel p-2.5 text-[11px] text-warning">
      <div className="flex items-center gap-2">
        <Shield className="h-3 w-3" strokeWidth={1.5} />
        <span className="font-mono uppercase tracking-wider">{event.label}</span>
      </div>
      <span className="text-[9px] text-muted">{event.artifact_type}</span>
    </div>
  );
  if (isRealLink) {
    return <Link href={link}>{card}</Link>;
  }
  return card;
}

function StatusCard({ event }: { event: AgentEvent }) {
  const Icon =
    event.type === "agent.completed"
      ? CheckCircle2
      : event.type === "agent.failed"
      ? XCircle
      : event.type === "agent.plan_created"
      ? Sparkles
      : event.type === "agent.started"
      ? Sparkles
      : event.type === "incident.updated"
      ? CheckCircle2
      : Bot;
  const tone =
    event.type === "agent.completed" ? "success" : event.type === "agent.failed" ? "critical" : "accent";
  const toneClass =
    tone === "success" ? "text-success" : tone === "critical" ? "text-critical" : "text-accent";
  return (
    <div className="flex items-center gap-2 border-b border-hairline py-2">
      <Dot tone={tone as any} pulse={event.type === "agent.started"} />
      <Icon className={cn("h-3.5 w-3.5", toneClass)} strokeWidth={1.5} />
      <Mono tone={tone as any}>{event.label}</Mono>
    </div>
  );
}

function SubagentCard({ event }: { event: AgentEvent }) {
  const Icon =
    event.type === "subagent.completed"
      ? CheckCircle2
      : event.type === "subagent.failed"
      ? XCircle
      : event.type === "subagent.cancelled"
      ? XCircle
      : event.type === "subagent.started"
      ? LoaderCircle
      : Users;
  const tone: "success" | "critical" | "warning" | "accent" =
    event.type === "subagent.completed"
      ? "success"
      : event.type === "subagent.failed"
      ? "critical"
      : event.type === "subagent.cancelled"
      ? "warning"
      : "accent";
  const running = event.type === "subagent.started" || event.type === "subagent.spawned";
  const payload = (event.payload || {}) as Record<string, unknown>;
  const status = String(payload.status || event.type.replace("subagent.", ""));
  const toolCalls = Number(payload.tool_calls_count) || undefined;
  const duration = Number(payload.duration_ms) || undefined;
  const toneClass =
    tone === "success"
      ? "text-success"
      : tone === "critical"
      ? "text-critical"
      : tone === "warning"
      ? "text-warning"
      : "text-accent";
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-hairline py-2 text-[11px]">
      <div className="flex min-w-0 flex-1 items-center gap-2">
        {running ? (
          <LoaderCircle className="h-3.5 w-3.5 animate-spin text-accent" strokeWidth={1.5} />
        ) : (
          <Icon className={cn("h-3.5 w-3.5", toneClass)} strokeWidth={1.5} />
        )}
        <Mono tone={tone}>{event.label}</Mono>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-[9px] text-muted">
        {!!payload.profile_id && <Chip tone={tone}>{String(payload.profile_id)}</Chip>}
        {!!payload.mode && <span>{String(payload.mode)}</span>}
        {!!payload.subagent_id && (
          <span className="font-mono">{String(payload.subagent_id)}</span>
        )}
        {status ? <Chip tone={tone}>{status}</Chip> : null}
        {typeof toolCalls === "number" && <span>{toolCalls} tools</span>}
        {typeof duration === "number" && <span>{Math.round(duration)}ms</span>}
      </div>
      {event.error_message && (
        <div className="w-full text-[10px] text-critical">{event.error_message}</div>
      )}
      {!!payload.result_summary && (
        <div className="w-full text-[10px] text-secondary">{String(payload.result_summary)}</div>
      )}
    </div>
  );
}

function ReasoningEventCard({ event }: { event: AgentEvent }) {
  const { state } = useAgent();
  const p = event.payload || {};
  const summary = p.summary as string | undefined;
  const source = p.source as string | undefined;
  const reasoningId = (p.reasoning_id as string) || `${event.execution_id}:${event.sequence}`;
  const started = state.events.find(
    (e) =>
      e.type === "agent.reasoning_started" &&
      (((e.payload?.reasoning_id as string) || `${e.execution_id}:${e.sequence}`) === reasoningId)
  );
  const durationMs =
    started && event.timestamp && started.timestamp
      ? Math.max(0, new Date(event.timestamp).getTime() - new Date(started.timestamp).getTime())
      : undefined;
  return (
    <AIReasoning isStreaming={false} defaultOpen={false} duration={durationMs ? durationMs / 1000 : undefined}>
      <div className="mb-1.5 flex items-center gap-2">
        <ScrollText className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
        <Mono tone="accent">reasoning</Mono>
        {source && <Chip tone="muted">{source}</Chip>}
      </div>
      <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-secondary">
        {summary || event.label || "..."}
      </p>
    </AIReasoning>
  );
}

function DecisionEventCard({ event }: { event: AgentEvent }) {
  const p = event.payload || {};
  const toolName = (p.tool_name as string) || event.tool_name || "";
  const label = (p.label as string) || event.label || toolName;
  const running = event.type === "agent.decision_started";
  return (
    <div className="border-b border-hairline py-2 text-[11px]">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {running ? (
            <LoaderCircle className="h-3.5 w-3.5 animate-spin text-accent" strokeWidth={1.5} />
          ) : (
            <Play className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
          )}
          <Mono tone="accent">{label || toolName}</Mono>
        </div>
        <div className="flex items-center gap-1.5 text-[9px] text-muted">
          <Chip tone={running ? "accent" : "warning"}>{running ? "running" : "requested"}</Chip>
          {typeof p.step_index === "number" && <span>step {Number(p.step_index) + 1}</span>}
        </div>
      </div>
      {toolName && toolName !== label && <div className="mt-0.5 font-mono text-[10px] text-muted">{toolName}</div>}
      {!!p.inputs_safe &&
        Object.keys(p.inputs_safe as Record<string, unknown>).length > 0 && (
          <pre className="mt-2 overflow-x-auto rounded bg-canvas-subtle p-1.5 font-mono text-[9px] text-secondary">
            {JSON.stringify(p.inputs_safe, null, 2)}
          </pre>
        )}
    </div>
  );
}

function observationSummary(
  summary: string,
  facts: Record<string, unknown>,
  source: string
): string {
  if (summary) return summary;
  const status = facts.status ? String(facts.status) : "";
  if (source === "manage_artifacts") {
    const deleted =
      typeof facts.deleted === "number"
        ? facts.deleted
        : typeof facts.deleted === "string"
        ? Number(facts.deleted)
        : undefined;
    const count =
      typeof facts.artifact_count === "number"
        ? facts.artifact_count
        : typeof facts.artifact_count === "string"
        ? Number(facts.artifact_count)
        : undefined;
    const projectId = facts.project_id ? String(facts.project_id) : "";
    if (deleted !== undefined && count !== undefined) {
      return `Deleted ${deleted} artifact type(s) · ${count} total for ${projectId || "project"}`;
    }
    if (count !== undefined) return `${status || "completed"} · ${count} artifact(s)`;
  }
  const parts: string[] = [];
  if (status) parts.push(status);
  if (typeof facts.count === "number") parts.push(`${facts.count} items`);
  if (typeof facts.artifact_count === "number") parts.push(`${facts.artifact_count} artifact(s)`);
  if (parts.length) return parts.join(" · ");
  const first = Object.entries(facts).slice(0, 2);
  if (first.length) {
    return first
      .map(([k, v]) => `${k}: ${typeof v === "object" ? "…" : String(v)}`)
      .join(" · ");
  }
  return "Observation recorded";
}

function ObservationEventCard({ event }: { event: AgentEvent }) {
  const p = event.payload || {};
  const rawSummary = (p.summary as string) || event.label || "";
  const facts = (p.facts as Record<string, unknown>) || {};
  const source = (p.source as string) || event.provider || "";
  const stepIndex = typeof p.step_index === "number" ? p.step_index : -1;
  const [expanded, setExpanded] = useState(false);
  const entries = Object.entries(facts);
  const summary = observationSummary(rawSummary, facts, source);
  const hasGrid = entries.length > 0;

  return (
    <div
      onClick={() => hasGrid && setExpanded((e) => !e)}
      className={cn(
        "border-b border-hairline py-2",
        hasGrid && "cursor-pointer"
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] leading-relaxed text-secondary">
            {stepIndex >= 0 && (
              <span className="text-[9px] text-muted">step {stepIndex + 1} · </span>
            )}
            {source && <span className="text-[9px] text-muted">{source} — </span>}
            <span className="text-primary">{summary}</span>
          </p>
        </div>
        {hasGrid && (
          <ChevronDown
            className={cn("h-3.5 w-3.5 shrink-0 text-muted transition-transform", expanded && "rotate-180")}
            strokeWidth={1.5}
          />
        )}
      </div>

      {expanded && hasGrid && (
        <div className="mt-2 grid grid-cols-2 gap-1.5 border-t border-hairline pt-2">
          {entries.map(([key, value]) => (
            <div key={key}>
              <Mono tone="muted" className="block truncate text-[8px]">
                {key}
              </Mono>
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

function PlanUpdatedCard({ event }: { event: AgentEvent }) {
  const p = event.payload || {};
  const reason = (p.reason as string) || "";
  return (
    <div className="flex items-center gap-2 border-b border-hairline py-2">
      <Sparkles className="h-3.5 w-3.5 text-accent" strokeWidth={1.5} />
      <div className="min-w-0 flex-1">
        <Mono tone="accent">plan updated</Mono>
        {reason && <p className="mt-0.5 text-[10px] text-secondary">{reason}</p>}
      </div>
    </div>
  );
}

function InterruptedEventCard({ event }: { event: AgentEvent }) {
  const p = event.payload || {};
  const reason = (p.reason as string) || event.error_message || "";
  return (
    <div className="flex items-start gap-2 border-l-2 border-critical pl-3 py-1 text-[11px] text-critical">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
      <div>
        <Mono tone="critical">interrupted</Mono>
        {reason && <div className="mt-0.5 text-[10px] text-critical/80">{reason}</div>}
      </div>
    </div>
  );
}


type TraceCategory =
  | "thought"
  | "search"
  | "read"
  | "explore"
  | "sentinel"
  | "simulation"
  | "defense"
  | "intelligence"
  | "automation"
  | "audit"
  | "build"
  | "subagent"
  | "devtools"
  | "verification"
  | "decision"
  | "observation"
  | "plan"
  | "message"
  | "status"
  | "artifact"
  | "chat"
  | "tool"
  | "mode"
  | "unknown";

const CATEGORY_META: Record<TraceCategory, { verb: string; noun: string }> = {
  thought: { verb: "Thought", noun: "thoughts" },
  search: { verb: "Searched", noun: "searches" },
  read: { verb: "Read", noun: "reads" },
  explore: { verb: "Explored", noun: "explores" },
  sentinel: { verb: "Sentinel", noun: "sentinel" },
  simulation: { verb: "Simulated", noun: "simulations" },
  defense: { verb: "Defended", noun: "defenses" },
  intelligence: { verb: "Intelligence", noun: "intel" },
  automation: { verb: "Automation", noun: "automations" },
  audit: { verb: "Audit", noun: "audits" },
  build: { verb: "Build", noun: "builds" },
  subagent: { verb: "Subagent", noun: "subagents" },
  devtools: { verb: "Test", noun: "tests" },
  verification: { verb: "Verified", noun: "verifications" },
  decision: { verb: "Deciding", noun: "decisions" },
  observation: { verb: "Observed", noun: "observations" },
  plan: { verb: "Plan", noun: "plans" },
  message: { verb: "Message", noun: "messages" },
  status: { verb: "Status", noun: "statuses" },
  artifact: { verb: "Artifact", noun: "artifacts" },
  chat: { verb: "Chat", noun: "messages" },
  tool: { verb: "Tool", noun: "tools" },
  mode: { verb: "Mode", noun: "mode" },
  unknown: { verb: "Event", noun: "events" },
};

function isTraceEvent(event: AgentEvent): boolean {
  const t = event.type;
  if (t === "agent.reasoning_delta") return false;
  if (t === "agent.reasoning_started") return false;
  if (t.startsWith("generation.")) return false;
  if (t.startsWith("navigation.")) return false;
  if (t.startsWith("element.")) return false;
  if (t === "artifact.created") return true;
  if (t.startsWith("artifact.")) return false;
  return true;
}

function getToolCategory(toolName?: string): TraceCategory {
  if (!toolName) return "tool";
  if (toolName.startsWith("search_")) return "search";
  if (
    toolName.startsWith("get_") ||
    toolName.startsWith("inspect_") ||
    toolName.startsWith("observe_")
  )
    return "read";
  if (
    toolName.startsWith("correlate_") ||
    toolName.startsWith("investigate_") ||
    toolName.startsWith("trace_") ||
    toolName.startsWith("reconstruct_") ||
    toolName.startsWith("calculate_") ||
    toolName.startsWith("compare_") ||
    toolName.startsWith("rank_") ||
    toolName.startsWith("detect_") ||
    toolName === "test_hypothesis"
  )
    return "explore";
  if (
    toolName.includes("sentinel") ||
    toolName === "confirm_ground_truth" ||
    toolName === "propose_rule" ||
    toolName === "validate_rule" ||
    toolName === "run_replay"
  )
    return "sentinel";
  if (
    toolName === "run_blastscope" ||
    toolName === "build_or_update_ecosystem" ||
    toolName.includes("orbit") ||
    toolName.includes("reach") ||
    toolName.includes("segment")
  )
    return "simulation";
  if (toolName === "run_what_if") return "defense";
  if (toolName === "threat_intelligence_lookup") return "intelligence";
  if (toolName === "trigger_automation") return "automation";
  if (toolName === "run_tests") return "devtools";
  if (toolName === "verify_conclusion") return "verification";
  if (
    toolName.includes("audit") ||
    toolName === "seal_incident" ||
    toolName === "create_finding" ||
    toolName === "append_audit_record" ||
    toolName === "verify_audit_chain"
  )
    return "audit";
  if (toolName === "generate_artifacts" || toolName === "manage_artifacts") return "build";
  if (toolName === "spawn_subagent") return "subagent";
  return "tool";
}

function eventCategory(event: AgentEvent): TraceCategory {
  const t = event.type;
  if (t === "agent.reasoning_started" || t === "agent.reasoning_completed") return "thought";
  if (t === "agent.decision_started" || t === "agent.tool_requested") return "decision";
  if (t === "agent.observation_created" || t === "agent.observation") return "observation";
  if (t === "agent.plan_created" || t === "agent.plan_updated") return "plan";
  if (t === "agent.message") return "message";
  if (t === "chat.user" || t === "chat.assistant") return "chat";
  if (t === "mode.switched") return "mode";
  if (t.startsWith("subagent.")) return "subagent";
  if (t.startsWith("tool.")) return getToolCategory(event.tool_name);
  if (t === "artifact.created") return "artifact";
  if (
    t === "agent.started" ||
    t === "agent.completed" ||
    t === "agent.failed" ||
    t === "agent.execution_interrupted" ||
    t === "agent.verification_started" ||
    t === "agent.verification_completed" ||
    t === "agent.awaiting_input" ||
    t === "incident.updated"
  )
    return "status";
  if (t.startsWith("agent.")) return "status";
  return "unknown";
}

function operationId(event: AgentEvent): string {
  if (event.type.startsWith("tool.")) {
    return event.tool_call_id || `${event.execution_id}:${event.sequence}`;
  }
  if (event.type === "agent.reasoning_started" || event.type === "agent.reasoning_completed") {
    return (
      (event.payload?.reasoning_id as string) ||
      `${event.execution_id}:${event.sequence}`
    );
  }
  return `${event.execution_id}:${event.sequence}`;
}

type TraceStats = {
  total: number;
  breakdown: { category: TraceCategory; count: number }[];
};

function traceStats(events: AgentEvent[]): TraceStats {
  const breakdown: { category: TraceCategory; count: number }[] = [];
  const seen = new Set<string>();
  let total = 0;
  for (const e of events) {
    const cat = eventCategory(e);
    const opId = operationId(e);
    const key = `${cat}:${opId}`;
    if (seen.has(key)) continue;
    seen.add(key);
    total++;
    const existing = breakdown.find((b) => b.category === cat);
    if (existing) existing.count += 1;
    else breakdown.push({ category: cat, count: 1 });
  }
  return { total, breakdown };
}

function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${Math.max(1, Math.round(ms))}ms`;
  const s = ms / 1000;
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}m${rem}s`;
}

function runDuration(events: AgentEvent[], status: string): string | null {
  if (events.length < 2) return null;
  if (status !== "completed" && status !== "failed") return null;
  const first = events[0]?.timestamp;
  const last = events[events.length - 1]?.timestamp;
  if (!first || !last) return null;
  const ms = new Date(last).getTime() - new Date(first).getTime();
  if (ms <= 0) return null;
  return formatDurationMs(ms);
}

function TraceTimeline({
  events,
  executionId,
  status,
  executing,
  modelStatus,
  currentAction,
}: {
  events: AgentEvent[];
  executionId?: string;
  status: string;
  executing: boolean;
  modelStatus: string;
  currentAction: AgentCurrentAction | null;
}) {
  const chatExecutionIds = useMemo(
    () =>
      new Set(
        events
          .filter((e) => e.type === "chat.user" || e.type === "chat.assistant")
          .map((e) => e.execution_id)
      ),
    [events]
  );
  const traceEvents = useMemo(() => {
    const seenIds = new Set<number>();
    return events
      .filter((e) => !executionId || e.execution_id === executionId)
      .filter(
        (e) =>
          isTraceEvent(e) &&
          !(
            chatExecutionIds.has(e.execution_id) &&
            (e.type === "agent.started" || e.type === "agent.completed")
          )
      )
      .filter((e) => {
        if (e.id && e.id > 0) {
          if (seenIds.has(e.id)) return false;
          seenIds.add(e.id);
        }
        return true;
      });
  }, [events, chatExecutionIds, executionId]);
  const stats = useMemo(() => traceStats(traceEvents), [traceEvents]);
  const duration = useMemo(() => runDuration(traceEvents, status), [traceEvents, status]);

  const tone: "accent" | "success" | "critical" | "muted" = executing
    ? "accent"
    : status === "completed"
    ? "success"
    : status === "failed" || status === "interrupted"
    ? "critical"
    : "muted";

  const liveText = executing
    ? currentAction?.label || modelStatus || "running"
    : status === "completed"
    ? "Completed"
    : status === "failed"
    ? "Failed"
    : status === "interrupted"
    ? "Interrupted"
    : "Idle";

  const breakdown = stats.breakdown
    .map((b) => `${b.count} ${CATEGORY_META[b.category].noun}`)
    .join(" · ");

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 border-b border-hairline pb-2 text-[11px]">
        <Dot tone={tone as any} pulse={executing} />
        <span className="font-medium text-primary">{liveText}</span>
        <span className="text-[10px] text-muted">
          {stats.total > 0 ? ` · ${stats.total} steps` : ""}
          {duration ? ` · ${duration}` : ""}
          {breakdown ? ` · ${breakdown}` : ""}
        </span>
      </div>
      <div className="space-y-3">
        {traceEvents.map((event, idx) => (
          <EventCard
            key={
              event.id
                ? `event:${event.id}`
                : `${event.execution_id}:${event.sequence}:${event.type}:${idx}`
            }
            event={event}
          />
        ))}
      </div>
    </div>
  );
}

type PendingAction = {
  objective: string;
  incidentId?: string;
  executionId?: string;
  targets: string[];
  kind: "delete" | "overwrite";
  isContinue: boolean;
};

function PendingActionGate({
  pending,
  onApprove,
  onReject,
}: {
  pending: PendingAction;
  onApprove: () => void;
  onReject: () => void;
}) {
  const allLines = pending.targets.map((t, i) => ({
    id: `target-${i}`,
    content: t,
    kind: pending.kind === "delete" ? ("removed" as const) : ("added" as const),
  }));

  return (
    <div className="space-y-3 rounded border border-hairline bg-canvas-panel/60 p-3">
      <AIDiff
        title={pending.kind === "delete" ? "Proposed deletion" : "Proposed overwrite"}
        lines={allLines}
        onAccept={onApprove}
        onReject={onReject}
      />
      <AIApproval
        question={`Approve ${pending.kind} of ${pending.targets.join(", ")}?`}
        options={[
          { id: "proceed", label: "Proceed", destructive: pending.kind === "delete" },
          { id: "cancel", label: "Cancel" },
        ]}
        onDecide={(option) => {
          if (option.id === "proceed") onApprove();
          else onReject();
        }}
      />
    </div>
  );
}

function ReplayBranchPanel({ projectId }: { projectId: string }) {
  const replay = useProjectReplay(projectId);
  if (!replay) return null;

  const preEvents = replay.events.filter((e) => e.lane !== "post");
  const postEvents = replay.events.filter((e) => e.lane !== "pre");

  return (
    <AIBranch defaultBranch={0} className="rounded border border-hairline bg-canvas-panel/60 p-3">
      <div className="mb-2 flex items-center justify-between">
        <Mono tone="accent">Replay divergence</Mono>
        <AIBranchSelector from="assistant" className="px-0">
          <AIBranchPrevious />
          <AIBranchPage />
          <AIBranchNext />
        </AIBranchSelector>
      </div>
      <AIBranchMessages>
        <ReplayLane events={preEvents} label="pre-patch" replay={replay} />
        <ReplayLane events={postEvents} label="post-patch" replay={replay} />
      </AIBranchMessages>
    </AIBranch>
  );
}

function ReplayLane({ events, label, replay }: { events: any[]; label: string; replay: any }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-muted">{label}</span>
        <span className="text-[9px] text-muted">{replay.incidentId}</span>
      </div>
      <div className="space-y-1.5">
        {events.length === 0 && <div className="text-[10px] text-muted">No events</div>}
        {events.map((e, i) => (
          <div key={i} className="flex items-center gap-2 rounded border border-hairline bg-canvas-subtle px-2 py-1.5 text-[10px]">
            <Dot tone={e.tone} pulse={false} />
            <span className="text-primary">{e.label}</span>
            {e.sub && <span className="text-muted">{e.sub}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
