"use client";

import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, FolderPlus, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { AnvayaAPI } from "@/lib/api";

interface CreateProjectDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function CreateProjectDialog({
  open,
  onClose,
  onSuccess,
}: CreateProjectDialogProps) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);
  const [mounted, setMounted] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    setName("");
    setDescription("");
    setError(null);
    const id = setTimeout(() => inputRef.current?.focus(), 60);
    return () => clearTimeout(id);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("A project name is required.");
      return;
    }
    setIsPending(true);
    try {
      const project = (await AnvayaAPI.createProject({
        name: trimmed,
        description,
      })) as { project_id: string };
      onSuccess?.();
      onClose();
      router.push(`/projects/${project.project_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project.");
    } finally {
      setIsPending(false);
    }
  };

  if (!mounted) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-lg border border-hairline bg-canvas-elevated/95 p-6 shadow-2xl backdrop-blur"
          >
            <div className="mb-5 flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent-dim text-accent">
                <FolderPlus
                  className="h-5 w-5"
                  strokeWidth={1.5}
                />
              </div>
              <div className="min-w-0">
                <h2 className="text-[15px] font-semibold text-primary">
                  Create New Project
                </h2>
                <p className="text-[12px] text-muted">
                  Give your project or incident a name to get started.
                </p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="ml-auto rounded-md p-1 text-muted transition-colors hover:text-primary"
                aria-label="Close"
              >
                <X className="h-4 w-4" strokeWidth={1.5} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-[11px] uppercase tracking-wider text-muted">
                  Project Name
                </label>
                <input
                  ref={inputRef}
                  type="text"
                  value={name}
                  onChange={(e) => {
                    setName(e.target.value);
                    if (error) setError(null);
                  }}
                  placeholder="Enter project name..."
                  className={cn(
                    "w-full rounded-md border bg-canvas-subtle px-3 py-2.5 text-[13px] text-primary outline-none transition-colors placeholder:text-muted",
                    error ? "border-critical" : "border-hairline focus:border-accent"
                  )}
                />
                {error && (
                  <p className="mt-1.5 text-[10px] text-critical">{error}</p>
                )}
              </div>

              <div>
                <label className="mb-1.5 block text-[11px] uppercase tracking-wider text-muted">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(e) => {
                    setDescription(e.target.value);
                    if (error) setError(null);
                  }}
                  placeholder="Optional description..."
                  rows={3}
                  className={cn(
                    "w-full rounded-md border bg-canvas-subtle px-3 py-2.5 text-[13px] text-primary outline-none transition-colors placeholder:text-muted",
                    error ? "border-critical" : "border-hairline focus:border-accent"
                  )}
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-1">
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-md border border-hairline px-4 py-2 text-[11px] font-medium text-secondary transition-colors hover:bg-canvas-subtle"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isPending}
                  className="flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-[11px] font-medium text-black transition-colors hover:bg-accent/90 disabled:opacity-50"
                >
                  {isPending ? "Creating..." : "Create Project"}
                  <ArrowRight
                    className="h-3.5 w-3.5"
                    strokeWidth={2}
                  />
                </button>
              </div>
            </form>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body as HTMLElement
  );
}
