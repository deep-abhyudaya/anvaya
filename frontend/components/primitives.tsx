"use client";

import React from "react";
import { cn } from "@/lib/utils";

export function Mono({ children, className, tone }: { children: React.ReactNode; className?: string; tone?: "muted" | "accent" | "warning" | "primary" | "success" | "critical" }) {
  return (
    <span
      className={cn(
        "font-mono text-[10px] uppercase tracking-wider",
        tone === "accent" && "text-accent",
        tone === "warning" && "text-warning",
        tone === "primary" && "text-primary",
        tone === "success" && "text-success",
        tone === "critical" && "text-critical",
        (!tone || tone === "muted") && "text-muted",
        className
      )}
    >
      {children}
    </span>
  );
}

export function Panel({ children, className, glow }: { children: React.ReactNode; className?: string; glow?: "accent" | "warning" }) {
  return (
    <div className={cn("border border-hairline bg-canvas-panel/60", glow === "accent" && "glow-accent border-accent/50", glow === "warning" && "glow-warning border-warning/50", className)}>
      {children}
    </div>
  );
}

export function Dot({ tone = "accent", pulse, className }: { tone?: "accent" | "warning" | "success" | "muted" | "critical"; pulse?: boolean; className?: string }) {
  return (
    <span
      className={cn(
        "inline-block h-1.5 w-1.5 rounded-full",
        tone === "accent" && "bg-accent",
        tone === "warning" && "bg-warning",
        tone === "success" && "bg-success",
        tone === "critical" && "bg-critical",
        tone === "muted" && "bg-muted",
        pulse && "anim-pulse",
        className
      )}
    />
  );
}

export function Tabs({ items, value, onChange, className }: { items: string[]; value: string; onChange: (v: string) => void; className?: string }) {
  return (
    <div className={cn("flex items-center gap-4", className)} role="tablist">
      {items.map((it) => {
        const active = it === value;
        return (
          <button
            key={it}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(it)}
            className={cn(
              "border-b pb-1 font-mono text-[10px] uppercase tracking-widest transition-colors",
              active ? "border-accent text-primary" : "border-transparent text-muted hover:text-secondary"
            )}
          >
            {it}
          </button>
        );
      })}
    </div>
  );
}

export function Segmented({ items, value, onChange }: { items: string[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex border border-hairline" role="group">
      {items.map((it) => {
        const active = it === value;
        return (
          <button
            key={it}
            aria-pressed={active}
            onClick={() => onChange(it)}
            className={cn(
              "px-4 py-1.5 font-mono text-[10px] uppercase tracking-widest transition-colors",
              active ? "bg-accent-dim text-accent shadow-[inset_0_0_12px_var(--color-accent-dim)]" : "text-muted hover:text-secondary"
            )}
          >
            {it}
          </button>
        );
      })}
    </div>
  );
}

export function Chip({ children, tone = "muted" }: { children: React.ReactNode; tone?: "muted" | "accent" | "warning" | "success" | "critical" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center border px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider",
        tone === "accent" && "border-accent/50 text-accent",
        tone === "warning" && "border-warning/60 text-warning",
        tone === "success" && "border-success/50 text-success",
        tone === "critical" && "border-critical/50 text-critical",
        tone === "muted" && "border-hairline text-muted"
      )}
    >
      {children}
    </span>
  );
}

export function Bar({ value, warning, className }: { value: number | null | undefined; warning?: boolean; className?: string }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return (
      <div className={cn("bar-track w-full", className)}>
        <div className="h-full w-full bg-canvas-subtle/50" />
      </div>
    );
  }
  return (
    <div className={cn("bar-track w-full", className)}>
      <div className={warning ? "bar-fill-warning" : "bar-fill"} style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }} />
    </div>
  );
}

export function TransportBtn({ children, onClick, label, active }: { children: React.ReactNode; onClick: () => void; label: string; active?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cn(
        "flex h-6 w-7 items-center justify-center border border-hairline text-muted transition-colors hover:border-accent/40 hover:text-accent",
        active && "border-accent/60 text-accent glow-accent"
      )}
    >
      {children}
    </button>
  );
}

export function Scrubber({ value, onChange, label, markers }: { value: number; onChange: (v: number) => void; label: string; markers?: { at: number; tone: "accent" | "warning" | "muted" }[] }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const setFromClient = (clientX: number) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    onChange(Math.min(1, Math.max(0, (clientX - r.left) / r.width)));
  };
  const onPointerDown = (e: React.PointerEvent) => {
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    setFromClient(e.clientX);
    const move = (ev: PointerEvent) => setFromClient(ev.clientX);
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return (
    <div
      ref={ref}
      role="slider"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value * 100)}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "ArrowLeft") onChange(Math.max(0, value - 0.02));
        if (e.key === "ArrowRight") onChange(Math.min(1, value + 0.02));
      }}
      onPointerDown={onPointerDown}
      className="relative h-5 flex-1 cursor-ew-resize touch-none"
    >
      <div className="absolute left-0 right-0 top-1/2 h-px -translate-y-1/2 bg-hairline-bright" />
      {markers?.map((m, i) => (
        <span
          key={i}
          className={cn(
            "absolute top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full",
            m.tone === "accent" && "bg-accent",
            m.tone === "warning" && "bg-warning",
            m.tone === "muted" && "bg-muted"
          )}
          style={{ left: `${m.at * 100}%` }}
        />
      ))}
      <span
        className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent shadow-[0_0_8px_var(--color-accent-glow)]"
        style={{ left: `${value * 100}%` }}
      />
    </div>
  );
}
