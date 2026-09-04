"use client";

import { useMutation } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { AnvayaAPI } from "@/lib/api";

export function DemoButton({ onRun }: { onRun?: () => void }) {
  const mutation = useMutation({
    mutationFn: AnvayaAPI.demo,
    onSuccess: () => {
      onRun?.();
    },
  });

  return (
    <button
      onClick={() => mutation.mutate()}
      disabled={mutation.isPending}
      className="flex items-center gap-2 rounded border border-warning bg-warning-dim px-3 py-1.5 text-[10px] uppercase tracking-wider text-warning transition-colors hover:bg-warning hover:text-black disabled:opacity-50"
    >
      <Play className="h-3 w-3" />
      {mutation.isPending ? "Running..." : "Run Self-Correction Demo"}
    </button>
  );
}
