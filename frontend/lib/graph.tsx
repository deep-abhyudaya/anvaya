"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Maximize, Minus, Plus, RotateCcw } from "lucide-react";
import { cn } from "@/lib/utils";

export interface GNode {
  id: string;
  x: number;
  y: number;
}
export interface GEdge {
  from: string;
  to: string;
}

export interface Transform { k: number; tx: number; ty: number }

interface GraphCanvasProps<N extends GNode, E extends GEdge> {
  nodes: N[];
  edges?: E[];
  viewW: number;
  viewH: number;
  positions?: Record<string, { x: number; y: number }>;
  onNodePos?: (id: string, pos: { x: number; y: number }) => void;
  selected?: string | null;
  hovered?: string | null;
  onSelect?: (id: string | null) => void;
  onHover?: (id: string | null) => void;
  renderNode: (n: N, ctx: NodeCtx) => React.ReactNode;
  renderEdge?: (e: E, ctx: EdgeCtx) => React.ReactNode;
  renderOverlay?: (ctx: { pos: (id: string) => { x: number; y: number } }) => React.ReactNode;
  className?: string;
  toolbar?: boolean;
  padding?: number;
  ariaLabel?: string;
}

export interface NodeCtx {
  pos: { x: number; y: number };
  selected: boolean;
  hovered: boolean;
  dragging: boolean;
  k: number;
  dragProps: React.SVGAttributes<SVGGElement>;
}
export interface EdgeCtx {
  from: { x: number; y: number };
  to: { x: number; y: number };
  active: boolean;
  dimmed: boolean;
}

export function GraphCanvas<N extends GNode, E extends GEdge>(props: GraphCanvasProps<N, E>) {
  const {
    nodes, edges = [], viewW, viewH, positions = {}, onNodePos,
    selected = null, hovered: hoveredExt, onSelect, onHover,
    renderNode, renderEdge, renderOverlay, className, toolbar = true, padding = 60, ariaLabel,
  } = props;

  const svgRef = useRef<SVGSVGElement>(null);
  const [t, setT] = useState<Transform | null>(null);
  const [hoveredInt, setHoveredInt] = useState<string | null>(null);
  const hovered = hoveredExt !== undefined ? hoveredExt : hoveredInt;
  const setHovered = onHover ?? setHoveredInt;

  const dragRef = useRef<{
    mode: "pan" | "node";
    id?: string;
    startX: number; startY: number;
    origTx: number; origTy: number;
    nodeX: number; nodeY: number;
    moved: boolean;
  } | null>(null);

  const posOf = useCallback(
    (id: string) => positions[id] ?? nodes.find((n) => n.id === id) ?? { x: 0, y: 0 },
    [positions, nodes]
  );

  const fit = useCallback(() => {
    const el = svgRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const k = Math.min((r.width - padding * 2) / viewW, (r.height - padding * 2) / viewH);
    setT({ k, tx: (r.width - viewW * k) / 2, ty: (r.height - viewH * k) / 2 });
  }, [viewW, viewH, padding]);

  useEffect(() => { if (t === null) fit(); }, [t, fit]);

  const interacted = useRef(false);
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => { if (!interacted.current) fit(); });
    ro.observe(el);
    return () => ro.disconnect();
  }, [fit]);

  const zoomAt = useCallback((clientX: number, clientY: number, factor: number) => {
    const el = svgRef.current;
    if (!el || !t) return;
    const r = el.getBoundingClientRect();
    const px = clientX - r.left, py = clientY - r.top;
    const k = Math.min(4, Math.max(0.25, t.k * factor));
    setT({ k, tx: px - ((px - t.tx) / t.k) * k, ty: py - ((py - t.ty) / t.k) * k });
    interacted.current = true;
  }, [t]);

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.12 : 1 / 1.12);
  }, [zoomAt]);

  const onBgPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0 || !t) return;
    (e.target as Element).setPointerCapture?.(e.pointerId);
    dragRef.current = { mode: "pan", startX: e.clientX, startY: e.clientY, origTx: t.tx, origTy: t.ty, nodeX: 0, nodeY: 0, moved: false };
  };

  const nodeDragProps = useCallback((id: string): React.SVGAttributes<SVGGElement> => ({
    onPointerDown: (e) => {
      if (e.button !== 0 || !t) return;
      e.stopPropagation();
      (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
      const p = posOf(id);
      dragRef.current = { mode: "node", id, startX: e.clientX, startY: e.clientY, origTx: 0, origTy: 0, nodeX: p.x, nodeY: p.y, moved: false };
    },
    onPointerEnter: () => setHovered(id),
    onPointerLeave: () => setHovered(null),
    onClick: (e) => { e.stopPropagation(); onSelect?.(id); },
    tabIndex: 0,
    role: "button",
    "aria-label": `node ${id}`,
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect?.(id); }
      if (["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key) && onNodePos) {
        e.preventDefault();
        const p = posOf(id);
        const d = 12;
        onNodePos(id, {
          x: p.x + (e.key === "ArrowRight" ? d : e.key === "ArrowLeft" ? -d : 0),
          y: p.y + (e.key === "ArrowDown" ? d : e.key === "ArrowUp" ? -d : 0),
        });
      }
    },
  }), [t, posOf, onSelect, onNodePos, setHovered]);

  const [draggingId, setDraggingId] = useState<string | null>(null);

  const onPointerMove = (e: React.PointerEvent) => {
    const d = dragRef.current;
    if (!d || !t) return;
    const dx = e.clientX - d.startX, dy = e.clientY - d.startY;
    if (!d.moved && Math.hypot(dx, dy) < 4) return;
    d.moved = true;
    interacted.current = true;
    if (d.mode === "pan") {
      setT({ ...t, tx: d.origTx + dx, ty: d.origTy + dy });
    } else if (d.mode === "node" && d.id && onNodePos) {
      setDraggingId(d.id);
      onNodePos(d.id, { x: d.nodeX + dx / t.k, y: d.nodeY + dy / t.k });
    }
  };

  const onPointerUp: React.PointerEventHandler<SVGSVGElement> = () => {
    const d = dragRef.current;
    dragRef.current = null;
    setDraggingId(null);
    if (d && !d.moved && d.mode === "pan") onSelect?.(null);
  };

  const tt = t ?? { k: 1, tx: 0, ty: 0 };

  return (
    <div className={cn("relative h-full w-full select-none overflow-hidden", className)}>
      <svg
        ref={svgRef}
        className="h-full w-full cursor-grab touch-none active:cursor-grabbing"
        onWheel={onWheel}
        onPointerDown={onBgPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        role="application"
        aria-label={ariaLabel ?? "interactive graph"}
      >
        <g transform={`translate(${tt.tx},${tt.ty}) scale(${tt.k})`}>
          {renderEdge && edges.map((edge, i) => {
            const from = posOf(edge.from), to = posOf(edge.to);
            const touchesSelection = !!selected && (edge.from === selected || edge.to === selected);
            return (
              <React.Fragment key={`${edge.from}->${edge.to}-${i}`}>
                {renderEdge(edge, { from, to, active: touchesSelection, dimmed: !!selected && !touchesSelection })}
              </React.Fragment>
            );
          })}
          {nodes.map((n, i) => {
            const p = posOf(n.id);
            return (
              <React.Fragment key={`${n.id}-${i}`}>
                {renderNode(n, {
                  pos: p,
                  selected: selected === n.id,
                  hovered: hovered === n.id,
                  dragging: draggingId === n.id,
                  k: tt.k,
                  dragProps: nodeDragProps(n.id),
                })}
              </React.Fragment>
            );
          })}
          {renderOverlay?.({ pos: posOf })}
        </g>
      </svg>

      {toolbar && (
        <div className="absolute bottom-3 left-3 z-10 flex items-center gap-1 opacity-60 transition-opacity hover:opacity-100">
          <ToolBtn label="zoom in" onClick={() => { const r = svgRef.current!.getBoundingClientRect(); zoomAt(r.left + r.width / 2, r.top + r.height / 2, 1.25); }}><Plus className="h-3 w-3" /></ToolBtn>
          <ToolBtn label="zoom out" onClick={() => { const r = svgRef.current!.getBoundingClientRect(); zoomAt(r.left + r.width / 2, r.top + r.height / 2, 0.8); }}><Minus className="h-3 w-3" /></ToolBtn>
          <ToolBtn label="fit to view" onClick={() => { interacted.current = false; fit(); }}><Maximize className="h-3 w-3" /></ToolBtn>
          <ToolBtn label="reset zoom" onClick={() => { interacted.current = false; fit(); }}><RotateCcw className="h-3 w-3" /></ToolBtn>
          <span className="ml-1 text-[9px] tabular-nums text-muted">{Math.round(tt.k * 100)}%</span>
        </div>
      )}
    </div>
  );
}

function ToolBtn({ children, onClick, label }: { children: React.ReactNode; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="flex h-6 w-6 items-center justify-center border border-hairline bg-canvas-elevated text-muted transition-colors hover:border-accent/40 hover:text-accent focus-visible:outline focus-visible:outline-1 focus-visible:outline-accent"
    >
      {children}
    </button>
  );
}
