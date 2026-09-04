"use client";

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { type Layout } from "react-grid-layout";
import ReactGridLayout from "react-grid-layout/legacy";
import "react-grid-layout/css/styles.css";
import { RotateCcw } from "lucide-react";
import { useSession } from "@/lib/auth-client";
import { cn } from "@/lib/utils";

export interface UseTileLayoutResult {
  layout: Layout;
  setLayout: (layout: Layout) => void;
  reset: () => void;
  loaded: boolean;
}

export function useTileLayout(
  page: string,
  defaultLayout: Layout,
  constraints: Record<string, { minW?: number; minH?: number }>
): UseTileLayoutResult {
  const { data } = useSession();
  const userId = data?.user?.id ?? "anonymous";
  const storageKey = `anvaya-tile-layout:${userId}:${page}`;

  const [state, setState] = useState<{ layout: Layout; loaded: boolean }>(() => ({
    layout: mergeConstraints(defaultLayout, constraints),
    loaded: false,
  }));

  useEffect(() => {
    if (typeof window === "undefined") {
      setState((s) => ({ ...s, loaded: true }));
      return;
    }
    let next: Layout = mergeConstraints(defaultLayout, constraints);
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) {
        const parsed = JSON.parse(raw) as unknown;
        if (Array.isArray(parsed) && parsed.every(isLayoutItemLike)) {
          next = mergeConstraints(parsed as Layout, constraints);
        }
      }
    } catch {
    }
    setState({ layout: next, loaded: true });
  }, [storageKey, defaultLayout, constraints]);

  const setLayout = useCallback(
    (layout: Layout) => {
      const merged = mergeConstraints(layout, constraints);
      setState((s) => ({ ...s, layout: merged }));
      try {
        if (typeof window !== "undefined") {
          localStorage.setItem(storageKey, JSON.stringify(merged));
        }
      } catch {
      }
    },
    [storageKey, constraints]
  );

  const reset = useCallback(() => {
    const merged = mergeConstraints(defaultLayout, constraints);
    setState({ layout: merged, loaded: true });
    try {
      if (typeof window !== "undefined") {
        localStorage.removeItem(storageKey);
      }
    } catch {
    }
  }, [storageKey, defaultLayout, constraints]);

  return { layout: state.layout, setLayout, reset, loaded: state.loaded };
}

function isLayoutItemLike(
  value: unknown
): value is { i: string; x: number; y: number; w: number; h: number } {
  return (
    typeof value === "object" &&
    value !== null &&
    "i" in value &&
    typeof (value as { i: unknown }).i === "string" &&
    "x" in value &&
    typeof (value as { x: unknown }).x === "number" &&
    "y" in value &&
    typeof (value as { y: unknown }).y === "number" &&
    "w" in value &&
    typeof (value as { w: unknown }).w === "number" &&
    "h" in value &&
    typeof (value as { h: unknown }).h === "number"
  );
}

function mergeConstraints(layout: Layout, constraints: Record<string, { minW?: number; minH?: number }>): Layout {
  return layout.map((item) => {
    const c = constraints[item.i];
    if (!c) return item;
    return {
      ...item,
      minW: c.minW ?? item.minW,
      minH: c.minH ?? item.minH,
    };
  });
}

export interface TileGridProps {
  layout: Layout;
  onLayoutChange: (layout: Layout) => void;
  maxRows?: number;
  children: React.ReactNode;
}

export function TileGrid({ layout, onLayoutChange, maxRows = 5, children }: TileGridProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const scrollRef = useRef<HTMLElement | null>(null);
  const rafRef = useRef<number | null>(null);
  const dragPosRef = useRef<{ y: number; active: boolean }>({ y: 0, active: false });

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const parent = el.parentElement;
    if (!parent) return;

    const update = (rect: { width: number; height: number }) => {
      setSize({ width: Math.max(0, rect.width), height: Math.max(0, rect.height) });
    };

    update(getContentSize(parent));

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const cr = entry.contentRect;
        update(cr);
      }
    });

    ro.observe(parent);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    let node: HTMLElement | null = ref.current;
    while (node) {
      const style = window.getComputedStyle(node);
      if (
        (style.overflowY === "auto" || style.overflowY === "scroll") &&
        node.scrollHeight > node.clientHeight
      ) {
        scrollRef.current = node;
        break;
      }
      node = node.parentElement;
    }
    if (!scrollRef.current) {
      node = ref.current;
      while (node) {
        const style = window.getComputedStyle(node);
        if (style.overflowY === "auto" || style.overflowY === "scroll") {
          scrollRef.current = node;
          break;
        }
        node = node.parentElement;
      }
    }
  }, [size]);

  useEffect(() => {
    const tick = () => {
      const sc = scrollRef.current;
      const dp = dragPosRef.current;
      if (sc && dp.active) {
        const rect = sc.getBoundingClientRect();
        const edge = 60;
        const top = rect.top + edge;
        const bottom = rect.bottom - edge;
        if (dp.y < top) {
          sc.scrollTop -= 8;
        } else if (dp.y > bottom) {
          sc.scrollTop += 8;
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const handleDrag = useCallback((_layout: Layout[], _oldItem: unknown, _newItem: unknown, _placeholder: unknown, event: MouseEvent) => {
    dragPosRef.current = { y: event.clientY, active: true };
  }, []);

  const handleDragStop = useCallback(() => {
    dragPosRef.current.active = false;
  }, []);

  const rowHeight = Math.max(80, Math.floor((size.height - (maxRows - 1) * 12) / maxRows));

  const Grid = ReactGridLayout as unknown as React.FC<Record<string, unknown>>;

  return (
    <div
      ref={ref}
      className="min-h-full w-full"
      style={{ width: size.width, minHeight: size.height }}
    >
      <Grid
        width={size.width}
        layout={layout}
        onLayoutChange={onLayoutChange}
        onDrag={handleDrag}
        onDragStop={handleDragStop}
        cols={12}
        rowHeight={rowHeight}
        margin={[12, 12]}
        containerPadding={[0, 0]}
        autoSize
        isDraggable
        isResizable
        draggableHandle=".tile-drag-handle"
        draggableCancel=".no-drag,button,a,input,select"
        resizeHandles={["s", "e", "w", "se", "sw"]}
        compactType="vertical"
        preventCollision={false}
      >
        {children}
      </Grid>
    </div>
  );
}

function getContentSize(el: HTMLElement) {
  if (typeof window === "undefined") return { width: 0, height: 0 };
  const rect = el.getBoundingClientRect();
  const style = window.getComputedStyle(el);
  const pl = parseFloat(style.paddingLeft) || 0;
  const pr = parseFloat(style.paddingRight) || 0;
  const pt = parseFloat(style.paddingTop) || 0;
  const pb = parseFloat(style.paddingBottom) || 0;
  const bl = parseFloat(style.borderLeftWidth) || 0;
  const br = parseFloat(style.borderRightWidth) || 0;
  const bt = parseFloat(style.borderTopWidth) || 0;
  const bb = parseFloat(style.borderBottomWidth) || 0;
  return {
    width: Math.max(0, rect.width - pl - pr - bl - br),
    height: Math.max(0, rect.height - pt - pb - bt - bb),
  };
}

export function ResetLayoutButton({
  onClick,
  className,
}: {
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded border border-hairline px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-muted transition-colors hover:border-accent/40 hover:text-accent",
        className
      )}
    >
      <RotateCcw className="h-3 w-3" />
      Reset layout
    </button>
  );
}
