"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAnvaya } from "@/lib/store";
import { applyBuildEvent, ArtifactBuildState } from "@/lib/build";
import { cleanObjective } from "@/lib/utils";
import { trackStartupedEvent } from "@/lib/startuped";
import {
  AnvayaAPI,
  AgentEvent,
  AgentPlanStep,
  AgentObservation,
  AgentExecutionContext,
  useAgentExecutions,
} from "@/lib/api";

export type AgentProfile = {
  id: string;
  name: string;
  display_name: string;
  purpose: string;
  description: string;
  system_instruction: string;
  model_provider: string;
  model_name: string;
  temperature: number;
  verbosity: string;
  personality: string;
  expertise: string[];
  autonomy_level: string;
  preferred_tools: string[];
  fallback_tools: string[];
  confirmation_policy: string;
  response_style: string;
  icon: string;
  accent: string;
  status: string;
};

export type Incident = {
  incident_id: string;
  title: string;
  description?: string;
  status: string;
  self_correction_status: string;
  severity: string;
  attack_family: string;
  scenario_id: string;
  host?: string;
  user?: string;
};

export type AgentExecution = {
  execution_id: string;
  objective: string;
  incident_id: string;
  status: string;
  started_at: string;
  completed_at?: string;
  duration_ms?: number;
  result_summary?: string;
  profile_id?: string;
  mode?: string;
};

export type ModelPricing = {
  input_per_million: number | null;
  cached_input_per_million: number | null;
  output_per_million: number | null;
};

export type ModelBenchmarkEvidence = {
  name: string;
  value: string;
  source: string;
  url?: string | null;
};

export type ModelUsage = {
  rank?: number | null;
  tokens?: number | null;
  trend?: string;
};

export type ModelAnvayaData = {
  mission_success?: number | null;
  tool_success?: number | null;
  verification?: number | null;
  ttft_ms?: number | null;
  tokens_per_sec?: number | null;
  cost_per_mission?: number | null;
  recovery?: number | null;
  false_positive_rate?: number | null;
  usage?: ModelUsage;
};

export type ModelConfig = {
  id: string;
  provider: string;
  provider_model_id: string;
  model: string;
  maker: string;
  family: string;
  display_name: string;
  description: string;
  purpose: string;
  capabilities: string[];
  context_window: number;
  supports_tools: boolean;
  supports_streaming: boolean;
  supports_reasoning: boolean;
  supports_multimodal: boolean;
  latency_class: string;
  cost_class: string;
  availability: string;
  configured: boolean;
  default_temperature: number;
  recommended_for: string[];
  recommended_profiles: string[];
  logo_domain: string;
  protocol: string;
  base_url: string;
  pricing: ModelPricing | null;
  pricing_mode: string;
  cost_per_request: number | null;
  access_class: string;
  privacy_class: string;
  gateway_type: string;
  aliases: string[];
  max_tokens: number | null;
  profile_fit: Record<string, number | null>;
  evidence_confidence: string;
  anvaya_measured: boolean;
  recommendation_confidence: string;
  benchmark_evidence: ModelBenchmarkEvidence[];
  anvaya_data: ModelAnvayaData | null;
  best_for: string[];
  quality_class: string | null;
  evidence_level: string;
  fit_reason: string;
  limitations: string;
  provisional: boolean;
  experimental: boolean;
};

export type AgentCurrentAction = {
  tool_name: string;
  label: string;
  status: string;
  step_index: number;
};

export const CONSOLE_WIDTH = 400;
export const CONSOLE_MIN_WIDTH = 260;
export const CONSOLE_MAX_WIDTH = 600;

export type AgentMode = "agentic" | "chat";

interface AgentState {
  open: boolean;
  width: number;
  profile: AgentProfile | null;
  model: ModelConfig | null;
  profiles: AgentProfile[];
  models: ModelConfig[];
  profileMenuOpen: boolean;
  objective: string;
  contextText: string;
  incidentId: string;
  executionId: string | undefined;
  executing: boolean;
  events: AgentEvent[];
  status: string;
  error: string | null;
  scrollLocked: boolean;
  profileId: string;
  executions: AgentExecution[];
  closedExecutionIds: string[];
  mode: AgentMode;
  streamingMessage: string;
  streamingMessageModel: string;
  projectId: string;
  reasoning: string;
  reasoningSource: string;
  currentAction: AgentCurrentAction | null;
  plan: AgentPlanStep[];
  observations: AgentObservation[];
  interrupted: boolean;
  interruptionReason: string;
  modelStatus: string;
  build: ArtifactBuildState | null;
}

export type AgentAction =
  | { type: "setOpen"; value: boolean }
  | { type: "setWidth"; value: number }
  | { type: "setProfiles"; value: AgentProfile[] }
  | { type: "setModels"; value: ModelConfig[] }
  | { type: "toggle" }
  | { type: "setProfile"; profile: AgentProfile }
  | { type: "setModel"; model: ModelConfig }
  | { type: "setProfileMenu"; value: boolean }
  | { type: "setObjective"; value: string }
  | { type: "setContextText"; value: string }
  | { type: "setIncidentId"; value: string }
  | { type: "setExecutionId"; value: string | undefined }
  | { type: "setExecuting"; value: boolean }
  | { type: "setEvents"; value: AgentEvent[] }
  | { type: "appendEvents"; value: AgentEvent[] }
  | { type: "setStatus"; value: string }
  | { type: "setError"; value: string | null }
  | { type: "setScrollLocked"; value: boolean }
  | { type: "resetEvents" }
  | { type: "setExecutions"; value: AgentExecution[] }
  | { type: "loadExecution"; execution: AgentExecution }
  | { type: "closeExecution"; executionId: string }
  | { type: "closeAllExecutions" }
  | { type: "closeExecutionsToRight"; executionId: string }
  | { type: "closeExecutionsToLeft"; executionId: string }
  | { type: "setClosedExecutionIds"; value: string[] }
  | { type: "setMode"; value: AgentMode }
  | { type: "setStreamingMessage"; value: string; model: string }
  | { type: "setProjectId"; value: string }
  | { type: "setReasoning"; value: string; source?: string }
  | { type: "appendReasoning"; value: string }
  | { type: "setReasoningSource"; value: string }
  | { type: "setCurrentAction"; value: AgentCurrentAction | null }
  | { type: "setPlan"; value: AgentPlanStep[] }
  | { type: "setObservations"; value: AgentObservation[] }
  | { type: "appendObservation"; value: AgentObservation }
  | { type: "setInterrupted"; value: boolean; reason?: string }
  | { type: "setModelStatus"; value: string }
  | { type: "setBuild"; value: ((build: ArtifactBuildState | null) => Partial<ArtifactBuildState>) | Partial<ArtifactBuildState> }
  | { type: "resetBuild" }
  | { type: "setBuildNavigationConsumed"; value: boolean };

function reducer(state: AgentState, action: AgentAction): AgentState {
  switch (action.type) {
    case "setOpen":
      return { ...state, open: action.value };
    case "setWidth":
      return { ...state, width: Math.min(CONSOLE_MAX_WIDTH, Math.max(CONSOLE_MIN_WIDTH, action.value)) };
    case "setProfiles":
      return { ...state, profiles: action.value };
    case "setModels":
      return { ...state, models: action.value };
    case "toggle":
      return { ...state, open: !state.open };
    case "setProfile":
      return { ...state, profile: action.profile, profileId: action.profile.id };
    case "setModel":
      return { ...state, model: action.model };
    case "setProfileMenu":
      return { ...state, profileMenuOpen: action.value };
    case "setObjective":
      return { ...state, objective: action.value };
    case "setContextText":
      return { ...state, contextText: action.value };
    case "setIncidentId":
      return { ...state, incidentId: action.value };
    case "setExecutionId": {
      const next = action.value;
      const reset = state.executionId !== next ? _emptyBuildState() : state.build;
      return {
        ...state,
        executionId: next,
        build: reset,
        ...(state.executionId !== next ? _emptyLiveState() : {}),
      };
    }
    case "setExecuting":
      return { ...state, executing: action.value };
    case "setEvents": {
      const seenIds = new Set<number>();
      const events = (action.value || []).filter((e) => {
        if (e.id && e.id > 0) {
          if (seenIds.has(e.id)) return false;
          seenIds.add(e.id);
        }
        return true;
      });
      return { ...state, events };
    }
    case "appendEvents": {
      const seenIds = new Set(
        state.events.map((e) => e.id).filter((id): id is number => id !== undefined && id > 0)
      );
      const newEvents = action.value.filter((e) => {
        if (e.id && e.id > 0) {
          if (seenIds.has(e.id)) return false;
          seenIds.add(e.id);
        }
        return true;
      });
      return { ...state, events: [...state.events, ...newEvents] };
    }
    case "setStatus":
      return { ...state, status: action.value };
    case "setError":
      return { ...state, error: action.value };
    case "setScrollLocked":
      return { ...state, scrollLocked: action.value };
    case "setExecutions":
      return { ...state, executions: action.value };
    case "closeExecution": {
      const closed = new Set(state.closedExecutionIds);
      closed.add(action.executionId);
      const shouldReset = state.executionId === action.executionId;
      return {
        ...state,
        closedExecutionIds: Array.from(closed),
        ...(shouldReset ? _emptyExecutionState() : {}),
      };
    }
    case "closeAllExecutions":
      return {
        ...state,
        closedExecutionIds: state.executions.map((e) => e.execution_id),
        ..._emptyExecutionState(),
      };
    case "closeExecutionsToRight": {
      const index = state.executions.findIndex((e) => e.execution_id === action.executionId);
      const toClose = state.executions.slice(index + 1).map((e) => e.execution_id);
      const closed = new Set([...state.closedExecutionIds, ...toClose]);
      const shouldReset = state.executionId !== undefined && toClose.includes(state.executionId);
      return {
        ...state,
        closedExecutionIds: Array.from(closed),
        ...(shouldReset ? _emptyExecutionState() : {}),
      };
    }
    case "closeExecutionsToLeft": {
      const index = state.executions.findIndex((e) => e.execution_id === action.executionId);
      const toClose = state.executions.slice(0, index).map((e) => e.execution_id);
      const closed = new Set([...state.closedExecutionIds, ...toClose]);
      const shouldReset = state.executionId !== undefined && toClose.includes(state.executionId);
      return {
        ...state,
        closedExecutionIds: Array.from(closed),
        ...(shouldReset ? _emptyExecutionState() : {}),
      };
    }
    case "setClosedExecutionIds":
      return { ...state, closedExecutionIds: action.value };
    case "setMode":
      return { ...state, mode: action.value };
    case "setStreamingMessage":
      return { ...state, streamingMessage: action.value, streamingMessageModel: action.model };
    case "setProjectId":
      return { ...state, projectId: action.value };
    case "setReasoning":
      return {
        ...state,
        reasoning: action.value,
        reasoningSource: action.source ?? state.reasoningSource,
      };
    case "appendReasoning":
      return { ...state, reasoning: state.reasoning + action.value };
    case "setReasoningSource":
      return { ...state, reasoningSource: action.value };
    case "setCurrentAction":
      return { ...state, currentAction: action.value };
    case "setPlan":
      return { ...state, plan: action.value };
    case "setObservations":
      return { ...state, observations: action.value };
    case "appendObservation": {
      const idx = state.observations.findIndex(
        (o) => o.step_index === action.value.step_index && o.source === action.value.source
      );
      if (idx >= 0) {
        const next = [...state.observations];
        next[idx] = action.value;
        return { ...state, observations: next };
      }
      return { ...state, observations: [...state.observations, action.value] };
    }
    case "setInterrupted":
      return {
        ...state,
        interrupted: action.value,
        interruptionReason: action.reason ?? state.interruptionReason,
      };
    case "setModelStatus":
      return { ...state, modelStatus: action.value };
    case "setBuild": {
      const update =
        typeof action.value === "function"
          ? action.value(state.build)
          : action.value;
      if (!update) return state;
      if (!state.build) {
        if (!("executionId" in update)) return state;
        return { ...state, build: update as ArtifactBuildState };
      }
      return { ...state, build: { ...state.build, ...update } };
    }
    case "resetBuild":
      return { ...state, build: null };
    case "setBuildNavigationConsumed":
      return state.build
        ? { ...state, build: { ...state.build, navigateConsumed: action.value } }
        : state;
    case "loadExecution": {
      const closed = new Set(state.closedExecutionIds);
      closed.delete(action.execution.execution_id);
      return {
        ...state,
        executionId: action.execution.execution_id,
        mode: (action.execution.mode as AgentMode) || "agentic",
        incidentId: action.execution.incident_id,
        objective: cleanObjective(action.execution.objective),
        contextText: "",
        status: action.execution.status,
        events: [],
        executing: false,
        open: true,
        closedExecutionIds: Array.from(closed),
        build: _emptyBuildState(),
        ..._emptyLiveState(),
      };
    }
    case "resetEvents":
      return { ...state, ..._emptyExecutionState() };
    default:
      return state;
  }
}

function _emptyLiveState() {
  return {
    reasoning: "",
    reasoningSource: "",
    currentAction: null as AgentCurrentAction | null,
    plan: [] as AgentPlanStep[],
    observations: [] as AgentObservation[],
    interrupted: false,
    interruptionReason: "",
    modelStatus: "idle" as string,
  };
}

function _emptyExecutionState() {
  return {
    events: [] as AgentEvent[],
    status: "" as string,
    executionId: undefined as string | undefined,
    executing: false,
    contextText: "" as string,
    objective: "" as string,
    incidentId: "" as string,
    build: _emptyBuildState(),
    ..._emptyLiveState(),
  };
}

function _emptyBuildState(): ArtifactBuildState | null {
  return null;
}

const AgentCtx = createContext<{
  state: AgentState;
  dispatch: React.Dispatch<AgentAction>;
  start: (objective: string, incidentId?: string, executionId?: string) => Promise<boolean>;
  attachExecution: (executionId: string) => Promise<boolean>;
  chat: (message: string, images?: string[], contextText?: string, continueExecutionId?: string) => Promise<void>;
  chatStream: (message: string, images?: string[], contextText?: string, continueExecutionId?: string) => Promise<boolean>;
  sendFollowUp: (message: string) => Promise<boolean>;
  cancelExecution: () => Promise<void>;
  seed: () => Promise<string | undefined>;
  selectProfile: (id: string) => void;
  loadExecution: (execution: AgentExecution) => Promise<void>;
  newConversation: () => void;
  consoleWidth: number;
} | null>(null);

export function AgentProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = React.useReducer(reducer, {
    open: false,
    width: CONSOLE_WIDTH,
    profile: null,
    model: null,
    profiles: [],
    models: [],
    profileMenuOpen: false,
    objective: "",
    contextText: "",
    incidentId: "",
    executionId: undefined,
    executing: false,
    events: [],
    status: "",
    error: null,
    scrollLocked: false,
    profileId: "sentinel",
    executions: [],
    closedExecutionIds: [],
    mode: "agentic",
    streamingMessage: "",
    streamingMessageModel: "",
    projectId: "",
    reasoning: "",
    reasoningSource: "",
    currentAction: null,
    plan: [],
    observations: [],
    interrupted: false,
    interruptionReason: "",
    modelStatus: "idle",
    build: null,
  });

  const stateRef = useRef(state);
  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const previousPanelOpen = useRef(state.open);
  const previousMode = useRef(state.mode);
  const previousModelId = useRef(state.model?.id || "");
  const previousProfileId = useRef(state.profileId);
  const previousIncidentId = useRef(state.incidentId);

  useEffect(() => {
    if (previousPanelOpen.current !== state.open) {
      trackStartupedEvent({
        name: state.open ? "anvaya.agent.panel.opened" : "anvaya.agent.panel.closed",
        description: state.open ? "User opened the agent panel" : "User closed the agent panel",
        type: "behavioral",
        strength: 12,
        value: "Low",
        metadata: { surface: "agent-panel", open: state.open },
      });
      previousPanelOpen.current = state.open;
    }
  }, [state.open]);

  useEffect(() => {
    if (previousMode.current !== state.mode) {
      trackStartupedEvent({
        name: "anvaya.agent.mode.switched",
        description: `User switched the agent panel to ${state.mode} mode`,
        type: "behavioral",
        strength: 20,
        value: "Medium",
        metadata: { surface: "agent-panel", mode: state.mode },
      });
      previousMode.current = state.mode;
    }
  }, [state.mode]);

  useEffect(() => {
    const modelId = state.model?.id || "";
    if (modelId && previousModelId.current !== modelId) {
      trackStartupedEvent({
        name: "anvaya.agent.model.selected",
        description: "User selected an agent model",
        type: "behavioral",
        strength: 25,
        value: "Medium",
        metadata: {
          surface: "agent-panel",
          modelId,
          provider: state.model?.provider || "",
        },
      });
      previousModelId.current = modelId;
    }
  }, [state.model]);

  useEffect(() => {
    if (state.profileId && previousProfileId.current !== state.profileId) {
      trackStartupedEvent({
        name: "anvaya.agent.profile.selected",
        description: "User selected an agent profile",
        type: "behavioral",
        strength: 20,
        value: "Medium",
        metadata: { surface: "agent-panel", profileId: state.profileId },
      });
      previousProfileId.current = state.profileId;
    }
  }, [state.profileId]);

  useEffect(() => {
    if (state.incidentId && previousIncidentId.current !== state.incidentId) {
      trackStartupedEvent({
        name: "anvaya.agent.incident.selected",
        description: "User selected an incident for the agent",
        type: "engagement",
        strength: 30,
        value: "Medium",
        metadata: { surface: "agent-panel", incidentId: state.incidentId },
      });
      previousIncidentId.current = state.incidentId;
    }
  }, [state.incidentId]);

  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { state: appState } = useAnvaya();

  const { data: profilesData } = useQuery({
    queryKey: ["agent-profiles"],
    queryFn: () => AnvayaAPI.agentProfiles() as Promise<{ items: AgentProfile[] }>,
    staleTime: Infinity,
  });
  const { data: modelsData } = useQuery({
    queryKey: ["agent-models"],
    queryFn: () => AnvayaAPI.agentModels() as Promise<{ items: ModelConfig[] }>,
    staleTime: Infinity,
  });

  useEffect(() => {
    if (profilesData?.items?.length && !state.profiles.length) {
      dispatch({ type: "setProfiles", value: profilesData.items });
    }
  }, [profilesData, state.profiles.length]);

  useEffect(() => {
    if (modelsData?.items?.length && !state.models.length) {
      dispatch({ type: "setModels", value: modelsData.items });
    }
  }, [modelsData, state.models.length]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("anvaya.agent.closed-executions");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed)) {
          dispatch({ type: "setClosedExecutionIds", value: parsed });
        }
      } catch {}
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem("anvaya.agent.closed-executions", JSON.stringify(state.closedExecutionIds));
  }, [state.closedExecutionIds]);

  useEffect(() => {
    if (!state.profile && state.profiles.length) {
      const p = state.profiles.find((x) => x.id === state.profileId) || state.profiles[0];
      dispatch({ type: "setProfile", profile: p });
    }
    if (!state.model && state.models.length) {
      const nonLocal = state.models.filter((x) => x.provider !== "anvaya");
      const pool = nonLocal.length ? nonLocal : state.models;
      const m =
        pool.find((x) => x.id === state.profile?.model_name) ||
        pool.find((x) => x.availability === "available") ||
        pool.find((x) => x.availability === "configured") ||
        pool[0];
      dispatch({ type: "setModel", model: m });
    }
  }, [state.profiles, state.models, state.profile, state.model, state.profileId]);

  useEffect(() => {
    const fromPath = _extractIncidentIdFromPath(pathname);
    const fromQuery = _extractIncidentIdFromQuery();
    const id = fromPath || fromQuery || "";
    if (id && id !== state.incidentId) {
      dispatch({ type: "setIncidentId", value: id });
      if (!state.objective) {
        dispatch({ type: "setObjective", value: `Investigate ${id}` });
      }
    }

    const projectId = _extractProjectIdFromPath(pathname) || appState.activeProjectId || "";
    if (projectId !== state.projectId) {
      dispatch({ type: "setProjectId", value: projectId });
    }
  }, [pathname, state.incidentId, state.objective, state.projectId, appState.activeProjectId]);

  useEffect(() => {
    const build = state.build;
    if (!build?.navigateTo || build.navigateConsumed) return;
    if (build.status === "completed" || build.status === "failed") return;

    const target = build.navigateTo.startsWith("/")
      ? build.navigateTo
      : `/${build.navigateTo}`;

    if (pathname === target) {
      dispatch({ type: "setBuildNavigationConsumed", value: true });
      return;
    }

    router.push(`${target}?build=${build.executionId}`);
    dispatch({ type: "setBuildNavigationConsumed", value: true });
  }, [
    state.build,
    pathname,
    router,
  ]);

  const { data: executionsData } = useAgentExecutions(undefined, 5000);

  useEffect(() => {
    if (executionsData?.items) {
      dispatch({ type: "setExecutions", value: executionsData.items as AgentExecution[] });
    }
  }, [executionsData]);

  const applyContext = useCallback((ctx: AgentExecutionContext) => {
    dispatch({ type: "setReasoning", value: ctx.reasoning_summary || "", source: "execution_summary" });
    dispatch({ type: "setCurrentAction", value: ctx.current_action });
    dispatch({ type: "setPlan", value: ctx.plan || [] });
    dispatch({ type: "setObservations", value: ctx.observations || [] });
    if (ctx.status === "interrupted") {
      dispatch({ type: "setInterrupted", value: true });
    }
    dispatch({
      type: "setModelStatus",
      value: ctx.status === "running"
        ? "waiting"
        : ctx.status === "interrupted"
        ? "interrupted"
        : "idle",
    });
  }, []);

  const processLiveEvent = useCallback((event: AgentEvent) => {
    const p = event.payload || {};
    switch (event.type) {
      case "agent.reasoning_started":
        dispatch({ type: "setReasoning", value: "", source: "model" });
        dispatch({ type: "setModelStatus", value: "generating" });
        break;
      case "agent.reasoning_delta":
        dispatch({ type: "appendReasoning", value: String(p.delta || "") });
        dispatch({ type: "setModelStatus", value: "generating" });
        break;
      case "agent.reasoning_completed":
        dispatch({
          type: "setReasoning",
          value: String(p.summary || ""),
          source: String(p.source || "model"),
        });
        dispatch({ type: "setReasoningSource", value: String(p.source || "model") });
        dispatch({ type: "setModelStatus", value: "waiting" });
        break;
      case "agent.decision_started":
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: String(p.tool_name || event.tool_name || ""),
            label: String(event.label || p.tool_name || event.tool_name || ""),
            status: "running",
            step_index: Number(p.step_index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "running tool" });
        break;
      case "agent.tool_requested":
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: String(p.tool_name || event.tool_name || ""),
            label: String(p.label || event.label || p.tool_name || event.tool_name || ""),
            status: "requested",
            step_index: Number(p.step_index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "running tool" });
        break;
      case "agent.observation_created":
        dispatch({
          type: "appendObservation",
          value: {
            summary: String(p.summary || ""),
            facts: (p.facts as Record<string, unknown>) || {},
            source: String(p.source || event.provider || ""),
            step_index: Number(p.step_index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "waiting" });
        break;
      case "agent.plan_created":
        if (Array.isArray(p.plan)) {
          dispatch({ type: "setPlan", value: p.plan as AgentPlanStep[] });
        }
        dispatch({ type: "setModelStatus", value: "waiting" });
        break;
      case "agent.plan_updated":
        if (Array.isArray(p.plan)) {
          dispatch({ type: "setPlan", value: p.plan as AgentPlanStep[] });
        }
        dispatch({ type: "setModelStatus", value: "waiting" });
        break;
      case "agent.execution_interrupted":
        dispatch({ type: "setInterrupted", value: true, reason: String(p.reason || "") });
        dispatch({ type: "setModelStatus", value: "interrupted" });
        dispatch({ type: "setCurrentAction", value: null });
        break;
      case "agent.completed":
        dispatch({ type: "setModelStatus", value: "idle" });
        dispatch({ type: "setCurrentAction", value: null });
        break;
      case "agent.failed":
        dispatch({ type: "setModelStatus", value: "idle" });
        dispatch({ type: "setCurrentAction", value: null });
        break;
      case "agent.verification_started":
        dispatch({ type: "setModelStatus", value: "verifying" });
        break;
      case "agent.verification_completed": {
        const passed = Boolean(p.passed);
        dispatch({ type: "setModelStatus", value: passed ? "waiting" : "waiting" });
        dispatch({
          type: "appendObservation",
          value: {
            summary: `Verification ${passed ? "passed" : "failed"}: ${String(p.reason || "")}`,
            facts: {
              passed,
              missing: p.missing || [],
              contradictions: p.contradictions || [],
              confidence: p.confidence ?? 0,
            },
            source: "verification",
            step_index: -1,
          },
        });
        break;
      }
      case "artifact.progress":
        dispatch({ type: "setModelStatus", value: "running tool" });
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        break;
      case "artifact.saved":
        dispatch({ type: "setModelStatus", value: "waiting" });
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        break;
      case "agent.awaiting_input":
        dispatch({ type: "setModelStatus", value: "waiting" });
        dispatch({ type: "setCurrentAction", value: null });
        break;
      case "agent.observation":
        if (p.summary || p.observation) {
          dispatch({
            type: "appendObservation",
            value: {
              summary: String(p.summary || p.observation || event.label || ""),
              facts: p.observation ? { observation: p.observation } : {},
              source: String(event.provider || "agent"),
              step_index: -1,
            },
          });
        }
        break;
      case "generation.started":
      case "generation.analyzing":
      case "navigation.started":
      case "navigation.completed":
      case "artifact.queued":
      case "artifact.deleted":
      case "artifact.regenerating":
      case "artifact.generating":
      case "artifact.world_build_started":
      case "artifact.world_build_completed":
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        break;

      case "artifact.thinking": {
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        const stepName = String(p.name || event.label || "Artifact");
        dispatch({
          type: "setReasoning",
          value: String(p.purpose || ""),
          source: "build",
        });
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: "build",
            label: `Planning ${stepName}`,
            status: "thinking",
            step_index: Number(p.index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "thinking" });
        break;
      }

      case "artifact.creating": {
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        const stepName = String(p.name || event.label || "Artifact");
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: "build",
            label: `Creating ${stepName}`,
            status: "running",
            step_index: Number(p.index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "running tool" });
        break;
      }

      case "artifact.created": {
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        const stepName = String(p.name || event.label || "Artifact");
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: "build",
            label: `${stepName} created`,
            status: "running",
            step_index: Number(p.index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "running tool" });
        break;
      }

      case "artifact.attaching":
      case "artifact.completed": {
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        const stepName = String(p.name || event.label || "Artifact");
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: "build",
            label: event.type === "artifact.completed" ? `${stepName} complete` : `Connecting ${stepName}`,
            status: event.type === "artifact.completed" ? "completed" : "running",
            step_index: Number(p.index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "running tool" });
        break;
      }

      case "artifact.failed":
      case "artifact.retrying": {
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        const stepName = String(p.name || event.label || "Artifact");
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: "build",
            label: event.type === "artifact.failed" ? `${stepName} failed` : `Retrying ${stepName}`,
            status: event.type === "artifact.failed" ? "failed" : "running",
            step_index: Number(p.index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "running tool" });
        break;
      }

      case "element.thinking": {
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        dispatch({
          type: "setReasoning",
          value: String(p.reason || ""),
          source: "build",
        });
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: "build",
            label: `Preparing ${p.display || p.element_id || "element"}`,
            status: "thinking",
            step_index: Number(p.step_index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "thinking" });
        break;
      }

      case "element.mounted": {
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: "build",
            label: `${p.display || p.element_id || "Element"} mounted`,
            status: "completed",
            step_index: Number(p.step_index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "running tool" });
        break;
      }

      case "element.batch_mounted":
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: "build",
            label: "Batch of elements mounted",
            status: "completed",
            step_index: Number(p.step_index ?? -1),
          },
        });
        dispatch({ type: "setModelStatus", value: "running tool" });
        break;

      case "generation.finishing":
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        dispatch({
          type: "setCurrentAction",
          value: {
            tool_name: "build",
            label: "Finishing up",
            status: "running",
            step_index: -1,
          },
        });
        break;

      case "generation.completed": {
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        dispatch({ type: "setReasoning", value: "", source: "build" });
        dispatch({ type: "setCurrentAction", value: null });
        dispatch({ type: "setModelStatus", value: "idle" });
        break;
      }

      case "generation.failed": {
        dispatch({ type: "setBuild", value: (build) => applyBuildEvent(build, event) });
        dispatch({ type: "setReasoning", value: "Build failed", source: "build" });
        dispatch({ type: "setCurrentAction", value: null });
        dispatch({ type: "setModelStatus", value: "idle" });
        break;
      }
    }
  }, []);

  useEffect(() => {
    if (!state.executionId) return;
    if (stateRef.current.mode === "chat") return;

    let after = 0;
    const existing = stateRef.current.events.filter((e) => e.execution_id === state.executionId);
    if (existing.length) {
      after = Math.max(...existing.map((e) => e.sequence));
    }

    let closed = false;
    let source: EventSource | null = null;

    const connect = () => {
      source = new EventSource(
        `/api/backend/api/v1/agent/executions/${state.executionId}/stream?after=${after}`,
        { withCredentials: true }
      );

      source.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (!data || !data.type) return;
          const event = data as AgentEvent;

          const key = `${event.execution_id}:${event.sequence}`;
          if (stateRef.current.events.some((e) => `${e.execution_id}:${e.sequence}` === key)) return;

          processLiveEvent(event);
          dispatch({ type: "appendEvents", value: [event] });

          if (event.sequence > after) {
            after = event.sequence;
          }

          if (data.type === "agent.completed" || data.type === "agent.failed" || data.type === "agent.execution_interrupted") {
            source?.close();
            closed = true;
          }
        } catch {
        }
      };

      source.onerror = () => {
        if (!closed) {
          source?.close();
          setTimeout(() => {
            if (!closed) connect();
          }, 1000);
        }
      };
    };

    connect();

    return () => {
      closed = true;
      source?.close();
    };
  }, [state.executionId, processLiveEvent]);

  useEffect(() => {
    const executionEvents = state.events.filter((e) => e.execution_id === state.executionId);
    if (!executionEvents.length) return;
    const final = executionEvents[executionEvents.length - 1];

    if (final.type === "agent.completed") {
      dispatch({ type: "setExecuting", value: false });
      dispatch({ type: "setStatus", value: "completed" });
      dispatch({ type: "setModelStatus", value: "idle" });
      dispatch({ type: "setCurrentAction", value: null });
    } else if (final.type === "agent.failed") {
      dispatch({ type: "setExecuting", value: false });
      dispatch({ type: "setStatus", value: "failed" });
      dispatch({ type: "setModelStatus", value: "idle" });
      dispatch({ type: "setCurrentAction", value: null });
    } else if (final.type === "agent.execution_interrupted") {
      dispatch({ type: "setExecuting", value: false });
      dispatch({ type: "setStatus", value: "interrupted" });
      dispatch({ type: "setModelStatus", value: "interrupted" });
      dispatch({ type: "setCurrentAction", value: null });
    } else {
      dispatch({ type: "setStatus", value: "running" });
    }

    if ((final.type === "agent.completed" || final.type === "agent.failed") && state.projectId) {
      queryClient.invalidateQueries({ queryKey: ["projects", state.projectId] });
    }
    const hasArtifactSaved = executionEvents.some((e) => e.type === "artifact.saved");
    if (hasArtifactSaved && state.projectId) {
      queryClient.invalidateQueries({ queryKey: ["projects", state.projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects", state.projectId, "artifacts"] });
      queryClient.invalidateQueries({ queryKey: ["projects", state.projectId, "generations"] });
    }
  }, [state.events, state.executionId, state.projectId, queryClient]);

  const selectProfile = useCallback(
    (id: string) => {
      const p = state.profiles.find((x) => x.id === id);
      if (p) {
        dispatch({ type: "setProfile", profile: p });
        const m = state.models.find((x) => x.id === p.model_name) || state.model;
        if (m) dispatch({ type: "setModel", model: m });
      }
    },
    [state.profiles, state.models, state.model]
  );

  const start = useCallback(
    async (objective: string, incidentId?: string, executionId?: string) => {
      const current = stateRef.current;
      if (!executionId) {
        dispatch({ type: "resetEvents" });
      }
      dispatch({ type: "setExecuting", value: true });
      dispatch({ type: "setError", value: null });
      dispatch({ type: "setStatus", value: "running" });
      dispatch({ type: "setModelStatus", value: "waiting" });
      dispatch({ type: "setOpen", value: true });
      dispatch({ type: "setMode", value: "agentic" });
      try {
        const id = incidentId !== undefined ? incidentId : current.incidentId;
        const data = (await AnvayaAPI.agentExecute(
          objective,
          id || undefined,
          current.profileId,
          current.model?.id,
          current.projectId || undefined,
          executionId,
        )) as {
          execution_id: string;
          status: string;
          incident_id: string;
        };

        const [eventsData, ctxData] = await Promise.all([
          AnvayaAPI.agentEvents(data.execution_id).catch(() => null) as Promise<{ items: AgentEvent[] } | null>,
          AnvayaAPI.agentExecutionContext(data.execution_id).catch(() => null),
        ]);

        dispatch({ type: "setExecutionId", value: data.execution_id });
        dispatch({ type: "setIncidentId", value: data.incident_id || "" });
        dispatch({ type: "setStatus", value: data.status });

        if (eventsData?.items) {
          const existingIds = new Set(stateRef.current.events.map((e) => `${e.execution_id}:${e.sequence}`));
          const newEvents = eventsData.items.filter(
            (e) => !existingIds.has(`${e.execution_id}:${e.sequence}`)
          );
          if (newEvents.length) {
            dispatch({ type: "appendEvents", value: newEvents });
          }
        }
        if (ctxData) {
          applyContext(ctxData);
        }

        return true;
      } catch (err: any) {
        dispatch({ type: "setError", value: err?.message || "Failed to start" });
        dispatch({ type: "setExecuting", value: false });
        dispatch({ type: "setModelStatus", value: "idle" });
        return false;
      }
    },
    [applyContext]
  );

  const attachExecution = useCallback(async (executionId: string) => {
    if (!executionId) return false;
    // Subscribe the panel to an externally-created execution (e.g. a project-page
    // generation). Mode must switch before setExecutionId so the SSE effect
    // (which skips subscriptions in chat mode) connects, and the stream replays
    // the execution's events from sequence 0 so narration from the start shows.
    dispatch({ type: "setMode", value: "agentic" });
    dispatch({ type: "setExecuting", value: true });
    dispatch({ type: "setStatus", value: "running" });
    dispatch({ type: "setError", value: null });
    dispatch({ type: "setOpen", value: true });
    dispatch({ type: "setExecutionId", value: executionId });
    try {
      const eventsData = (await AnvayaAPI.agentEvents(executionId).catch(() => null)) as
        | { items: AgentEvent[] }
        | null;
      if (eventsData?.items) {
        const existingIds = new Set(
          stateRef.current.events.map((e) => `${e.execution_id}:${e.sequence}`)
        );
        const newEvents = eventsData.items.filter(
          (e) => !existingIds.has(`${e.execution_id}:${e.sequence}`)
        );
        if (newEvents.length) {
          dispatch({ type: "appendEvents", value: newEvents });
        }
      }
    } catch {
      // SSE subscription will still pick the stream up from sequence 0.
    }
    return true;
  }, []);

  const chat = useCallback(
    async (
      message: string,
      images: string[] = [],
      contextText: string = "",
      continueExecutionId?: string
    ) => {
      const current = stateRef.current;
      trackStartupedEvent({
        name: "anvaya.agent.chat.started",
        description: "User started an agent chat",
        type: "engagement",
        strength: 35,
        value: "Medium",
        metadata: {
          surface: "agent-panel",
          modelId: current.model?.id || "",
          hasImages: images.length > 0,
          hasContext: Boolean(contextText),
          continued: Boolean(continueExecutionId),
        },
      });
      dispatch({ type: "setExecuting", value: true });
      dispatch({ type: "setError", value: null });
      dispatch({ type: "setStatus", value: "running" });
      dispatch({ type: "setModelStatus", value: "generating" });
      dispatch({ type: "setOpen", value: true });
      dispatch({ type: "setMode", value: "chat" });
      try {
        const data = (await AnvayaAPI.agentChat(
          message,
          current.model?.id,
          images,
          contextText,
          current.projectId,
          [],
          continueExecutionId,
        )) as {
          execution_id: string;
          status: string;
          response: string;
        };
        dispatch({ type: "setExecutionId", value: data.execution_id });
        dispatch({ type: "setMode", value: "chat" });
        dispatch({ type: "setStatus", value: data.status });
        dispatch({ type: "setModelStatus", value: data.status === "failed" ? "idle" : "idle" });
        trackStartupedEvent({
          name: data.status === "failed" ? "anvaya.agent.chat.failed" : "anvaya.agent.chat.completed",
          description: data.status === "failed" ? "Agent chat failed" : "Agent chat completed",
          type: data.status === "failed" ? "behavioral" : "conversion",
          strength: data.status === "failed" ? 25 : 55,
          value: data.status === "failed" ? "Medium" : "High",
          metadata: { surface: "agent-panel", executionId: data.execution_id, status: data.status },
        });
      } catch (err: any) {
        trackStartupedEvent({
          name: "anvaya.agent.chat.failed",
          description: "Agent chat failed",
          type: "behavioral",
          strength: 25,
          value: "Medium",
          metadata: { surface: "agent-panel", phase: "request" },
        });
        dispatch({ type: "setError", value: err?.message || "Failed to send message" });
        dispatch({ type: "setExecuting", value: false });
        dispatch({ type: "setModelStatus", value: "idle" });
      }
    },
    []
  );

  const sendFollowUp = useCallback(
    async (message: string) => {
      if (!state.executionId) return false;
      trackStartupedEvent({
        name: "anvaya.agent.chat.followup.started",
        description: "User sent an agent follow-up",
        type: "engagement",
        strength: 30,
        value: "Medium",
        metadata: { surface: "agent-panel", executionId: state.executionId },
      });
      dispatch({ type: "setError", value: null });
      if (!state.executing) {
        dispatch({ type: "setExecuting", value: true });
        dispatch({ type: "setStatus", value: "running" });
      }
      dispatch({ type: "setModelStatus", value: "waiting" });

      const now = Date.now();
      const optimistic: AgentEvent = {
        id: -now,
        execution_id: state.executionId,
        sequence: -now,
        type: "chat.user",
        timestamp: new Date().toISOString(),
        payload: { message },
      };
      dispatch({ type: "appendEvents", value: [optimistic] });

      try {
        await AnvayaAPI.agentExecutionMessage(state.executionId, message);
        trackStartupedEvent({
          name: "anvaya.agent.chat.followup.completed",
          description: "Agent follow-up was accepted",
          type: "engagement",
          strength: 35,
          value: "Medium",
          metadata: { surface: "agent-panel", executionId: state.executionId },
        });
        return true;
      } catch (err: any) {
        trackStartupedEvent({
          name: "anvaya.agent.chat.followup.failed",
          description: "Agent follow-up failed",
          type: "behavioral",
          strength: 20,
          value: "Medium",
          metadata: { surface: "agent-panel", executionId: state.executionId },
        });
        dispatch({ type: "setError", value: err?.message || "Failed to send follow-up" });
        return false;
      }
    },
    [state.executionId, state.executing]
  );

  const cancelExecution = useCallback(async () => {
    if (!state.executionId) return;
    dispatch({ type: "setError", value: null });
    try {
      await AnvayaAPI.agentExecutionCancel(state.executionId);
      trackStartupedEvent({
        name: "anvaya.agent.execution.cancelled",
        description: "User cancelled an agent execution",
        type: "behavioral",
        strength: 25,
        value: "Medium",
        metadata: { surface: "agent-panel", executionId: state.executionId },
      });
      dispatch({ type: "setInterrupted", value: true, reason: "Cancelled by user" });
      dispatch({ type: "setExecuting", value: false });
      dispatch({ type: "setStatus", value: "interrupted" });
      dispatch({ type: "setModelStatus", value: "interrupted" });
      dispatch({ type: "setCurrentAction", value: null });
    } catch (err: any) {
      dispatch({ type: "setError", value: err?.message || "Failed to cancel execution" });
    }
  }, [state.executionId]);

  const chatStream = useCallback(
    async (
      message: string,
      images: string[] = [],
      contextText: string = "",
      continueExecutionId?: string
    ) => {
      const current = stateRef.current;
      trackStartupedEvent({
        name: "anvaya.agent.chat.started",
        description: "User started a streaming agent chat",
        type: "engagement",
        strength: 35,
        value: "Medium",
        metadata: {
          surface: "agent-panel",
          transport: "stream",
          modelId: current.model?.id || "",
          hasImages: images.length > 0,
          hasContext: Boolean(contextText),
          continued: Boolean(continueExecutionId),
        },
      });
      dispatch({ type: "setExecuting", value: true });
      dispatch({ type: "setError", value: null });
      dispatch({ type: "setStatus", value: "running" });
      dispatch({ type: "setOpen", value: true });
      dispatch({
        type: "setStreamingMessage",
        value: "",
        model: current.model?.display_name || current.model?.id || "model",
      });
      dispatch({ type: "setMode", value: "chat" });

      let executionId = "";
      let status: "running" | "completed" | "failed" | "interrupted" = "running";
      let completed = false;
      let eventSeq = 0;
      const makeEvent = (type: string, payload: Record<string, unknown>, extra?: Partial<AgentEvent>): AgentEvent => {
        const now = Date.now() + eventSeq++;
        return {
          execution_id: (payload.execution_id as string) || executionId || "pending",
          sequence: -now,
          type,
          timestamp: new Date().toISOString(),
          payload,
          ...extra,
        };
      };

      const abortController = new AbortController();
      const firstChunkTimeout = setTimeout(() => {
        abortController.abort();
      }, 60000);

      try {
        const response = await AnvayaAPI.agentChatStream(
          message,
          current.model?.id,
          images,
          contextText,
          current.projectId,
          [],
          continueExecutionId,
          abortController.signal
        );

        if (!response.ok) {
          const text = await response.text();
          trackStartupedEvent({
            name: "anvaya.agent.chat.failed",
            description: "Streaming agent chat failed to start",
            type: "behavioral",
            strength: 25,
            value: "Medium",
            metadata: { surface: "agent-panel", transport: "stream", phase: "start" },
          });
          dispatch({ type: "setError", value: text || "Failed to start chat stream" });
          return false;
        }

        if (!response.body) {
          trackStartupedEvent({
            name: "anvaya.agent.chat.failed",
            description: "Streaming agent chat returned no response stream",
            type: "behavioral",
            strength: 25,
            value: "Medium",
            metadata: { surface: "agent-panel", transport: "stream", phase: "response" },
          });
          dispatch({ type: "setError", value: "No response stream" });
          return false;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let done = false;

        while (!done) {
          const { value, done: readerDone } = await reader.read();
          done = readerDone || completed;
          if (value) {
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
              const trimmed = line.trim();
              if (!trimmed.startsWith("data:")) continue;
              const dataStr = trimmed.slice(5).trim();
              if (dataStr === "[DONE]") {
                done = true;
                break;
              }
              try {
                const data = JSON.parse(dataStr) as {
                  type: string;
                  payload: Record<string, unknown>;
                };
                if (data.payload?.execution_id && !executionId) {
                  executionId = data.payload.execution_id as string;
                  dispatch({ type: "setExecutionId", value: executionId });
                }

                if (data.type === "chat.user") {
                  clearTimeout(firstChunkTimeout);
                  dispatch({
                    type: "appendEvents",
                    value: [
                      makeEvent("chat.user", data.payload, {
                        label: message.slice(0, 120),
                        provider: (data.payload.provider as string) || "anvaya",
                      }),
                    ],
                  });
                } else if (data.type === "chat.assistant") {
                  clearTimeout(firstChunkTimeout);
                  if (data.payload?.streaming) {
                    dispatch({
                      type: "setStreamingMessage",
                      value: (data.payload?.message as string) || "",
                      model:
                        (data.payload?.model as string) ||
                        current.model?.display_name ||
                        "model",
                    });
                  } else {
                    dispatch({
                      type: "appendEvents",
                      value: [
                        makeEvent("chat.assistant", data.payload, {
                          label: ((data.payload?.message as string) || "").slice(0, 120) || "response",
                          provider: (data.payload.provider as string) || "anvaya",
                        }),
                      ],
                    });
                    dispatch({ type: "setStreamingMessage", value: "", model: "" });
                  }
                } else if (data.type === "agent.completed") {
                  status = "completed";
                  completed = true;
                  trackStartupedEvent({
                    name: "anvaya.agent.chat.completed",
                    description: "Streaming agent chat completed",
                    type: "conversion",
                    strength: 55,
                    value: "High",
                    metadata: { surface: "agent-panel", transport: "stream", executionId },
                  });
                  dispatch({
                    type: "appendEvents",
                    value: [
                      makeEvent("agent.completed", data.payload, {
                        label: "Chat complete",
                        provider: (data.payload.provider as string) || "anvaya",
                      }),
                    ],
                  });
                  dispatch({ type: "setModelStatus", value: "idle" });
                  dispatch({ type: "setCurrentAction", value: null });
                  dispatch({ type: "setStreamingMessage", value: "", model: "" });
                } else if (data.type === "agent.failed") {
                  status = "failed";
                  completed = true;
                  trackStartupedEvent({
                    name: "anvaya.agent.chat.failed",
                    description: "Streaming agent chat failed",
                    type: "behavioral",
                    strength: 25,
                    value: "Medium",
                    metadata: { surface: "agent-panel", transport: "stream", executionId },
                  });
                  dispatch({
                    type: "appendEvents",
                    value: [
                      makeEvent("agent.failed", data.payload, {
                        label: "Chat failed",
                        error_message: (data.payload.error_message as string) || "",
                        provider: (data.payload.provider as string) || "anvaya",
                      }),
                    ],
                  });
                  dispatch({ type: "setModelStatus", value: "idle" });
                  dispatch({ type: "setCurrentAction", value: null });
                  dispatch({ type: "setStreamingMessage", value: "", model: "" });
                } else if (data.type === "agent.execution_interrupted") {
                  status = "interrupted";
                  completed = true;
                  dispatch({
                    type: "appendEvents",
                    value: [
                      makeEvent("agent.execution_interrupted", data.payload, {
                        error_message: (data.payload.reason as string) || "",
                        provider: (data.payload.provider as string) || "anvaya",
                      }),
                    ],
                  });
                  dispatch({
                    type: "setInterrupted",
                    value: true,
                    reason: String(data.payload?.reason || ""),
                  });
                  dispatch({ type: "setModelStatus", value: "interrupted" });
                  dispatch({ type: "setCurrentAction", value: null });
                  dispatch({ type: "setStreamingMessage", value: "", model: "" });
                }
              } catch {
              }
            }
          }
        }

        if (executionId) {
          dispatch({ type: "setExecutionId", value: executionId });
          dispatch({ type: "setMode", value: "chat" });
          queryClient.invalidateQueries({ queryKey: ["agent-executions"] });
        }
        dispatch({ type: "setStreamingMessage", value: "", model: "" });

        dispatch({ type: "setStatus", value: status });
        return true;
      } catch (err: any) {
        trackStartupedEvent({
          name: "anvaya.agent.chat.failed",
          description: err?.name === "AbortError" ? "Streaming agent chat timed out" : "Streaming agent chat failed",
          type: "behavioral",
          strength: 25,
          value: "Medium",
          metadata: {
            surface: "agent-panel",
            transport: "stream",
            phase: err?.name === "AbortError" ? "timeout" : "stream",
          },
        });
        if (err?.name === "AbortError") {
          dispatch({
            type: "setError",
            value: "Model did not respond within 60s. It may not support chat or is overloaded. Try another model.",
          });
        } else {
          dispatch({
            type: "setError",
            value: err?.message || "Chat stream failed",
          });
        }
        dispatch({ type: "setStatus", value: "failed" });
        dispatch({ type: "setModelStatus", value: "idle" });
        return false;
      } finally {
        clearTimeout(firstChunkTimeout);
        dispatch({ type: "setExecuting", value: false });
      }
    },
    [queryClient]
  );

  const seed = useCallback(async () => {
    try {
      const data = await AnvayaAPI.agentSeedDemo();
      dispatch({ type: "setIncidentId", value: data.incident_id });
      dispatch({ type: "setObjective", value: `Investigate ${data.incident_id}` });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["agent-executions"] });
      return data.incident_id;
    } catch (err: any) {
      dispatch({ type: "setError", value: err?.message || "Failed to seed demo" });
      return undefined;
    }
  }, [queryClient]);

  const loadExecution = useCallback(
    async (execution: AgentExecution) => {
      trackStartupedEvent({
        name: "anvaya.agent.execution.selected",
        description: "User selected a previous agent execution",
        type: "behavioral",
        strength: 20,
        value: "Medium",
        metadata: { surface: "agent-panel", executionId: execution.execution_id },
      });
      dispatch({ type: "loadExecution", execution });
      try {
        const [eventsData, contextData] = await Promise.all([
          AnvayaAPI.agentEvents(execution.execution_id) as Promise<{ items: AgentEvent[] }>,
          AnvayaAPI.agentExecutionContext(execution.execution_id).catch(() => null),
        ]);
        dispatch({ type: "setEvents", value: eventsData.items || [] });
        if (contextData) {
          applyContext(contextData);
        }
      } catch (err: any) {
        dispatch({ type: "setError", value: err?.message || "Failed to load execution" });
      }
    },
    [applyContext]
  );

  const newConversation = useCallback(() => {
    trackStartupedEvent({
      name: "anvaya.agent.conversation.created",
      description: "User started a new agent conversation",
      type: "engagement",
      strength: 25,
      value: "Medium",
      metadata: { surface: "agent-panel" },
    });
    dispatch({ type: "resetEvents" });
    dispatch({ type: "setMode", value: "agentic" });
    dispatch({ type: "setStatus", value: "" });
    dispatch({ type: "setObjective", value: "" });
    dispatch({ type: "setContextText", value: "" });
    dispatch({ type: "setOpen", value: true });
  }, []);

  const value = useMemo(
    () => ({
      state,
      dispatch,
      start,
      attachExecution,
      chat,
      chatStream,
      sendFollowUp,
      cancelExecution,
      seed,
      selectProfile,
      loadExecution,
      newConversation,
      consoleWidth: state.open ? state.width : 0,
    }),
    [state, start, attachExecution, chat, chatStream, sendFollowUp, cancelExecution, seed, selectProfile, loadExecution, newConversation]
  );

  return <AgentCtx.Provider value={value}>{children}</AgentCtx.Provider>;
}

export function useAgent() {
  const ctx = useContext(AgentCtx);
  if (!ctx) throw new Error("useAgent outside AgentProvider");
  return ctx;
}

function _extractIncidentIdFromPath(pathname: string): string {
  const m = pathname.match(/(?:incident|incidents|replay|miss-replay|blastscope|ledger)\/([A-Z0-9-]+)/i);
  if (m) return m[1].toUpperCase();
  return "";
}

function _extractIncidentIdFromQuery(): string {
  if (typeof window === "undefined") return "";
  const params = new URLSearchParams(window.location.search);
  return (params.get("incident_id") || "").toUpperCase();
}

function _extractProjectIdFromPath(pathname: string): string {
  const m = pathname.match(/\/projects\/([A-Z0-9\-]+)/i);
  return m ? m[1].toUpperCase() : "";
}


