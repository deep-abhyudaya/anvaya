"use client";

import { cn } from "@/lib/utils";

export function DashboardHeader({ title, subtitle, className }: { title: string; subtitle?: string; className?: string }) {
  return (
    <header className={cn("border-b border-hairline bg-canvas-subtle p-4", className)}>
      <h1 className="text-lg font-semibold text-primary">{title}</h1>
      {subtitle ? <p className="text-sm text-secondary">{subtitle}</p> : null}
    </header>
  );
}
