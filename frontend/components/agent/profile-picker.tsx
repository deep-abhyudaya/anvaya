"use client";

import React, { useEffect, useRef, useState } from "react";
import { ChevronDown, Zap } from "lucide-react";
import { useAgent } from "./agent-context";
import { cn } from "@/lib/utils";

export function ProfilePicker({
  variant = "default",
  className,
}: {
  variant?: "default" | "minimal";
  className?: string;
}) {
  const { state, selectProfile } = useAgent();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const activeProfile = state.profile;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const trigger =
    variant === "minimal" ? (
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "flex items-center gap-1.5 text-[10px] text-muted transition-colors hover:text-primary",
          className
        )}
      >
        <Zap className="h-3 w-3" strokeWidth={1.5} />
        <span className="truncate max-w-[80px]">{activeProfile?.name || "Agent"}</span>
        <ChevronDown
          className={cn("h-3 w-3 shrink-0 transition-transform", open && "rotate-180")}
          strokeWidth={1.5}
        />
      </button>
    ) : (
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "flex items-center gap-1.5 rounded border border-hairline px-2 py-1.5 text-[10px] text-primary transition-colors hover:border-accent/60",
          className
        )}
      >
        <Zap className="h-3 w-3 text-accent" strokeWidth={1.5} />
        <span className="max-w-[80px] truncate uppercase tracking-wider">
          {activeProfile?.name || "Agent"}
        </span>
        <ChevronDown
          className={cn("h-3 w-3 text-muted transition-transform", open && "rotate-180")}
          strokeWidth={1.5}
        />
      </button>
    );

  return (
    <div className="relative" ref={ref}>
      {trigger}

      {open && (
        <div className="absolute bottom-full right-0 z-50 mb-1 w-64 rounded border border-hairline bg-canvas-panel p-2 shadow-xl">
          <div className="mb-1 text-[9px] uppercase tracking-wider text-muted">Agent Profiles</div>
          <div className="max-h-60 space-y-0.5 overflow-y-auto pr-0.5">
            {state.profiles?.map((p) => {
              const isCurrent = p.id === activeProfile?.id;
              return (
                <button
                  key={p.id}
                  onClick={() => {
                    selectProfile(p.id);
                    setOpen(false);
                  }}
                  className={cn(
                    "w-full rounded p-2 text-left transition-colors",
                    isCurrent ? "bg-accent-dim/50" : "hover:bg-canvas-subtle"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={cn("h-1.5 w-1.5 rounded-full", isCurrent ? "bg-accent" : "bg-muted")}
                    />
                    <span className="text-[11px] font-medium text-primary">{p.display_name}</span>
                  </div>
                  <div className="mt-0.5 pl-3 text-[9px] text-muted">{p.purpose}</div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
