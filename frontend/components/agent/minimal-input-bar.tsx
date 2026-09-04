"use client";

import React, { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Plus, Square, X, Zap } from "lucide-react";
import Image from "next/image";
import { useAgent } from "./agent-context";
import { ModelSelector } from "./model-explorer";
import { cn } from "@/lib/utils";

function AutoResizeTextarea({
  value,
  onChange,
  onSubmit,
  placeholder,
  className,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      disabled={disabled}
      aria-label="Message input"
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          onSubmit();
        }
      }}
      placeholder={placeholder}
      className={cn(
        "min-h-[24px] w-full resize-none overflow-y-auto bg-transparent px-0 py-0 text-[13px] leading-5 text-primary placeholder:text-muted/70 outline-none ring-0",
        className
      )}
      style={{ height: "auto" }}
    />
  );
}

function ModeToggle({ state, dispatch }: { state: { mode: "agentic" | "chat" }; dispatch: React.Dispatch<any> }) {
  const active = state.mode === "chat";
  const [rotation, setRotation] = useState(0);

  return (
    <motion.button
      layout
      type="button"
      onClick={() => {
        setRotation((r) => r + 1440);
        dispatch({ type: "setMode", value: active ? "agentic" : "chat" });
      }}
      title={active ? "Switch to Agent mode" : "Switch to Ask mode"}
      className={cn(
        "relative flex h-7 items-center gap-1.5 rounded-full px-1.5 text-[10px] font-medium transition-colors",
        active
          ? "text-primary"
          : "text-muted hover:text-primary hover:bg-canvas-subtle"
      )}
      style={{ originX: 0, backgroundColor: active ? "var(--color-canvas-panel)" : undefined }}
      transition={{ type: "spring", stiffness: 500, damping: 32 }}
    >
      <motion.div
        animate={{ rotate: rotation }}
        transition={{ type: "spring", stiffness: 300, damping: 20 }}
      >
        <Zap className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
      </motion.div>
      <AnimatePresence mode="popLayout" initial={false}>
        {active && (
          <motion.span
            key="ask-label"
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 12 }}
            transition={{ type: "spring", stiffness: 500, damping: 32 }}
            className="whitespace-nowrap pr-1"
          >
            Ask
          </motion.span>
        )}
      </AnimatePresence>
    </motion.button>
  );
}

export function MinimalInputBar({
  value,
  onChange,
  onSubmit,
  onImageSelect,
  onCancel,
  images,
  onRemoveImage,
  running,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onImageSelect: (files: FileList) => void;
  onCancel?: () => void;
  images: string[];
  onRemoveImage: (index: number) => void;
  running: boolean;
  disabled: boolean;
}) {
  const { state, dispatch } = useAgent();
  const fileRef = useRef<HTMLInputElement>(null);

  const hasContent = value.trim().length > 0;
  const placeholder = state.mode === "chat" ? "Ask anything..." : "Investigate current incident...";

  return (
    <div className="space-y-2">
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2 px-1">
          {images.map((img, i) => (
            <div key={i} className="relative h-10 w-10 overflow-hidden rounded border border-hairline">
              <Image src={img} alt="" fill className="object-cover" sizes="40px" />
              <button
                onClick={() => onRemoveImage(i)}
                className="absolute right-0 top-0 flex h-3 w-3 items-center justify-center bg-black/60 text-[8px] text-white"
              >
                <X className="h-2.5 w-2.5" strokeWidth={2} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        className={cn(
          "rounded-[22px] border bg-canvas-subtle/80 p-3 transition-all",
          "border-hairline/60 focus-within:border-accent/40 focus-within:bg-canvas-subtle focus-within:ring-1 focus-within:ring-accent/20"
        )}
      >
        <AutoResizeTextarea
          value={value}
          onChange={onChange}
          onSubmit={onSubmit}
          placeholder={placeholder}
          disabled={disabled}
        />

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <input
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              ref={fileRef}
              onChange={(e) => {
                if (e.target.files) {
                  onImageSelect(e.target.files);
                  e.target.value = "";
                }
              }}
            />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              title="Attach image"
              className="flex h-7 w-7 items-center justify-center rounded-full text-muted transition-colors hover:bg-canvas-subtle hover:text-primary"
            >
              <Plus className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>

            <ModelSelector />
            <ModeToggle state={state} dispatch={dispatch} />
          </div>

          {running && onCancel ? (
            <button
              type="button"
              onClick={onCancel}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-critical text-primary transition-colors hover:bg-critical/90"
            >
              <Square className="h-3.5 w-3.5 fill-current" strokeWidth={2} />
            </button>
          ) : (
            <button
              type="button"
              onClick={onSubmit}
              disabled={(!value.trim() && !state.contextText) || disabled}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
                hasContent
                  ? "bg-accent text-primary hover:bg-accent/90"
                  : "bg-canvas-subtle text-muted hover:text-primary"
              )}
            >
              <ArrowRight className="h-3.5 w-3.5" strokeWidth={2} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
