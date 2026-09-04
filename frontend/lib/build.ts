"use client";

import { useMemo } from "react";

export type BuildStatus = "idle" | "running" | "completed" | "failed";

export interface BuildElement {
  id: string;
  stepIndex: number;
  stepId: string;
  elementId: string;
  index: number;
  total: number;
  reason: string;
  display?: string;
  data?: unknown;
  mounted: boolean;
}

export interface ArtifactBuildItem {
  id: string;
  index: number;
  artifactType: string;
  targetArtifactType: string;
  name: string;
  purpose: string;
  building: string;
  status: string;
  route: string;
  stepId: string;
  error?: string;
}

export interface ArtifactBuildState {
  executionId: string;
  prompt: string;
  target: string;
  status: BuildStatus;
  currentIndex: number;
  totalArtifacts: number;
  activeName: string;
  activePurpose: string;
  activeBuilding: string;
  activeLiveReason: string;
  activeStatus: string;
  activeElementReason: string | null;
  activeElementId: string | null;
  artifacts: ArtifactBuildItem[];
  elements: BuildElement[];
  navigateTo: string | null;
  navigateConsumed: boolean;
  phase: string;
}

export type BuildEvent = {
  execution_id?: string;
  type: string;
  payload?: Record<string, unknown>;
  label?: string;
};

export function initBuildState(
  executionId: string,
  prompt: string = "",
  target: string = "",
  totalArtifacts: number = 0
): ArtifactBuildState {
  return {
    executionId,
    prompt: prompt || "",
    target: target || "",
    status: "running",
    currentIndex: 0,
    totalArtifacts,
    activeName: "",
    activePurpose: "",
    activeBuilding: "",
    activeLiveReason: "",
    activeStatus: "queued",
    activeElementReason: null,
    activeElementId: null,
    artifacts: [],
    elements: [],
    navigateTo: null,
    navigateConsumed: false,
    phase: "Build started",
  };
}

function artifactStatusFromEvent(eventType: string): string {
  switch (eventType) {
    case "artifact.queued":
      return "queued";
    case "artifact.thinking":
      return "thinking";
    case "artifact.creating":
      return "creating";
    case "artifact.created":
      return "created";
    case "artifact.attaching":
      return "connecting";
    case "artifact.completed":
      return "complete";
    case "artifact.failed":
      return "failed";
    case "artifact.retrying":
      return "retrying";
    default:
      return "running";
  }
}

function makeArtifactItem(
  payload: Record<string, unknown>,
  eventType: string
): ArtifactBuildItem {
  const index = typeof payload.index === "number" ? payload.index : 0;
  const artifactType = String(payload.artifact_type || "");
  const targetArtifactType = String(payload.target_artifact_type || "");
  const name = String(payload.name || artifactType || "Artifact");
  const building = String(payload.building || payload.why || "");
  return {
    id: `${index}-${artifactType || name}`,
    index,
    artifactType,
    targetArtifactType,
    name,
    purpose: String(payload.purpose || ""),
    building,
    status: artifactStatusFromEvent(eventType),
    route: String(payload.route || ""),
    stepId: String(payload.step_id || `${targetArtifactType}-${artifactType}-${index}`),
    error: typeof payload.error === "string" ? payload.error : undefined,
  };
}

function upsertArtifact(
  artifacts: ArtifactBuildItem[],
  item: ArtifactBuildItem
): ArtifactBuildItem[] {
  const exists = artifacts.find((a) => a.index === item.index);
  if (exists) {
    return artifacts.map((a) =>
      a.index === item.index ? { ...a, ...item } : a
    );
  }
  return [...artifacts, item];
}

function upsertElement(
  elements: BuildElement[],
  next: BuildElement
): BuildElement[] {
  const exists = elements.find((e) => e.id === next.id);
  if (exists) {
    return elements.map((e) => (e.id === next.id ? { ...e, ...next } : e));
  }
  return [...elements, next];
}

function normalizeElementPayload(
  data: unknown
): Record<string, unknown> | undefined {
  if (data === null || data === undefined) return undefined;
  if (typeof data === "object") return data as Record<string, unknown>;
  return { value: data };
}

export function buildMountedElements<T>(
  build: ArtifactBuildState | null
): T[] {
  if (!build) return [];
  return build.elements
    .filter(
      (e): e is BuildElement & { data: Record<string, unknown> } =>
        e.mounted && e.data !== null && e.data !== undefined && typeof e.data === "object"
    )
    .map((e) => e.data as T);
}

export function activeBuildTarget(build: ArtifactBuildState | null): string {
  if (!build) return "";
  const current = build.artifacts.find((a) => a.index === build.currentIndex);
  return current?.targetArtifactType || build.target || "";
}

export function useArtifactSource<T>(
  build: ArtifactBuildState | null,
  payloadArray: T[] | undefined | null,
  isLoading: boolean,
  isError: boolean,
  artifactType: string,
  filter?: (value: unknown) => value is T
) {
  return useMemo(() => {
    const activeTarget = activeBuildTarget(build);
    const isBuilding = Boolean(
      build &&
        build.status !== "completed" &&
        build.status !== "failed" &&
        (!activeTarget || activeTarget === artifactType)
    );
    const mounted = buildMountedElements<Record<string, unknown>>(build);
    const mountedItems: T[] = filter
      ? (mounted.filter(filter) as T[])
      : (mounted as unknown as T[]);
    const payloadReady =
      !isBuilding &&
      !isLoading &&
      !isError &&
      Array.isArray(payloadArray) &&
      payloadArray.length >= mountedItems.length;
    const data: T[] = payloadReady ? payloadArray : mountedItems;
    return { data, isBuilding };
  }, [build, payloadArray, isLoading, isError, filter, artifactType]);
}

export function applyBuildEvent(
  state: ArtifactBuildState | null,
  event: BuildEvent
): Partial<ArtifactBuildState> {
  const p = (event.payload || {}) as Record<string, unknown>;
  const eventType = event.type;

  if (!state) {
    if (eventType === "generation.started" || eventType === "generation.analyzing") {
      return initBuildState(
        String(event.execution_id || p.execution_id || ""),
        String(p.prompt || ""),
        String(p.target || ""),
        typeof p.manifest_length === "number" ? p.manifest_length : 0
      );
    }
    return {};
  }

  if (eventType === "generation.started") {
    return initBuildState(
      state.executionId,
      p.prompt ? String(p.prompt) : state.prompt,
      p.target ? String(p.target) : state.target,
      typeof p.manifest_length === "number" ? p.manifest_length : state.totalArtifacts
    );
  }

  if (eventType === "generation.analyzing") {
    const target = p.target ? String(p.target) : state.target;
    return {
      target,
      status: "running",
      phase: `Planning ${target}...`,
      totalArtifacts:
        typeof p.manifest_length === "number"
          ? p.manifest_length
          : state.totalArtifacts,
    };
  }

  if (eventType === "artifact.world_build_started") {
    return { phase: "Building world model..." };
  }

  if (eventType === "artifact.world_build_completed") {
    return {
      phase: `World model ready · ${p.entities ?? "—"} entities · ${p.events ?? "—"} events`,
    };
  }

  if (eventType === "artifact.generating") {
    const target = String(p.artifact_type || state.target);
    return {
      activeName: target,
      activePurpose: `Generating ${target}`,
      activeBuilding: `Building the ${target} artifact`,
      activeStatus: "generating",
      phase: `Generating ${target}...`,
    };
  }

  if (eventType === "artifact.saved") {
    const target = String(p.artifact_type || state.target);
    return {
      activeName: target,
      activePurpose: `Generated ${target}`,
      activeBuilding: "",
      activeStatus: "saved",
      phase: `${target} generated`,
    };
  }

  if (eventType === "artifact.deleted" || eventType === "artifact.regenerating") {
    return {
      phase: event.label || eventType,
      activeStatus: "running",
    };
  }

  if (eventType === "navigation.started" || eventType === "navigation.completed") {
    const route = typeof p.route === "string" ? p.route : null;
    const update: Partial<ArtifactBuildState> = {
      navigateTo: route,
      status: "running",
      navigateConsumed:
        eventType === "navigation.started" ? false : state.navigateConsumed,
    };
    if (eventType === "navigation.started") {
      update.phase = event.label || `Opening ${state.target} workspace`;
    } else {
      update.phase = event.label || `${state.target} workspace ready`;
    }
    return update;
  }

  if (
    eventType.startsWith("artifact.") &&
    eventType !== "artifact.progress" &&
    eventType !== "artifact.saved" &&
    eventType !== "artifact.world_build_started" &&
    eventType !== "artifact.world_build_completed" &&
    eventType !== "artifact.generating" &&
    eventType !== "artifact.deleted" &&
    eventType !== "artifact.regenerating"
  ) {
    const item = makeArtifactItem(p, eventType);
    const nextArtifacts = upsertArtifact(state.artifacts, item);
    let update: Partial<ArtifactBuildState> = { artifacts: nextArtifacts };

    if (eventType !== "artifact.completed" && eventType !== "artifact.failed") {
      update = {
        ...update,
        currentIndex: item.index,
        activeName: item.name,
        activePurpose: item.purpose,
        activeBuilding: item.building,
        activeLiveReason:
          eventType === "artifact.queued"
            ? ""
            : typeof p.live_reason === "string"
              ? p.live_reason
              : state.activeLiveReason,
        activeStatus: item.status,
        activeElementReason: null,
        activeElementId: null,
      };
    }

    if (eventType === "artifact.completed") {
      const completed = nextArtifacts.filter((a) => a.status === "complete").length;
      const total = state.totalArtifacts || nextArtifacts.length;
      update = {
        ...update,
        currentIndex: Math.min(item.index + 1, Math.max(0, total - 1)),
        phase: `${item.name} complete`,
      };
      if (completed >= total && total > 0) {
        update.status = "completed";
        update.activeName = "";
        update.activePurpose = "";
        update.activeBuilding = "";
        update.activeLiveReason = "";
        update.activeStatus = "complete";
      }
    }

    if (eventType === "artifact.failed") {
      update = {
        ...update,
        phase: `${item.name} failed`,
        activeStatus: "failed",
      };
    }

    return update;
  }

  if (eventType === "artifact.progress") {
    const label = String(p.label || event.label || "Building...");
    const artifactType = String(p.artifact_type || state.target);
    return {
      activeName: artifactType,
      activePurpose: label,
      activeBuilding: label,
      activeStatus: String(p.status || "running"),
      phase: label,
    };
  }

  if (eventType === "element.thinking") {
    const stepIndex =
      typeof p.step_index === "number" ? p.step_index : state.currentIndex;
    const index =
      typeof p.index === "number" ? p.index : state.elements.length;
    const total =
      typeof p.total === "number" ? p.total : state.elements.length + 1;
    const elementId = String(p.element_id || `${stepIndex}-${index}`);
    const id = `${state.executionId}-element-${elementId}`;
    const el: BuildElement = {
      id,
      stepIndex,
      stepId: String(p.step_id || `${state.target}-${stepIndex}`),
      elementId,
      index,
      total,
      reason: String(p.reason || "Preparing..."),
      display: String(p.display || elementId),
      data: normalizeElementPayload(p.data),
      mounted: false,
    };
    return {
      elements: upsertElement(state.elements, el),
      activeElementReason: el.reason,
      activeElementId: el.elementId,
    };
  }

  if (eventType === "element.mounted") {
    const stepIndex =
      typeof p.step_index === "number" ? p.step_index : state.currentIndex;
    const index = typeof p.index === "number" ? p.index : 0;
    const total = typeof p.total === "number" ? p.total : 1;
    const elementId = String(p.element_id || `${stepIndex}-${index}`);
    const id = `${state.executionId}-element-${elementId}`;
    const el: BuildElement = {
      id,
      stepIndex,
      stepId: String(p.step_id || `${state.target}-${stepIndex}`),
      elementId,
      index,
      total,
      reason: String(p.reason || ""),
      display: String(p.display || elementId),
      data: normalizeElementPayload(p.data),
      mounted: true,
    };
    return {
      elements: upsertElement(state.elements, el),
      activeElementReason: el.reason,
      activeElementId: el.elementId,
    };
  }

  if (eventType === "element.batch_mounted") {
    const items = Array.isArray(p.items) ? p.items : [];
    const stepIndex =
      typeof p.step_index === "number" ? p.step_index : state.currentIndex;
    const total = typeof p.total === "number" ? p.total : items.length;
    let nextElements = state.elements;
    for (let i = 0; i < items.length; i++) {
      const raw = items[i];
      const data =
        typeof raw === "object" && raw !== null
          ? (raw as Record<string, unknown>)
          : ({} as Record<string, unknown>);
      const index =
        typeof data.index === "number" ? data.index : i;
      const elementId = String(
        data.element_id || data.id || `${stepIndex}-${index}`
      );
      const id = `${state.executionId}-element-${elementId}`;
      const el: BuildElement = {
        id,
        stepIndex,
        stepId: String(data.step_id || `${state.target}-${stepIndex}`),
        elementId,
        index,
        total,
        reason: String(data.reason || p.reason || ""),
        display: String(data.display || elementId),
        data,
        mounted: true,
      };
      nextElements = upsertElement(nextElements, el);
    }
    return { elements: nextElements };
  }

  if (eventType === "generation.finishing") {
    return { phase: "Finishing up", activeStatus: "finishing" };
  }

  if (eventType === "generation.completed") {
    const completed = state.artifacts.filter((a) => a.status === "complete").length;
    const total = state.totalArtifacts || state.artifacts.length;
    const isReady = completed >= total && total > 0;
    return {
      status: isReady ? "completed" : "running",
      phase: isReady
        ? event.label || `${state.target} is ready`
        : "Finishing up",
      activeName: isReady ? "" : state.activeName,
      activePurpose: isReady ? "" : state.activePurpose,
      activeBuilding: isReady ? "" : state.activeBuilding,
      activeLiveReason: isReady ? "" : state.activeLiveReason,
      activeStatus: isReady ? "complete" : state.activeStatus,
    };
  }

  if (eventType === "generation.failed") {
    return {
      status: "failed",
      phase: event.label || "Build failed",
      activeName: "",
      activePurpose: "",
      activeBuilding: "",
      activeLiveReason: "",
      activeStatus: "failed",
    };
  }

  return {};
}
