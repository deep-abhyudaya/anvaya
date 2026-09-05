"use client";

import React, { createContext, useContext, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { HEADER_DEFAULTS } from "./data";

export interface AppState {
  cycles: number;
  connected: boolean;
  activeProjectId: string | null;
  arbor: { selected: string | null; positions: Record<string, { x: number; y: number }> };
  impact: { filter: string; selected: string | null };
  arena: { stage: "before" | "after" | "counterfactuals" };
  orbits: { period: string; selected: string | null };
  replay: { t: number; playing: boolean; speed: number; details: boolean; replayNo: number };
  eco: {
    step: number; playing: boolean; speed: number;
    mode: "IGNORE" | "CONTAIN";
    positions: Record<string, { x: number; y: number }>;
    selected: string | null;
  };
  segments: { selected: string | null; positions: Record<string, { x: number; y: number }> };
  reach: { mode: "ATTACK" | "DEFENSE"; selected: string | null };
  trophy: { filter: string; sort: "recent" | "rarity" | "severity"; selected: string | null };
}

export const initialState: AppState = {
  cycles: HEADER_DEFAULTS.cycles,
  connected: true,
  activeProjectId: null,
  arbor: { selected: "process-pattern", positions: {} },
  impact: { filter: "ALL", selected: "INC-2214" },
  arena: { stage: "after" },
  orbits: { period: "last 24h", selected: null },
  replay: { t: 191, playing: false, speed: 1, details: false, replayNo: 1 },
  eco: { step: 4, playing: false, speed: 1, mode: "CONTAIN", positions: {}, selected: "D-01" },
  segments: { selected: "SEG-1", positions: {} },
  reach: { mode: "ATTACK", selected: "customer-db" },
  trophy: { filter: "ALL", sort: "recent", selected: "INC-2214" },
};

export type Action =
  | { type: "tick-cycle" }
  | { type: "set-connected"; value: boolean }
  | { type: "set-active-project"; value: string | null }
  | { type: "patch"; path: "arbor" | "impact" | "arena" | "orbits" | "replay" | "eco" | "segments" | "reach" | "trophy"; value: Record<string, unknown> };

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "tick-cycle":
      return { ...state, cycles: state.cycles + 1 };
    case "set-connected":
      return { ...state, connected: action.value };
    case "set-active-project":
      return { ...state, activeProjectId: action.value };
    case "patch": {
      const base = state[action.path] as unknown as Record<string, unknown>;
      return { ...state, [action.path]: { ...base, ...action.value } } as AppState;
    }
    default:
      return state;
  }
}

const StoreCtx = createContext<{ state: AppState; dispatch: React.Dispatch<Action> } | null>(null);

export function AnvayaProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    let alive = true;
    const probe = async () => {
      try {
        const res = await fetch("/api/backend/health", { signal: AbortSignal.timeout(2500) });
        if (alive) dispatch({ type: "set-connected", value: res.ok });
      } catch {
        if (alive) dispatch({ type: "set-connected", value: false });
      }
    };
    probe();
    const id = setInterval(probe, 5000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  return <StoreCtx.Provider value={{ state, dispatch }}>{children}</StoreCtx.Provider>;
}

export function useAnvaya() {
  const ctx = useContext(StoreCtx);
  if (!ctx) throw new Error("useAnvaya outside provider");
  return ctx;
}

export function useLiveClock(base = "14:04:38") {
  const startRef = useRef<number>(Date.now());
  const [now, setNow] = useState(base);
  useEffect(() => {
    const [h, m, s] = base.split(":").map(Number);
    const baseSec = h * 3600 + m * 60 + s;
    const id = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startRef.current) / 1000);
      const total = baseSec + elapsed;
      const hh = Math.floor(total / 3600) % 24;
      const mm = Math.floor((total % 3600) / 60);
      const ss = total % 60;
      setNow([hh, mm, ss].map((n) => String(n).padStart(2, "0")).join(":"));
    }, 1000);
    return () => clearInterval(id);
  }, [base]);
  return now;
}

export function useTicker(active: boolean, speed: number, onTick: (dt: number) => void) {
  const cb = useRef(onTick);
  cb.current = onTick;
  useEffect(() => {
    if (!active) return;
    let last = performance.now();
    let raf = 0;
    const loop = (now: number) => {
      const dt = ((now - last) / 1000) * speed;
      last = now;
      cb.current(dt);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [active, speed]);
}

export function useMemoValue<T>(fn: () => T, deps: unknown[]): T {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(fn, deps);
}
