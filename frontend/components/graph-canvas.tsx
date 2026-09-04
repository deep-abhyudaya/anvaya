"use client";

import React, { useEffect, useRef } from "react";
import { useTheme } from "@/components/theme-provider";

interface Node {
  id: string;
  label: string;
  x: number;
  y: number;
  kind?: string;
  status?: string;
}

interface Edge {
  from: string;
  to: string;
  kind?: string;
}

interface Pin {
  id: string;
  x: number;
  y: number;
}

interface GraphCanvasProps {
  nodes: Node[];
  edges: Edge[];
  pins: Pin[];
  onNodeClick: (nodeId: string) => void;
  onNodeHover: (nodeId: string | null) => void;
}

const NODE_RADIUS = 20;
const LABEL_PAD = 12;
const LABEL_GAP = 8;

function drawNodeLabel(
  ctx: CanvasRenderingContext2D,
  node: Node,
  maxWidth: number
) {
  if (maxWidth <= 10) return;

  const style = getComputedStyle(document.documentElement);
  ctx.fillStyle = style.getPropertyValue("--color-text-primary").trim();
  ctx.font = "10px JetBrains Mono, monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";

  const text = node.label;
  const measured = ctx.measureText(text).width;
  if (measured <= maxWidth) {
    ctx.fillText(text, node.x, node.y + NODE_RADIUS + LABEL_GAP);
    return;
  }

  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi + 1) / 2);
    const candidate = text.slice(0, mid) + "…";
    if (ctx.measureText(candidate).width <= maxWidth) lo = mid;
    else hi = mid - 1;
  }

  const display = lo > 0 ? text.slice(0, lo) + "…" : "…";
  if (display) ctx.fillText(display, node.x, node.y + NODE_RADIUS + LABEL_GAP);
}

function buildMaxWidths(
  ctx: CanvasRenderingContext2D,
  canvasWidth: number,
  nodes: Node[]
): Map<string, number> {
  const map = new Map<string, number>();
  const byRow = new Map<number, Node[]>();

  nodes.forEach((n) => {
    const row = Math.round(n.y / 30) * 30;
    if (!byRow.has(row)) byRow.set(row, []);
    byRow.get(row)!.push(n);
  });

  byRow.forEach((row) => {
    row.sort((a, b) => a.x - b.x);
    row.forEach((node, i) => {
      const prev = row[i - 1];
      const next = row[i + 1];

      const leftHalf = prev
        ? (node.x - prev.x) / 2 - LABEL_PAD / 2
        : node.x - LABEL_PAD / 2;
      const rightHalf = next
        ? (next.x - node.x) / 2 - LABEL_PAD / 2
        : canvasWidth - node.x - LABEL_PAD / 2;

      const half = Math.max(0, Math.min(leftHalf, rightHalf));
      map.set(node.id, half * 2);
    });
  });

  return map;
}

export function GraphCanvas({
  nodes,
  edges,
  pins,
  onNodeClick,
  onNodeHover,
}: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const { themeId } = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const style = getComputedStyle(document.documentElement);
    const textSecondary = style.getPropertyValue("--color-text-secondary").trim();
    const textMuted = style.getPropertyValue("--color-text-muted").trim();
    const surface = style.getPropertyValue("--color-surface").trim();
    const surfaceHover = style.getPropertyValue("--color-surface-hover").trim();
    const bgElevated = style.getPropertyValue("--color-bg-elevated").trim();
    const bg = style.getPropertyValue("--color-bg").trim();
    const accent = style.getPropertyValue("--color-accent").trim();
    const warning = style.getPropertyValue("--color-warning").trim();

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const cssWidth = container.clientWidth;
      const cssHeight = container.clientHeight;

      canvas.width = Math.floor(cssWidth * dpr);
      canvas.height = Math.floor(cssHeight * dpr);
      canvas.style.width = `${cssWidth}px`;
      canvas.style.height = `${cssHeight}px`;

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.scale(dpr, dpr);

      edges.forEach((edge) => {
        const fromNode = nodes.find((n) => n.id === edge.from);
        const toNode = nodes.find((n) => n.id === edge.to);
        if (!fromNode || !toNode) return;

        ctx.beginPath();
        ctx.moveTo(fromNode.x, fromNode.y);
        ctx.lineTo(toNode.x, toNode.y);
        ctx.strokeStyle = edge.kind === "incident" ? warning : textMuted;
        ctx.lineWidth = edge.kind === "incident" ? 2 : 1;
        if (edge.kind === "incident") {
          ctx.setLineDash([5, 5]);
        } else {
          ctx.setLineDash([]);
        }
        ctx.stroke();
        ctx.setLineDash([]);
      });

      pins.forEach((pin) => {
        ctx.beginPath();
        ctx.arc(pin.x, pin.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = accent;
        ctx.fill();
      });

      const maxWidths = buildMaxWidths(ctx, cssWidth, nodes);

      nodes.forEach((node) => {
        ctx.beginPath();
        ctx.arc(node.x, node.y, NODE_RADIUS, 0, Math.PI * 2);

        let fillColor = surface;
        let strokeColor = textMuted;

        if (node.kind === "active" || node.status === "active") {
          fillColor = accent;
          strokeColor = accent;
        } else if (node.kind === "proposed" || node.status === "proposed") {
          fillColor = surfaceHover;
          strokeColor = textSecondary;
        } else if (node.kind === "transitioning") {
          fillColor = bgElevated;
          strokeColor = accent;
        } else if (node.kind === "dead") {
          fillColor = bg;
          strokeColor = textMuted;
        }

        ctx.fillStyle = fillColor;
        ctx.fill();
        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 2;
        ctx.stroke();

        drawNodeLabel(ctx, node, maxWidths.get(node.id) ?? cssWidth);
      });
    };

    const resizeCanvas = () => draw();

    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);

    return () => {
      window.removeEventListener("resize", resizeCanvas);
    };
  }, [nodes, edges, pins, themeId]);

  const getNodeAt = (x: number, y: number) => {
    for (const node of nodes) {
      const distance = Math.sqrt((x - node.x) ** 2 + (y - node.y) ** 2);
      if (distance <= NODE_RADIUS) return node;
    }
    return null;
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const node = getNodeAt(x, y);
    onNodeHover(node?.id ?? null);
  };

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const node = getNodeAt(x, y);
    if (node) onNodeClick(node.id);
  };

  return (
    <div ref={containerRef} className="h-full w-full">
      <canvas
        ref={canvasRef}
        className="h-full w-full"
        onMouseMove={handleMouseMove}
        onClick={handleClick}
      />
    </div>
  );
}
