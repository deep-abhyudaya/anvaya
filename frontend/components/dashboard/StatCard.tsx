"use client";

import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

export function StatCard({
  label,
  value,
  change,
  icon: Icon,
  color,
  className,
}: {
  label: string;
  value: string | number;
  change: string;
  icon: LucideIcon;
  color: string;
  className?: string;
}) {
  const isPositive = change.startsWith("+") || !change.startsWith("-");
  return (
    <article className={cn("rounded border border-hairline bg-canvas-subtle p-4", className)}>
      <div className="flex items-center justify-between">
        <span className="text-sm text-secondary">{label}</span>
        <Icon className={cn("h-4 w-4", color)} />
      </div>
      <div className="mt-2 flex items-end gap-2">
        <span className="text-2xl font-semibold text-primary">{value}</span>
        <span className={cn("mb-1 text-xs", isPositive ? "text-emerald-500" : "text-rose-500")}>{change}</span>
      </div>
    </article>
  );
}
