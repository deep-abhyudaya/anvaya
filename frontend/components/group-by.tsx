"use client";

import React, { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { GroupByKey } from "@/lib/incidents";

const DEFAULT_OPTIONS: { value: GroupByKey; label: string }[] = [
  { value: "date", label: "Date" },
  { value: "status", label: "Status" },
  { value: "severity", label: "Severity" },
  { value: "none", label: "None" },
];

interface GroupByMenuProps<T extends string = GroupByKey> {
  value: T;
  onChange: (value: T) => void;
  options?: { value: T; label: string }[];
}

export function GroupByMenu<T extends string = GroupByKey>({
  value,
  onChange,
  options,
}: GroupByMenuProps<T>) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const opts = options ?? (DEFAULT_OPTIONS as { value: T; label: string }[]);
  const selected = opts.find((o) => o.value === value) ?? opts[opts.length - 1];

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between rounded-md px-2 py-1 text-[10px] text-muted transition-colors hover:bg-canvas-subtle hover:text-secondary"
      >
        <span className="flex items-center gap-1">
          <span className="uppercase tracking-wider">Group by</span>
          <span className="font-medium text-secondary">{selected?.label}</span>
        </span>
        <ChevronDown
          className={cn("h-3 w-3 transition-transform", open && "rotate-180")}
          strokeWidth={1.5}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.12 }}
            className="absolute left-0 top-full z-[70] mt-1 w-36 rounded border border-hairline bg-canvas-elevated/95 p-1 shadow-lg backdrop-blur"
          >
            {opts.map((opt) => (
              <button
                key={opt.value}
                onClick={() => {
                  onChange(opt.value);
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-[11px] text-secondary transition-colors hover:bg-canvas-subtle"
              >
                <span>{opt.label}</span>
                {value === opt.value && (
                  <Check className="h-3 w-3 text-accent" strokeWidth={2} />
                )}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
