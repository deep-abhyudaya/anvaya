"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Pin, PinOff, Search, SlidersHorizontal, X } from "lucide-react";
import { useAgent, ModelConfig } from "./agent-context";
import { Chip, Dot, Tabs, Bar } from "@/components/primitives";
import { cn } from "@/lib/utils";

const GROUP_BY_LABELS: Record<string, string> = {
  none: "None",
  provider: "Provider",
  maker: "Maker",
  family: "Family",
  cost: "Cost",
  availability: "Availability",
  latency: "Latency",
  context: "Context",
};

function contextBucket(n: number) {
  if (!n) return "Configurable";
  if (n < 32_000) return "0–32K";
  if (n < 128_000) return "32K–128K";
  if (n < 500_000) return "128K–500K";
  if (n < 1_000_000) return "500K–1M";
  return "1M+";
}

const SORT_BY_LABELS: Record<string, string> = {
  recommended: "Recommended",
  provider: "Provider",
  maker: "Maker",
  cost: "Cost",
  context: "Context",
  latency: "Latency",
};

const LATENCY_ORDER: Record<string, number> = {
  instant: 0,
  fast: 1,
  standard: 2,
  slow: 3,
  unknown: 9,
};

function formatContextWindow(n: number) {
  if (!n) return "Configurable";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1000)}K`;
  return `${n}`;
}

function availabilityTone(a?: string): "success" | "accent" | "warning" | "critical" | "muted" {
  if (a === "available") return "success";
  if (a === "configured") return "accent";
  if (a === "unavailable" || a === "deprecated") return "critical";
  return "warning";
}

function providerLabel(p: string) {
  return p === "anvaya" ? "ANVAYA" : p.toUpperCase();
}

function evidenceTone(confidence: string): "success" | "accent" | "warning" | "critical" | "muted" {
  if (confidence.toLowerCase().startsWith("high")) return "success";
  if (confidence.toLowerCase().startsWith("medium")) return "accent";
  if (confidence.toLowerCase().startsWith("low")) return "warning";
  if (confidence.toLowerCase() === "unknown") return "critical";
  return "muted";
}

function qualityTone(quality?: string | null): "success" | "accent" | "warning" | "critical" | "muted" {
  if (!quality) return "muted";
  if (quality === "frontier") return "success";
  if (quality === "strong") return "accent";
  if (quality === "specialist") return "warning";
  if (quality === "utility") return "accent";
  if (quality === "experimental" || quality === "unknown") return "critical";
  return "muted";
}

function costScore(costClass: string) {
  switch (costClass) {
    case "free":
      return 1;
    case "low":
      return 0.75;
    case "standard":
      return 0.5;
    case "high":
      return 0.25;
    default:
      return 0.4;
  }
}

function costLabel(costClass: string) {
  if (costClass === "standard") return "medium";
  return costClass;
}

function accessLabel(accessClass: string) {
  if (accessClass === "promotional_free") return "promo free";
  if (accessClass === "community_free") return "community free";
  if (accessClass === "native_free") return "native free";
  return accessClass;
}

function accessColor(accessClass: string): "warning" | "accent" | "success" | "muted" {
  if (accessClass === "community_free") return "warning";
  if (accessClass === "promotional_free") return "accent";
  if (accessClass === "native_free") return "success";
  return "muted";
}

function privacyColor(privacyClass: string): "critical" | "muted" {
  if (privacyClass === "public_community_endpoint") return "critical";
  return "muted";
}

function costColor(costClass: string) {
  switch (costClass) {
    case "free":
      return "success";
    case "low":
      return "accent";
    case "standard":
      return "warning";
    case "high":
    case "premium":
      return "critical";
    default:
      return "muted";
  }
}

function profileFitScore(model: ModelConfig, profileId: string): number | null {
  const fit = model.profile_fit?.[profileId];
  if (fit === undefined || fit === null || Number.isNaN(fit)) {
    return null;
  }
  return Math.max(0, Math.min(1, fit));
}

function MiniEfficiencyBar({ costClass }: { costClass: string }) {
  return (
    <div className="h-1 w-8 overflow-hidden rounded-full bg-hairline">
      <div
        className={cn(
          "h-full rounded-full",
          costClass === "free" && "bg-success",
          costClass === "low" && "bg-accent",
          costClass === "standard" && "bg-warning",
          (costClass === "high" || costClass === "premium") && "bg-critical",
          !["free", "low", "standard", "high", "premium"].includes(costClass) && "bg-muted"
        )}
        style={{ width: `${Math.round(costScore(costClass) * 100)}%` }}
      />
    </div>
  );
}

function ModelLogo({
  model,
  size = 6,
}: {
  model: ModelConfig;
  size?: number;
}) {
  const [srcIndex, setSrcIndex] = useState(0);
  const domain = model.logo_domain;
  const sizeCls = size >= 8 ? "h-8 w-8" : "h-6 w-6";
  const px = size >= 8 ? 128 : 64;

  const sources = domain
    ? [
        `https://unavatar.io/${domain}?fallback=false`,
        `https://www.google.com/s2/favicons?domain=${domain}&sz=${px}`,
        `https://icons.duckduckgo.com/ip3/${domain}.ico`,
      ]
    : [];

  if (!domain || srcIndex >= sources.length) {
    return (
      <span
        className={cn(
          "flex shrink-0 items-center justify-center rounded border border-hairline bg-canvas-subtle text-[10px] font-semibold uppercase text-primary",
          sizeCls
        )}
      >
        {(model.maker || model.provider || model.display_name).slice(0, 1)}
      </span>
    );
  }

  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center overflow-hidden rounded",
        sizeCls
      )}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={sources[srcIndex]}
        alt={model.display_name}
        className="h-full w-full object-contain"
        onError={() => setSrcIndex((i) => i + 1)}
      />
    </span>
  );
}

function CapabilityBadge({ label }: { label: string }) {
  return (
    <span className="rounded border border-hairline bg-canvas-subtle px-1.5 py-0.5 text-[8px] uppercase tracking-wider text-muted">
      {label}
    </span>
  );
}

const ROLE_ORDER = ["sentinel", "pathfinder", "responder", "auditor"] as const;

function AnvayaFit({ model }: { model: ModelConfig }) {
  const isOrchestrator = model.gateway_type === "orchestrator" || model.provider === "anvaya";
  const label = isOrchestrator ? "ORCHESTRATOR FIT" : "ANVAYA FIT";

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[9px] uppercase tracking-wider text-muted">
        <span title="ANVAYA Fit is a role-specific estimate derived from public benchmark evidence, model capabilities, provider metadata, and—when available—ANVAYA internal evaluations. It is not a universal intelligence score.">
          {label}
        </span>
        <span className="normal-case tracking-normal">
          {model.evidence_level || "Provisional"}
        </span>
      </div>

      <div className="space-y-1">
        {ROLE_ORDER.map((role) => {
          const fit = profileFitScore(model, role);
          return (
            <div key={role} className="grid grid-cols-[5.5rem_1.75rem_1fr] items-center gap-1.5">
              <span className="text-[9px] capitalize text-muted">{role}</span>
              <span className="text-[10px] text-right font-mono text-primary">
                {fit === null ? "—" : Math.round(fit * 100)}
              </span>
              <Bar value={fit} className="h-1" />
            </div>
          );
        })}
      </div>

      <p className="text-[8px] leading-relaxed text-muted">
        {isOrchestrator
          ? "ORCHESTRATOR FIT — ANVAYA's local policy orchestrator. Not a foundation model."
          : "ANVAYA Fit is a role-specific estimate derived from public benchmark evidence, model capabilities, provider metadata, and—when available—ANVAYA internal evaluations. It is not a universal intelligence score."}
      </p>
    </div>
  );
}

type FilterState = {
  providers: string[];
  makers: string[];
  cost: string[];
  capabilities: string[];
  availability: string[];
  contextMin: number;
  contextMax: number;
  hasTools?: boolean;
  hasStreaming?: boolean;
  hasReasoning?: boolean;
  hasMultimodal?: boolean;
};

const DEFAULT_FILTERS: FilterState = {
  providers: [],
  makers: [],
  cost: [],
  capabilities: [],
  availability: [],
  contextMin: 0,
  contextMax: 2_000_000,
};

function uniq<T>(arr: T[]) {
  return Array.from(new Set(arr));
}

function matchesSearch(model: ModelConfig, q: string) {
  if (!q) return true;
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  const hay = [
    model.display_name,
    model.id,
    model.model,
    model.provider,
    model.maker,
    model.family,
    model.description,
    model.purpose,
    ...(model.capabilities || []),
    model.cost_class,
    String(model.context_window),
  ]
    .join(" ")
    .toLowerCase();
  return terms.every((t) => hay.includes(t));
}

function modelCanRun(model: ModelConfig) {
  return model.availability === "available" || model.availability === "configured";
}

function scoreModel(model: ModelConfig, profileId: string | undefined) {
  let score = 0;
  if (model.availability === "available") score += 30;
  else if (model.availability === "configured") score += 20;
  if (model.configured) score += 10;
  if (model.cost_class === "free") score += 8;
  if (profileId) {
    const fit = profileFitScore(model, profileId);
    score += (fit === null ? 0.2 : fit) * 20;
  }
  if (model.supports_tools && model.supports_streaming) score += 5;
  return score;
}

export function ModelSelector() {
  const { state, dispatch } = useAgent();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [hovered, setHovered] = useState<ModelConfig | null>(null);
  const [view, setView] = useState<string>("all");
  const [groupBy, setGroupBy] = useState<string>("provider");
  const [sortBy, setSortBy] = useState<string>("recommended");
  const [pinnedIds, setPinnedIds] = useState<string[]>([]);
  const [recentIds, setRecentIds] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [keyboardIndex, setKeyboardIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const pinned = localStorage.getItem("anvaya:pinned-models");
      const recent = localStorage.getItem("anvaya:recent-models");
      const viewSaved = localStorage.getItem("anvaya:model-view");
      const groupSaved = localStorage.getItem("anvaya:model-group");
      const sortSaved = localStorage.getItem("anvaya:model-sort");
      const filtersSaved = localStorage.getItem("anvaya:model-filters");
      if (pinned) setPinnedIds(JSON.parse(pinned));
      if (recent) setRecentIds(JSON.parse(recent));
      if (viewSaved) setView(viewSaved);
      if (groupSaved) setGroupBy(groupSaved);
      if (sortSaved) setSortBy(sortSaved);
      if (filtersSaved) setFilters({ ...DEFAULT_FILTERS, ...JSON.parse(filtersSaved) });
    } catch {
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem("anvaya:model-view", view);
      localStorage.setItem("anvaya:model-group", groupBy);
      localStorage.setItem("anvaya:model-sort", sortBy);
      localStorage.setItem("anvaya:model-filters", JSON.stringify(filters));
    } catch {
    }
  }, [view, groupBy, sortBy, filters]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
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

  const togglePin = (id: string) => {
    setPinnedIds((prev) => {
      const next = prev.includes(id) ? prev.filter((p) => p !== id) : [id, ...prev];
      try {
        localStorage.setItem("anvaya:pinned-models", JSON.stringify(next));
      } catch {
      }
      return next;
    });
  };

  const pushRecent = (id: string) => {
    setRecentIds((prev) => {
      const next = [id, ...prev.filter((r) => r !== id)].slice(0, 10);
      try {
        localStorage.setItem("anvaya:recent-models", JSON.stringify(next));
      } catch {
      }
      return next;
    });
  };

  const allModels = useMemo(() => state.models || [], [state.models]);

  const allProviders = useMemo(
    () => uniq(allModels.map((m) => m.provider)).sort(),
    [allModels]
  );
  const allMakers = useMemo(
    () =>
      uniq(allModels.map((m) => m.maker).filter(Boolean)).sort((a, b) =>
        a.localeCompare(b)
      ),
    [allModels]
  );
  const allCapabilities = useMemo(
    () =>
      uniq(allModels.flatMap((m) => m.capabilities || [])).filter(
        (c) => !["chat"].includes(c)
      ),
    [allModels]
  );

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allModels.filter((m) => {
      if (!matchesSearch(m, q)) return false;

      if (view === "available" && m.availability !== "available") return false;
      if (view === "configured" && !m.configured) return false;
      if (view === "favorites" && !pinnedIds.includes(m.id)) return false;
      if (view === "recent" && !recentIds.includes(m.id)) return false;

      if (filters.providers.length && !filters.providers.includes(m.provider)) return false;
      if (filters.makers.length && !filters.makers.includes(m.maker)) return false;
      if (filters.cost.length && !filters.cost.includes(m.cost_class)) return false;
      if (filters.availability.length && !filters.availability.includes(m.availability)) return false;
      if (m.context_window < filters.contextMin || m.context_window > filters.contextMax)
        return false;
      if (filters.hasTools && !m.supports_tools) return false;
      if (filters.hasStreaming && !m.supports_streaming) return false;
      if (filters.hasReasoning && !m.supports_reasoning) return false;
      if (filters.hasMultimodal && !m.supports_multimodal) return false;
      if (
        filters.capabilities.length &&
        !filters.capabilities.every((c) => m.capabilities?.includes(c))
      )
        return false;

      return true;
    });
  }, [allModels, search, view, filters, pinnedIds, recentIds]);

  const sorted = useMemo(() => {
    const profileId = state.profile?.id;
    const sortedList = [...filtered];
    if (sortBy === "recommended") {
      sortedList.sort((a, b) => scoreModel(b, profileId) - scoreModel(a, profileId));
    } else if (sortBy === "provider") {
      sortedList.sort((a, b) => a.provider.localeCompare(b.provider) || a.display_name.localeCompare(b.display_name));
    } else if (sortBy === "maker") {
      sortedList.sort((a, b) => (a.maker || "").localeCompare(b.maker || "") || a.display_name.localeCompare(b.display_name));
    } else if (sortBy === "cost") {
      sortedList.sort((a, b) => costScore(b.cost_class) - costScore(a.cost_class));
    } else if (sortBy === "context") {
      sortedList.sort((a, b) => b.context_window - a.context_window);
    } else if (sortBy === "latency") {
      sortedList.sort(
        (a, b) =>
          (LATENCY_ORDER[a.latency_class] ?? 9) - (LATENCY_ORDER[b.latency_class] ?? 9) ||
          a.display_name.localeCompare(b.display_name)
      );
    }
    return sortedList;
  }, [filtered, sortBy, state.profile?.id]);

  const grouped = useMemo(() => {
    if (groupBy === "none") return { "All models": sorted };
    const groups: Record<string, ModelConfig[]> = {};
    for (const m of sorted) {
      let key = "";
      if (groupBy === "provider") key = m.provider;
      else if (groupBy === "maker") key = m.maker || "Unknown maker";
      else if (groupBy === "family") key = m.family || "Unknown family";
      else if (groupBy === "cost") key = m.cost_class || "unknown";
      else if (groupBy === "availability") key = m.availability || "unknown";
      else if (groupBy === "latency") key = m.latency_class || "unknown";
      else if (groupBy === "context") key = contextBucket(m.context_window);
      if (!groups[key]) groups[key] = [];
      groups[key].push(m);
    }
    return groups;
  }, [sorted, groupBy]);

  const flatRows = useMemo(() => {
    const rows: { type: "group"; label: string } | { type: "model"; model: ModelConfig }[] = [];
    for (const [label, models] of Object.entries(grouped)) {
      rows.push({ type: "group", label } as any);
      for (const m of models) rows.push({ type: "model", model: m } as any);
    }
    return rows;
  }, [grouped]);


  const current = state.model;
  const detail = hovered;

  const setFilter = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const toggleFilter = (key: "providers" | "makers" | "cost" | "capabilities" | "availability", value: string) => {
    setFilters((prev) => {
      const arr = prev[key];
      const next = arr.includes(value) ? arr.filter((v) => v !== value) : [...arr, value];
      return { ...prev, [key]: next };
    });
  };

  const clearFilters = () => setFilters(DEFAULT_FILTERS);

  const activeChips = useMemo(() => {
    const chips: { label: string; onRemove: () => void }[] = [];
    if (search)
      chips.push({
        label: `search: ${search}`,
        onRemove: () => setSearch(""),
      });
    filters.providers.forEach((p) =>
      chips.push({
        label: `provider: ${p}`,
        onRemove: () => toggleFilter("providers", p),
      })
    );
    filters.makers.forEach((m) =>
      chips.push({
        label: `maker: ${m}`,
        onRemove: () => toggleFilter("makers", m),
      })
    );
    filters.cost.forEach((c) =>
      chips.push({
        label: `cost: ${c}`,
        onRemove: () => toggleFilter("cost", c),
      })
    );
    filters.capabilities.forEach((c) =>
      chips.push({
        label: `cap: ${c}`,
        onRemove: () => toggleFilter("capabilities", c),
      })
    );
    filters.availability.forEach((a) =>
      chips.push({
        label: `status: ${a}`,
        onRemove: () => toggleFilter("availability", a),
      })
    );
    if (filters.hasTools) chips.push({ label: "tools", onRemove: () => setFilter("hasTools", false) });
    if (filters.hasStreaming) chips.push({ label: "streaming", onRemove: () => setFilter("hasStreaming", false) });
    if (filters.hasReasoning) chips.push({ label: "reasoning", onRemove: () => setFilter("hasReasoning", false) });
    if (filters.hasMultimodal) chips.push({ label: "multimodal", onRemove: () => setFilter("hasMultimodal", false) });
    return chips;
  }, [search, filters]);

  const selectModel = (m: ModelConfig) => {
    if (!modelCanRun(m)) return;
    dispatch({ type: "setModel", model: m });
    pushRecent(m.id);
    setOpen(false);
    setHovered(null);
    setKeyboardIndex(-1);
  };

  const focusRowAt = (index: number) => {
    const row = listRef.current?.querySelector(`[data-row-index="${index}"]`);
    if (row) row.scrollIntoView({ block: "nearest" });
  };

  const onContainerKeyDown = (e: React.KeyboardEvent) => {
    if (!open) return;
    const modelRows = flatRows.filter((r: any) => r.type === "model");
    if (!modelRows.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setKeyboardIndex((prev) => {
        const next = Math.min(prev + 1, modelRows.length - 1);
        focusRowAt(next);
        setHovered((modelRows[next] as any).model);
        return next;
      });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setKeyboardIndex((prev) => {
        const next = Math.max(prev - 1, 0);
        focusRowAt(next);
        setHovered((modelRows[next] as any).model);
        return next;
      });
    } else if (e.key === "Enter" && keyboardIndex >= 0) {
      e.preventDefault();
      selectModel((modelRows[keyboardIndex] as any).model);
    }
  };

  const renderRow = (m: ModelConfig, idx: number) => {
    const isCurrent = m.id === current?.id;
    const isPinned = pinnedIds.includes(m.id);
    const unavailable = !modelCanRun(m);
    return (
      <button
        key={m.id}
        data-row-index={idx}
        onClick={() => selectModel(m)}
        onMouseEnter={() => {
          setHovered(m);
          setKeyboardIndex(idx);
        }}
        onFocus={() => {
          setHovered(m);
          setKeyboardIndex(idx);
        }}
        aria-disabled={unavailable}
        className={cn(
          "flex w-full items-center gap-2.5 rounded px-2 py-2 text-left transition-colors",
          isCurrent ? "bg-accent-dim/40" : keyboardIndex === idx ? "bg-canvas-subtle" : "hover:bg-canvas-subtle",
          unavailable && "cursor-not-allowed opacity-40"
        )}
      >
        <ModelLogo model={m} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span className="truncate text-[11px] font-medium text-primary">{m.display_name}</span>
            {isPinned && <Pin className="h-2.5 w-2.5 shrink-0 text-accent" strokeWidth={2} />}
          </div>
          <div className="truncate text-[9px] text-muted">
            {m.maker || providerLabel(m.provider)} · {providerLabel(m.provider)} · {formatContextWindow(m.context_window)} ctx
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Dot tone={availabilityTone(m.availability)} pulse={false} />
          <MiniEfficiencyBar costClass={m.cost_class} />
        </div>
      </button>
    );
  };

  return (
    <div className="relative" ref={containerRef} onKeyDown={onContainerKeyDown}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded border border-hairline px-2 py-1.5 text-[10px] text-primary transition-colors hover:border-accent/60"
        aria-label="Select model"
      >
        <Dot tone={availabilityTone(current?.availability)} pulse={false} />
        <span className="max-w-[90px] truncate uppercase tracking-wider">
          {current?.display_name || "model"}
        </span>
        <ChevronDown className="h-3 w-3 text-muted" strokeWidth={1.5} />
      </button>

      {open && (
        <div
          className="absolute bottom-full right-0 z-50 mb-1 flex max-h-[85vh] overflow-hidden rounded border border-hairline bg-canvas-panel shadow-2xl"
          onMouseLeave={() => setHovered(null)}
        >
          {}
          {detail && (
            <div
              className={cn(
                "w-64 shrink-0 border-r border-hairline bg-canvas-subtle/40 p-3",
                !modelCanRun(detail) && "opacity-50"
              )}
            >
              <div className="mb-3 flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <ModelLogo model={detail} size={8} />
                  <div className="min-w-0">
                    <div className="truncate text-[11px] font-medium text-primary">{detail.display_name}</div>
                    <div className="truncate text-[9px] uppercase tracking-wider text-muted">
                      {providerLabel(detail.provider)}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => togglePin(detail.id)}
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded transition-colors",
                    pinnedIds.includes(detail.id) ? "text-accent" : "text-muted hover:text-primary"
                  )}
                  aria-label={pinnedIds.includes(detail.id) ? "Unpin model" : "Pin model"}
                >
                  {pinnedIds.includes(detail.id) ? (
                    <Pin className="h-3.5 w-3.5" strokeWidth={1.5} />
                  ) : (
                    <PinOff className="h-3.5 w-3.5" strokeWidth={1.5} />
                  )}
                </button>
              </div>

              <div className="mb-2 flex flex-wrap items-center gap-2 text-[9px] text-muted">
                <Chip tone={availabilityTone(detail.availability)}>
                  {detail.availability}
                </Chip>
                <Chip tone={costColor(detail.cost_class)}>{costLabel(detail.cost_class)}</Chip>
                {detail.access_class && detail.access_class !== "standard" && (
                  <Chip tone={accessColor(detail.access_class)}>{accessLabel(detail.access_class)}</Chip>
                )}
                {detail.privacy_class && detail.privacy_class !== "standard" && (
                  <Chip tone={privacyColor(detail.privacy_class)}>{detail.privacy_class.replace(/_/g, " ")}</Chip>
                )}
                <Chip tone={qualityTone(detail.quality_class)}>{detail.quality_class || "unknown"}</Chip>
                <span className="font-mono">{formatContextWindow(detail.context_window)} ctx</span>
                <span className="font-mono">{detail.latency_class}</span>
              </div>

              {}
              <div className="mb-3 space-y-1 rounded border border-hairline bg-canvas-subtle/30 p-2">
                <div className="text-[9px] uppercase tracking-wider text-muted">Identity</div>
                <div className="flex justify-between text-[10px] text-primary">
                  <span className="text-muted">Gateway</span>
                  <span className="font-medium">{providerLabel(detail.provider)}</span>
                </div>
                {detail.maker && (
                  <div className="flex justify-between text-[10px] text-primary">
                    <span className="text-muted">Maker</span>
                    <span className="font-medium">{detail.maker}</span>
                  </div>
                )}
                {detail.family && (
                  <div className="flex justify-between text-[10px] text-primary">
                    <span className="text-muted">Family</span>
                    <span className="font-medium">{detail.family}</span>
                  </div>
                )}
                {detail.provider_model_id && (
                  <div className="flex justify-between text-[10px] text-primary">
                    <span className="text-muted">Model</span>
                    <span className="font-mono truncate pl-2 text-right">{detail.provider_model_id}</span>
                  </div>
                )}
              </div>

              {}
              <div className="mb-3 rounded border border-hairline bg-canvas-subtle/30 p-2">
                <div className="mb-1 text-[9px] uppercase tracking-wider text-muted">Context</div>
                <div className="text-[10px] text-primary">
                  {detail.context_window > 0 ? (
                    <>
                      <span className="font-mono">{formatContextWindow(detail.context_window)}</span>
                      <span className="text-muted"> context window</span>
                    </>
                  ) : (
                    <span>Configurable</span>
                  )}
                </div>
              </div>

              <p className="mb-3 line-clamp-4 text-[10px] leading-relaxed text-secondary">
                {detail.description || detail.purpose}
              </p>

              {detail.privacy_class === "public_community_endpoint" && (
                <div className="mb-3 rounded border border-critical/30 bg-critical/10 p-2 text-[10px] leading-relaxed text-critical">
                  Public community endpoint: prompts and completions may be logged for training and service operation. Do not use with sensitive or classified incident data.
                </div>
              )}

              <div className="mb-3">
                <AnvayaFit model={detail} />
              </div>

              {}
              <div className="mb-3 space-y-1.5 rounded border border-hairline bg-canvas-subtle/30 p-2">
                <div className="flex items-center justify-between text-[9px] uppercase tracking-wider text-muted">
                  <span>Evidence</span>
                  <Chip tone={evidenceTone(detail.evidence_level)}>{detail.evidence_level}</Chip>
                </div>
                {detail.benchmark_evidence && detail.benchmark_evidence.length > 0 && (
                  <>
                    {detail.benchmark_evidence.slice(0, 4).map((ev, i) => (
                      <div key={i} className="flex justify-between text-[10px] text-primary">
                        <span className="text-muted">{ev.name}</span>
                        <span className="font-mono">{ev.value}</span>
                      </div>
                    ))}
                    <div className="text-[8px] text-muted">Sources: {detail.benchmark_evidence.map((ev) => ev.source).join(", ")}</div>
                  </>
                )}
              </div>

              {detail.fit_reason && (
                <div className="mb-3 rounded border border-hairline bg-canvas-subtle/30 p-2">
                  <div className="mb-1 text-[9px] uppercase tracking-wider text-muted">Why ANVAYA recommends it</div>
                  <p className="text-[10px] leading-relaxed text-primary">{detail.fit_reason}</p>
                </div>
              )}

              {detail.limitations && (
                <div className="mb-3 rounded border border-hairline bg-canvas-subtle/30 p-2">
                  <div className="mb-1 text-[9px] uppercase tracking-wider text-muted">Limitations</div>
                  <p className="text-[10px] leading-relaxed text-primary">{detail.limitations}</p>
                </div>
              )}

              {detail.pricing_mode === "per_request" && detail.cost_per_request !== null && detail.cost_per_request !== undefined && (
                <div className="mb-3 space-y-1 rounded border border-hairline bg-canvas-subtle/30 p-2">
                  <div className="text-[9px] uppercase tracking-wider text-muted">Pricing</div>
                  <div className="flex justify-between text-[10px] text-primary">
                    <span>Per request</span>
                    <span className="font-mono">${detail.cost_per_request.toFixed(4)}</span>
                  </div>
                </div>
              )}

              {detail.pricing && detail.pricing_mode !== "per_request" && (detail.pricing.input_per_million !== null || detail.pricing.output_per_million !== null) && (
                <div className="mb-3 space-y-1 rounded border border-hairline bg-canvas-subtle/30 p-2">
                  <div className="text-[9px] uppercase tracking-wider text-muted">Pricing / 1M tokens</div>
                  {detail.pricing.input_per_million !== null && detail.pricing.input_per_million !== undefined && (
                    <div className="flex justify-between text-[10px] text-primary">
                      <span>Input</span>
                      <span className="font-mono">${detail.pricing.input_per_million.toFixed(4)}</span>
                    </div>
                  )}
                  {detail.pricing.cached_input_per_million !== null && detail.pricing.cached_input_per_million !== undefined && (
                    <div className="flex justify-between text-[10px] text-primary">
                      <span>Cached</span>
                      <span className="font-mono">${detail.pricing.cached_input_per_million.toFixed(4)}</span>
                    </div>
                  )}
                  {detail.pricing.output_per_million !== null && detail.pricing.output_per_million !== undefined && (
                    <div className="flex justify-between text-[10px] text-primary">
                      <span>Output</span>
                      <span className="font-mono">${detail.pricing.output_per_million.toFixed(4)}</span>
                    </div>
                  )}
                </div>
              )}

              {detail.max_tokens && (
                <div className="mb-1 text-[10px] text-secondary">
                  <span className="text-muted">Max output:</span> {detail.max_tokens.toLocaleString()} tokens
                </div>
              )}

              <div className="flex flex-wrap gap-1">
                {uniq(detail.capabilities).map((cap) => (
                  <CapabilityBadge key={cap} label={cap} />
                ))}
              </div>

              {detail.best_for?.length > 0 && (
                <div className="mt-3 text-[9px] text-accent">
                  Best for: {detail.best_for.join(", ")}
                </div>
              )}

              {modelCanRun(detail) && (
                <button
                  onClick={() => selectModel(detail)}
                  className="mt-3 w-full rounded border border-accent/50 bg-accent-dim/20 py-1.5 text-[10px] font-medium text-accent transition-colors hover:bg-accent-dim/40"
                >
                  Use model
                </button>
              )}
            </div>
          )}

          {}
          <div className="flex w-80 flex-col">
            {}
            <div className="border-b border-hairline p-2">
              <div className="mb-2 flex items-center gap-1.5 rounded border border-hairline px-2 py-1.5">
                <Search className="h-3 w-3 text-muted" strokeWidth={1.5} />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search all models"
                  className="w-full bg-transparent text-[11px] text-primary outline-none"
                  autoFocus
                />
              </div>

              <Tabs
                items={["all", "available", "configured", "favorites", "recent"]}
                value={view}
                onChange={setView}
                className="mb-2 justify-start"
              />

              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setShowFilters((s) => !s)}
                  className={cn(
                    "flex items-center gap-1 rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wider transition-colors",
                    showFilters
                      ? "border-accent/50 bg-accent-dim/20 text-accent"
                      : "border-hairline text-muted hover:border-accent/40"
                  )}
                >
                  <SlidersHorizontal className="h-3 w-3" strokeWidth={1.5} />
                  filters
                </button>

                <select
                  value={groupBy}
                  onChange={(e) => setGroupBy(e.target.value)}
                  className="rounded border border-hairline bg-transparent px-1.5 py-0.5 text-[9px] text-primary outline-none"
                >
                  {Object.entries(GROUP_BY_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      Group: {v}
                    </option>
                  ))}
                </select>

                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="rounded border border-hairline bg-transparent px-1.5 py-0.5 text-[9px] text-primary outline-none"
                >
                  {Object.entries(SORT_BY_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      Sort: {v}
                    </option>
                  ))}
                </select>
              </div>

              {activeChips.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {activeChips.map((chip, i) => (
                    <button
                      key={i}
                      onClick={chip.onRemove}
                      className="flex items-center gap-1 rounded border border-hairline bg-canvas-subtle px-1.5 py-0.5 text-[9px] text-primary transition-colors hover:border-critical/50 hover:text-critical"
                    >
                      {chip.label}
                      <X className="h-2.5 w-2.5" strokeWidth={2} />
                    </button>
                  ))}
                  {activeChips.length > 0 && (
                    <button
                      onClick={clearFilters}
                      className="text-[9px] text-muted underline hover:text-accent"
                    >
                      clear all
                    </button>
                  )}
                </div>
              )}
            </div>

            {}
            {showFilters && (
              <div className="max-h-48 space-y-2 overflow-y-auto border-b border-hairline bg-canvas-subtle/30 p-2 text-[10px]">
                {}
                <div>
                  <div className="mb-1 text-[9px] uppercase tracking-wider text-muted">Provider</div>
                  <div className="flex flex-wrap gap-1">
                    {allProviders.map((p) => (
                      <FilterPill
                        key={p}
                        label={p}
                        active={filters.providers.includes(p)}
                        onClick={() => toggleFilter("providers", p)}
                      />
                    ))}
                  </div>
                </div>

                {}
                <div>
                  <div className="mb-1 text-[9px] uppercase tracking-wider text-muted">Maker</div>
                  <div className="flex max-h-20 flex-wrap gap-1 overflow-y-auto">
                    {allMakers.map((m) => (
                      <FilterPill
                        key={m}
                        label={m}
                        active={filters.makers.includes(m)}
                        onClick={() => toggleFilter("makers", m)}
                      />
                    ))}
                  </div>
                </div>

                {}
                <div>
                  <div className="mb-1 text-[9px] uppercase tracking-wider text-muted">Cost</div>
                  <div className="flex flex-wrap gap-1">
                    {["free", "low", "standard", "high", "premium"].map((c) => (
                      <FilterPill
                        key={c}
                        label={c}
                        active={filters.cost.includes(c)}
                        onClick={() => toggleFilter("cost", c)}
                      />
                    ))}
                  </div>
                </div>

                {}
                <div>
                  <div className="mb-1 text-[9px] uppercase tracking-wider text-muted">Availability</div>
                  <div className="flex flex-wrap gap-1">
                    {["available", "configured", "unavailable"].map((a) => (
                      <FilterPill
                        key={a}
                        label={a}
                        active={filters.availability.includes(a)}
                        onClick={() => toggleFilter("availability", a)}
                      />
                    ))}
                  </div>
                </div>

                {}
                <div>
                  <div className="mb-1 text-[9px] uppercase tracking-wider text-muted">Capabilities</div>
                  <div className="flex flex-wrap gap-1">
                    {allCapabilities.map((c) => (
                      <FilterPill
                        key={c}
                        label={c}
                        active={filters.capabilities.includes(c)}
                        onClick={() => toggleFilter("capabilities", c)}
                      />
                    ))}
                  </div>
                </div>

                {}
                <div>
                  <div className="mb-1 text-[9px] uppercase tracking-wider text-muted">Must have</div>
                  <div className="flex flex-wrap gap-1">
                    <FilterPill
                      label="tools"
                      active={!!filters.hasTools}
                      onClick={() => setFilter("hasTools", !filters.hasTools)}
                    />
                    <FilterPill
                      label="streaming"
                      active={!!filters.hasStreaming}
                      onClick={() => setFilter("hasStreaming", !filters.hasStreaming)}
                    />
                    <FilterPill
                      label="reasoning"
                      active={!!filters.hasReasoning}
                      onClick={() => setFilter("hasReasoning", !filters.hasReasoning)}
                    />
                    <FilterPill
                      label="multimodal"
                      active={!!filters.hasMultimodal}
                      onClick={() => setFilter("hasMultimodal", !filters.hasMultimodal)}
                    />
                  </div>
                </div>
              </div>
            )}

            {}
            <div className="flex-1 overflow-y-auto p-2" ref={listRef}>
              {Object.entries(grouped).map(([group, models]) => (
                <React.Fragment key={group}>
                  <div className="px-2 pb-1 pt-2 text-[9px] uppercase tracking-wider text-muted">
                    {groupBy === "none" ? "All models" : group}
                  </div>
                  {models.map((m, i) => renderRow(m, i))}
                </React.Fragment>
              ))}

              {filtered.length === 0 && (
                <div className="py-4 text-center text-[10px] text-muted">No models match</div>
              )}
            </div>

            <div className="border-t border-hairline px-2 py-1 text-[9px] text-muted">
              {filtered.length} model{filtered.length === 1 ? "" : "s"} ·{" "}
              {state.profile?.display_name?.split(" — ")[0] || "sentinel"} profile
            </div>
          </div>
        </div>
      )}
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
          ? "bg-accent-dim/50 border border-accent/30 text-accent"
          : "border border-hairline text-muted hover:border-accent/60"
      )}
    >
      {label}
    </button>
  );
}
