"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

const ROOT_BASE = API_BASE.replace(/\/api\/v1\/?$/, "");

class APIError extends Error {
  constructor(
    public method: string,
    public path: string,
    public status: number,
    public statusText: string,
    public detail?: unknown,
    message?: string,
  ) {
    super(
      message ||
        `API request failed: ${method} ${path}\n${status} ${statusText}${
          detail ? `\ndetail: ${JSON.stringify(detail)}` : ""
        }`,
    );
    this.name = "APIError";
  }
}

async function apiFetch(path: string, options?: RequestInit, base: string = API_BASE): Promise<unknown> {
  const url = `${base}${path}`;
  const method = (options?.method || "GET").toUpperCase();

  const isJsonString = options?.body != null && typeof options?.body === "string";
  const headers: Record<string, string> = {};
  if (isJsonString) {
    headers["Content-Type"] = "application/json";
  }
  if (options?.headers) {
    Object.assign(headers, options.headers);
  }

  const res = await fetch(url, {
    ...options,
    credentials: "include",
    headers,
  });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text().catch(() => undefined);
    }
    throw new APIError(method, path, res.status, res.statusText, detail);
  }
  return res.json();
}

export const AnvayaAPI = {
  health: () => apiFetch("/health", undefined, ROOT_BASE),

  incidents: () => apiFetch("/incidents"),
  incident: (id: string) => apiFetch(`/incidents/${id}`),
  createIncident: (data: Record<string, unknown>) =>
    apiFetch("/incidents", { method: "POST", body: JSON.stringify(data) }),
  transitionIncident: (id: string, status: string) =>
    apiFetch(`/incidents/${id}/transition?new_status=${status}`, { method: "POST" }),

  telemetry: (params?: string) => apiFetch(`/telemetry${params || ""}`),

  rules: () => apiFetch("/rules"),
  rule: (id: string) => apiFetch(`/rules/${id}`),
  createRule: (data: Record<string, unknown>) =>
    apiFetch("/rules", { method: "POST", body: JSON.stringify(data) }),

  detections: () => apiFetch("/detections"),
  detection: (id: string) => apiFetch(`/detections/${id}`),

  replay: (incidentId: string) =>
    apiFetch(`/sentinel/replay/${incidentId}`, { method: "POST" }),
  fullCycle: (incidentId: string) =>
    apiFetch(`/sentinel/full-cycle/${incidentId}`, { method: "POST" }),

  blastscope: (incidentId: string) =>
    apiFetch(`/blastscope/run/${incidentId}`, { method: "POST" }),

  whatif: (incidentId: string, changes: Record<string, unknown>) =>
    apiFetch(`/whatif/analyze/${incidentId}`, {
      method: "POST",
      body: JSON.stringify(changes),
    }),

  audit: () => apiFetch("/audit"),
  auditVerify: () => apiFetch("/audit/verify"),

  metrics: () => apiFetch("/metrics"),
  engines: (stage: string = "after") => apiFetch(`/metrics/engines?stage=${stage}`),
  trophies: () => apiFetch("/metrics/trophies"),

  organizations: () => apiFetch("/organizations"),
  organization: (id: string) => apiFetch(`/organizations/${id}`),
  updateOrganization: (id: string, data: Record<string, unknown>) =>
    apiFetch(`/organizations/${id}`, { method: "PUT", body: JSON.stringify(data) }),

  projects: () => apiFetch("/projects"),
  createProject: (data: Record<string, unknown>) =>
    apiFetch("/projects", { method: "POST", body: JSON.stringify(data) }),
  project: (id: string) => apiFetch(`/projects/${id}`),

  projectDatasets: (projectId: string) => apiFetch(`/projects/${projectId}/datasets`),
  createDataset: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return apiFetch(`/projects/${projectId}/datasets`, {
      method: "POST",
      body: form,
    });
  },

  projectGenerations: (projectId: string) => apiFetch(`/projects/${projectId}/generations`),
  createGeneration: (projectId: string, data: Record<string, unknown>) =>
    apiFetch(`/projects/${projectId}/generate`, { method: "POST", body: JSON.stringify(data) }),
  projectOrbits: (projectId: string) => apiFetch(`/projects/${projectId}/orbits`),
  projectArtifactLatest: (projectId: string, artifactType: string) =>
    apiFetch(`/projects/${projectId}/${artifactType}/latest`) as Promise<{ payload: Record<string, unknown> | null }>,
  projectArtifacts: (projectId: string, artifactType: string) =>
    apiFetch(`/projects/${projectId}/${artifactType}`),
  projectArtifact: (projectId: string, artifactType: string, artifactId: string) =>
    apiFetch(`/projects/${projectId}/${artifactType}/${artifactId}`),

  demo: () => apiFetch("/demo/run", { method: "POST" }),

  graph: (incidentId: string) => apiFetch(`/graph/${incidentId}`),
  segments: () => apiFetch("/graph/segments"),
  reachability: () => apiFetch("/graph/reachability"),

  ecosystem: (mode: string = "CONTAIN", step: number = 0, projectId?: string) =>
    apiFetch(
      `/simulation/ecosystem?mode=${mode}&step=${step}${projectId ? `&project_id=${projectId}` : ""}`
    ),

  blastscopeGallery: () => apiFetch("/blastscope/gallery"),

  agentTools: () => apiFetch("/agent/tools"),
  agentValidate: (tool: string, data: Record<string, unknown>) =>
    apiFetch(`/agent/tools/${tool}/validate`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  agentExecute: (objective: string, incidentId?: string, profileId?: string, modelId?: string, projectId?: string, executionId?: string) =>
    apiFetch("/agent/execute?background=true", {
      method: "POST",
      body: JSON.stringify({
        objective,
        incident_id: incidentId,
        profile_id: profileId,
        model_id: modelId,
        project_id: projectId,
        execution_id: executionId,
      }),
    }),
  tavilyLookup: (indicator: string, queryContext?: string, incidentId?: string) =>
    apiFetch("/tavily/search", {
      method: "POST",
      body: JSON.stringify({
        indicator,
        query_context: queryContext,
        incident_id: incidentId,
      }),
    }) as Promise<{
      indicator?: string;
      source?: string;
      provider?: string;
      records?: Array<{ title?: string; url?: string; summary?: string; relevance?: number }>;
      note?: string;
      fallback_used?: boolean;
      fallback_reason?: string;
    }>,
  n8nTrigger: (workflow: string, incidentId: string, payload?: Record<string, unknown>) =>
    apiFetch("/agent/execute?background=true", {
      method: "POST",
      body: JSON.stringify({
        objective: `Trigger n8n workflow ${workflow} for incident ${incidentId}`,
        incident_id: incidentId,
        payload,
      }),
    }),

  agentChat: (
    message: string,
    modelId?: string,
    images?: string[],
    contextText?: string,
    projectId?: string,
    conversation?: Array<{ role: string; content: string }>,
    executionId?: string,
  ) =>
    apiFetch("/agent/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        model_id: modelId,
        images: images || [],
        context_text: contextText || "",
        project_id: projectId || "",
        conversation: conversation || [],
        execution_id: executionId || "",
      }),
    }),
  agentChatStream: (
    message: string,
    modelId?: string,
    images?: string[],
    contextText?: string,
    projectId?: string,
    conversation?: Array<{ role: string; content: string }>,
    executionId?: string,
    signal?: AbortSignal,
  ) =>
    fetch(`${API_BASE}/agent/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        message,
        model_id: modelId,
        images: images || [],
        context_text: contextText || "",
        project_id: projectId || "",
        conversation: conversation || [],
        execution_id: executionId || "",
      }),
      signal,
    }),
  agentProfiles: () => apiFetch("/agent/profiles"),
  agentModels: () => apiFetch("/agent/models"),
  agentProviders: () => apiFetch("/agent/providers"),
  agentExecutions: (incidentId?: string) =>
    apiFetch(`/agent/executions${incidentId ? `?incident_id=${incidentId}` : ""}`),
  agentExecution: (id: string) => apiFetch(`/agent/executions/${id}`),
  agentEvents: (id: string, after: number = 0) =>
    apiFetch(`/agent/executions/${id}/events?after=${after}`),
  agentExecutionMessage: (id: string, message: string) =>
    apiFetch(`/agent/executions/${id}/message`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  agentExecutionCancel: (id: string) =>
    apiFetch(`/agent/executions/${id}/cancel`, { method: "POST" }),
  agentExecutionContext: (id: string) =>
    apiFetch(`/agent/executions/${id}/context`) as Promise<AgentExecutionContext>,
  agentExecutionStream: (id: string, after: number = 0, signal?: AbortSignal) =>
    fetch(`${API_BASE}/agent/executions/${id}/stream?after=${after}`, {
      credentials: "include",
      signal,
    }),
  agentSeedDemo: () =>
    apiFetch("/agent/seed", { method: "POST" }) as Promise<{
      incident_id: string;
      scenario_id: string;
      background_events: number;
      attack_events: number;
    }>,

  subagentProfiles: () => apiFetch("/agent/subagents/profiles"),
  subagents: (parentExecutionId?: string) =>
    apiFetch(`/agent/subagents${parentExecutionId ? `?parent_execution_id=${parentExecutionId}` : ""}`),
  subagent: (id: string) => apiFetch(`/agent/subagents/${id}`),
  spawnSubagent: (data: Record<string, unknown>) =>
    apiFetch("/agent/subagents", { method: "POST", body: JSON.stringify(data) }),
  cancelSubagent: (id: string) => apiFetch(`/agent/subagents/${id}/cancel`, { method: "POST" }),
  resumeSubagent: (id: string, task?: string) =>
    apiFetch(`/agent/subagents/${id}/resume`, {
      method: "POST",
      body: JSON.stringify(task ? { task } : {}),
    }),
  executionSubagents: (executionId: string) => apiFetch(`/agent/executions/${executionId}/subagents`),
  createBuildSession: (projectId: string, data: { prompt?: string; target?: string; targets?: string[]; dataset_id?: string }) =>
    apiFetch(`/projects/${projectId}/build`, { method: "POST", body: JSON.stringify(data) }),
  generationArtifacts: (projectId: string, generationId: string) =>
    apiFetch(`/projects/${projectId}/generations/${generationId}/artifacts`),
};

export function useMetrics(refetchInterval?: number) {
  return useQuery({
    queryKey: ["metrics"],
    queryFn: () => AnvayaAPI.metrics() as Promise<Record<string, unknown>>,
    refetchInterval: refetchInterval || 3000,
  });
}

export function useIncidents(refetchInterval?: number) {
  return useQuery({
    queryKey: ["incidents"],
    queryFn: () => AnvayaAPI.incidents() as Promise<{ items: unknown[] }>,
    refetchInterval: refetchInterval || 3000,
  });
}

export function useIncident(id: string) {
  return useQuery({
    queryKey: ["incident", id],
    queryFn: () => AnvayaAPI.incident(id) as Promise<Record<string, unknown>>,
    enabled: !!id,
  });
}

export function useRules() {
  return useQuery({
    queryKey: ["rules"],
    queryFn: () => AnvayaAPI.rules() as Promise<{ items: unknown[] }>,
  });
}

export function useRule(id: string) {
  return useQuery({
    queryKey: ["rule", id],
    queryFn: () => AnvayaAPI.rule(id) as Promise<Record<string, unknown>>,
    enabled: !!id,
  });
}

export function useAuditRecords() {
  return useQuery({
    queryKey: ["audit"],
    queryFn: () => AnvayaAPI.audit() as Promise<{ items: unknown[] }>,
  });
}

export function useGraph(incidentId: string) {
  return useQuery({
    queryKey: ["graph", incidentId],
    queryFn: () => AnvayaAPI.graph(incidentId) as Promise<Record<string, unknown>>,
    enabled: !!incidentId,
  });
}

export function useEngines(stage: string = "after") {
  return useQuery({
    queryKey: ["engines", stage],
    queryFn: () => AnvayaAPI.engines(stage) as Promise<Record<string, unknown>>,
  });
}

export function useEcosystem(mode: string = "CONTAIN", step: number = 0, projectId?: string) {
  return useQuery({
    queryKey: ["ecosystem", mode, step, projectId || ""],
    queryFn: () => AnvayaAPI.ecosystem(mode, step, projectId) as Promise<Record<string, unknown>>,
    placeholderData: keepPreviousData,
    enabled: !!projectId,
  });
}

export function useSegments() {
  return useQuery({
    queryKey: ["segments"],
    queryFn: () => AnvayaAPI.segments() as Promise<{ items: unknown[] }>,
  });
}

export function useReachability() {
  return useQuery({
    queryKey: ["reachability"],
    queryFn: () => AnvayaAPI.reachability() as Promise<{ items: unknown[] }>,
  });
}

export function useAgentExecutions(incidentId?: string, refetchInterval?: number) {
  return useQuery({
    queryKey: ["agent-executions", incidentId || ""],
    queryFn: () => AnvayaAPI.agentExecutions(incidentId) as Promise<{ items: unknown[]; total: number }>,
    refetchInterval: refetchInterval || 5000,
  });
}

export function useTrophies() {
  return useQuery({
    queryKey: ["trophies"],
    queryFn: () => AnvayaAPI.trophies() as Promise<{ items: unknown[] }>,
  });
}

export function useBlastscopeGallery() {
  return useQuery({
    queryKey: ["blastscope-gallery"],
    queryFn: () => AnvayaAPI.blastscopeGallery() as Promise<{ items: unknown[] }>,
  });
}

export function useAgentTools() {
  return useQuery({
    queryKey: ["agent-tools"],
    queryFn: () => AnvayaAPI.agentTools() as Promise<{ items: unknown[] }>,
  });
}

export function useAgentProviders(refetchInterval?: number) {
  return useQuery({
    queryKey: ["agent-providers"],
    queryFn: () => AnvayaAPI.agentProviders() as Promise<{ items: ProviderStatus[] }>,
    refetchInterval: refetchInterval || 10000,
  });
}

export type ProviderStatus = {
  name: string;
  provider: string;
  configured: boolean;
  healthy: boolean;
  availability: string;
  fallback_message?: string;
  kind?: string;
};

export type AgentEvent = {
  id?: number;
  execution_id: string;
  sequence: number;
  type: string;
  timestamp: string;
  tool_call_id?: string;
  tool_name?: string;
  provider?: string;
  status?: string;
  label?: string;
  payload?: Record<string, unknown>;
  artifact_ref?: string;
  artifact_type?: string;
  error_code?: string;
  error_message?: string;
  fallback_reason?: string;
};

export type AgentPlanStep = {
  tool: string;
  label: string;
  status: string;
  result_summary?: string;
  artifact_count?: number;
};

export type AgentObservation = {
  summary: string;
  facts: Record<string, unknown>;
  source: string;
  step_index: number;
};

export type AgentExecutionMessage = {
  role: string;
  content: string;
  timestamp: string;
};

export type AgentExecutionContext = {
  execution_id: string;
  objective: string;
  incident_id?: string;
  project_id?: string;
  plan: AgentPlanStep[];
  observations: AgentObservation[];
  messages: AgentExecutionMessage[];
  reasoning_summary: string;
  current_action: {
    tool_name: string;
    label: string;
    status: string;
    step_index: number;
  } | null;
  model: string;
  provider: string;
  status: string;
};

export type SubagentProfile = {
  id: string;
  name: string;
  display_name: string;
  description: string;
  icon: string;
  accent: string;
  model: string;
  allowed_tools: string[];
  preferred_tools: string[];
  fallback_tools: string[];
  confirmation_policy: string;
  max_nesting: number;
  status: string;
};

export type SubagentExecution = {
  subagent_id: string;
  parent_execution_id: string;
  child_execution_id?: string;
  profile_id: string;
  title: string;
  task: string;
  mode: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  duration_ms?: number;
  result_summary?: string;
  error_message?: string;
  tool_calls_count: number;
  nesting_depth: number;
};

export function useAgentEvents(executionId?: string, refetchInterval?: number) {
  return useQuery({
    queryKey: ["agent-events", executionId],
    queryFn: async () => {
      if (!executionId) return { items: [] as AgentEvent[], count: 0, after: 0 };
      const data = (await AnvayaAPI.agentEvents(executionId)) as {
        items: AgentEvent[];
        count: number;
        after: number;
      };
      return data;
    },
    enabled: !!executionId,
    refetchInterval: refetchInterval || 3000,
  });
}

export function useSubagentProfiles() {
  return useQuery({
    queryKey: ["subagent-profiles"],
    queryFn: () => AnvayaAPI.subagentProfiles() as Promise<{ items: SubagentProfile[] }>,
    staleTime: Infinity,
  });
}

export function useSubagents(parentExecutionId?: string, refetchInterval?: number) {
  return useQuery({
    queryKey: ["subagents", parentExecutionId || ""],
    queryFn: () =>
      AnvayaAPI.subagents(parentExecutionId) as Promise<{ items: SubagentExecution[]; total: number }>,
    enabled: !!parentExecutionId,
    refetchInterval: refetchInterval || 3000,
    placeholderData: keepPreviousData,
  });
}

export function useOrganizations(enabled = true) {
  return useQuery({
    queryKey: ["organizations"],
    queryFn: () => AnvayaAPI.organizations() as Promise<{ items: Organization[] }>,
    enabled,
  });
}

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: () => AnvayaAPI.projects() as Promise<{ items: Project[] }>,
  });
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId],
    queryFn: () => AnvayaAPI.project(projectId) as Promise<Project>,
    enabled: !!projectId,
  });
}

export function useProjectDatasets(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "datasets"],
    queryFn: () => AnvayaAPI.projectDatasets(projectId) as Promise<{ items: Dataset[] }>,
    enabled: !!projectId,
  });
}

export function useProjectGenerations(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "generations"],
    queryFn: () => AnvayaAPI.projectGenerations(projectId) as Promise<{ items: Generation[] }>,
    enabled: !!projectId,
  });
}

export function useProjectOrbits(projectId: string) {
  return useQuery({
    queryKey: ["projects", projectId, "orbits"],
    queryFn: () => AnvayaAPI.projectOrbits(projectId) as Promise<{ payload: Record<string, unknown> | null }>,
    enabled: !!projectId,
  });
}

export function useProjectArtifacts(projectId: string, artifactType: string) {
  return useQuery({
    queryKey: ["projects", projectId, "artifacts", artifactType],
    queryFn: () =>
      AnvayaAPI.projectArtifacts(projectId, artifactType) as Promise<{
        items: Array<{ artifact_id: string; payload: Record<string, unknown> }>;
      }>,
    enabled: !!projectId && !!artifactType,
  });
}

export function useProjectArtifactLatest(projectId: string, artifactType: string) {
  return useQuery({
    queryKey: ["projects", projectId, "artifacts", artifactType, "latest"],
    queryFn: () => AnvayaAPI.projectArtifactLatest(projectId, artifactType),
    enabled: !!projectId && !!artifactType,
    refetchInterval: 3000,
  });
}

export type Organization = {
  id: string;
  name: string;
  slug: string;
  logo: string | null;
  metadata: Record<string, unknown> | null;
  role: string;
};

export type Project = {
  project_id: string;
  organization_id: string;
  name: string;
  description: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  datasets?: Dataset[];
  artifact_counts?: Record<string, number>;
};

export type Dataset = {
  dataset_id: string;
  filename: string;
  format: string;
  size: number;
  checksum: string;
  status: string;
  profile_json: string;
  created_at: string;
};

export type Generation = {
  generation_id: string;
  requested_artifacts_json: string;
  created_artifacts_json: string;
  status: string;
  dataset_id: string;
  created_at: string;
};

export function connectExecutionSSE(
  executionId: string,
  afterSequence: number,
  onEvent: (event: AgentEvent) => void,
  onError?: (error: Event) => void,
): { close: () => void } {
  const url = `${API_BASE}/agent/executions/${executionId}/stream?after=${afterSequence}`;
  const source = new EventSource(url, { withCredentials: true });

  source.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data);
      if (data && data.type) {
        onEvent(data as AgentEvent);
      }
    } catch {
    }
  };

  source.onerror = (err) => {
    onError?.(err);
  };

  return {
    close: () => {
      source.close();
    },
  };
}
