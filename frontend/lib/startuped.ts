"use client";

export type StartupedEventInput = {
  name: string;
  description?: string;
  type?: "behavioral" | "engagement" | "conversion" | "retention" | "news-update" | "measurement";
  status?: "active" | "inactive" | "draft";
  strength?: number;
  value?: "Low" | "Medium" | "High";
  signalKey?: string;
  metadata?: Record<string, unknown>;
};

type QueuedEvent = Required<Pick<StartupedEventInput, "name">> &
  Omit<StartupedEventInput, "name"> & { metadata: Record<string, unknown> };

const queue: QueuedEvent[] = [];
const recentKeys = new Set<string>();
let flushScheduled = false;
let sessionId: string | null = null;

function makeId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getSessionId(): string {
  if (typeof window === "undefined") return "server";
  if (sessionId) return sessionId;
  try {
    const saved = window.sessionStorage.getItem("anvaya.startuped.session");
    if (saved) {
      sessionId = saved;
      return sessionId;
    }
    sessionId = makeId();
    window.sessionStorage.setItem("anvaya.startuped.session", sessionId);
  } catch {
    sessionId = makeId();
  }
  return sessionId;
}

function safeMetadata(metadata?: Record<string, unknown>): Record<string, unknown> {
  const safe: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(metadata || {})) {
    if (value === null || ["string", "number", "boolean"].includes(typeof value)) {
      safe[key] = typeof value === "string" ? value.slice(0, 160) : value;
    }
  }
  return safe;
}

function scheduleFlush() {
  if (flushScheduled || typeof window === "undefined") return;
  flushScheduled = true;
  setTimeout(() => {
    flushScheduled = false;
    void flushStartupedEvents();
  }, 0);
}

export function trackStartupedEvent(input: StartupedEventInput): void {
  if (!input?.name || typeof window === "undefined") return;

  const metadata = safeMetadata(input.metadata);
  const eventId = String(metadata.eventId || makeId());
  const dedupeKey = String(input.signalKey || `${input.name}:${eventId}`);
  if (recentKeys.has(dedupeKey)) return;

  recentKeys.add(dedupeKey);
  if (recentKeys.size > 500) {
    const first = recentKeys.values().next().value;
    if (first) recentKeys.delete(first);
  }

  queue.push({
    ...input,
    description: input.description || input.name,
    type: input.type || "behavioral",
    status: input.status || "active",
    strength: input.strength ?? 25,
    value: input.value || "Medium",
    signalKey: input.signalKey || `anvaya:${input.name}:${eventId}`,
    metadata: { ...metadata, eventId, sessionId: getSessionId(), occurredAt: new Date().toISOString() },
  });
  scheduleFlush();
}

export async function flushStartupedEvents(): Promise<void> {
  if (typeof window === "undefined" || !queue.length) return;
  const batch = queue.splice(0, queue.length);
  try {
    await fetch("/api/startuped/signals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }),
      keepalive: true,
    });
  } catch {}
}

export function trackRouteView(route: string): void {
  trackStartupedEvent({
    name: "anvaya.navigation.route.viewed",
    description: `User viewed ${route}`,
    type: "behavioral",
    strength: 10,
    value: "Low",
    metadata: { surface: "frontend", route },
  });
}

export function trackUiInteraction(target: EventTarget | null): void {
  const element = target instanceof Element ? target : null;
  if (!element || element.hasAttribute("data-startuped-ignore")) return;

  const interactive = element.closest("button, a, [role='button'], input, select, textarea");
  if (!interactive) return;

  const label =
    interactive.getAttribute("data-startuped-event") ||
    interactive.getAttribute("aria-label") ||
    interactive.getAttribute("title") ||
    interactive.getAttribute("name") ||
    interactive.id ||
    interactive.tagName.toLowerCase();

  trackStartupedEvent({
    name: "anvaya.ui.interaction",
    description: `User interacted with ${label}`,
    type: "behavioral",
    strength: 8,
    value: "Low",
    metadata: {
      surface: "frontend",
      route: window.location.pathname,
      interaction: "click",
      target: interactive.tagName.toLowerCase(),
      label: label.slice(0, 120),
    },
  });
}

export function trackFormSubmission(form: HTMLFormElement): void {
  const label =
    form.getAttribute("data-startuped-event") ||
    form.getAttribute("aria-label") ||
    form.getAttribute("name") ||
    form.id ||
    "form";

  trackStartupedEvent({
    name: "anvaya.ui.form.submitted",
    description: `User submitted ${label}`,
    type: "engagement",
    strength: 30,
    value: "Medium",
    metadata: {
      surface: "frontend",
      route: window.location.pathname,
      form: label.slice(0, 120),
    },
  });
}

export function trackError(_message: string, source: string): void {
  trackStartupedEvent({
    name: "anvaya.error.occurred",
    description: "A frontend error occurred",
    type: "behavioral",
    strength: 20,
    value: "Medium",
    metadata: { surface: "frontend", source },
  });
}
