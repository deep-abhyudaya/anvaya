"use client";

import { cn } from "@/lib/utils";
import { ReactNode } from "react";

export function DashboardLayout({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("min-h-screen bg-canvas text-primary", className)}>
      <DashboardSidebar />
      <main className="lg:pl-64">
        <div className="min-h-screen border-l border-hairline">{children}</div>
      </main>
    </div>
  );
}

function DashboardSidebar() {
  const items = ["Overview", "Incidents", "Alerts", "Assets", "Reports"];
  return (
    <aside className="fixed left-0 top-0 z-30 hidden h-screen w-64 flex-col border-r border-hairline bg-canvas-subtle lg:flex">
      <div className="flex h-14 items-center border-b border-hairline px-4 font-semibold text-accent">
        ANVAYA
      </div>
      <nav className="flex-1 p-2">
        <ul className="space-y-1">
          {items.map((item) => (
            <li key={item}>
              <button className="w-full rounded px-3 py-2 text-left text-sm text-secondary hover:bg-canvas hover:text-accent">
                {item}
              </button>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}
