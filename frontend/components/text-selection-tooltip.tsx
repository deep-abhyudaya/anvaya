"use client";

import React, { useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { useAgent } from "@/components/agent/agent-context";

export function TextSelectionTooltip() {
  const { state, dispatch } = useAgent();
  const [selection, setSelection] = useState("");
  const [position, setPosition] = useState<{ x: number; y: number } | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleSelection = () => {
      const sel = window.getSelection();
      const text = sel?.toString().trim() || "";

      if (!text || text.length < 2) {
        setSelection("");
        setPosition(null);
        return;
      }

      if (!sel || sel.rangeCount === 0) return;

      const range = sel.getRangeAt(0);

      let node: Node | null = range.commonAncestorContainer;
      while (node && node !== document.body) {
        if (node instanceof HTMLElement) {
          if (
            node.tagName === "ASIDE" ||
            node.getAttribute("aria-label") === "Agent console" ||
            node.getAttribute("aria-label") === "primary"
          ) {
            setSelection("");
            setPosition(null);
            return;
          }
        }
        node = node.parentNode;
      }

      const rect = range.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top - 8;
      setSelection(text);
      setPosition({ x, y });
    };

    const onMouseUp = () => {
      setTimeout(handleSelection, 10);
    };

    const onMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (tooltipRef.current?.contains(target)) return;
      setSelection("");
      setPosition(null);
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelection("");
        setPosition(null);
        window.getSelection()?.removeAllRanges();
      }
    };

    document.addEventListener("mouseup", onMouseUp);
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mouseup", onMouseUp);
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, []);

  if (!selection || !position) return null;

  const label = selection.length > 60 ? `${selection.slice(0, 60)}…` : selection;

  return (
    <div
      ref={tooltipRef}
      style={{ left: position.x, top: position.y }}
      className="fixed z-[100] -translate-x-1/2 -translate-y-full rounded border border-hairline bg-canvas-panel px-2 py-1.5 shadow-lg"
    >
      <button
        onClick={() => {
          const activeIsChat = state.events.some(
            (e) => e.execution_id === state.executionId && e.type === "chat.user"
          );
          if (!activeIsChat) {
            dispatch({ type: "resetEvents" });
            dispatch({ type: "setExecutionId", value: undefined });
          }
          dispatch({ type: "setContextText", value: selection });
          dispatch({ type: "setMode", value: "chat" });
          dispatch({ type: "setOpen", value: true });
          setSelection("");
          setPosition(null);
          window.getSelection()?.removeAllRanges();
        }}
        className="flex items-center gap-1.5 text-[10px] text-accent transition-colors hover:text-primary"
      >
        <Plus className="h-3 w-3" strokeWidth={1.5} />
        <span className="max-w-[200px] truncate">Add to agent: {label}</span>
      </button>
    </div>
  );
}
