"use client";

import React, { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { LogOut } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSidebar } from "./sidebar";
import { useAuth } from "@/components/auth/auth-provider";
import { AgentConsoleTrigger } from "@/components/agent/agent-console";

interface TopBarProps {
  title: string;
  subtitle?: string;
  center?: React.ReactNode;
  right?: React.ReactNode;
  live?: boolean;
}

function UserDropdown() {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { user, signOut, activeOrganization } = useAuth();

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  if (!mounted || !user) return null;

  const name = user.name || user.email;
  const linkText = activeOrganization
    ? `${activeOrganization.name} / ${user.email}`
    : user.email;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label="User menu"
        className={cn(
          "group flex h-8 max-w-[140px] items-center gap-1.5 rounded border border-hairline bg-canvas-elevated/60 px-2.5 text-secondary transition-colors hover:border-accent/60 hover:text-accent",
          open && "border-accent/60 text-accent"
        )}
      >
        <span className="truncate text-[11px] font-medium">{name}</span>
      </button>

      {open && (
        <div
          className="absolute right-0 top-full z-50 mt-1.5 w-56 rounded border border-hairline bg-canvas-panel/95 p-2 shadow-lg backdrop-blur-sm"
          role="menu"
        >
          <div className="border-b border-hairline px-2 pb-2">
            <div
              className="truncate text-[12px] font-medium text-primary"
              title={user.name || user.email}
            >
              {user.name || user.email}
            </div>
          </div>

          <div className="py-1">
            <Link
              href="/organization"
              className="block truncate px-2 py-1.5 font-mono text-[10px] uppercase tracking-wider text-accent transition-colors hover:text-accent/80"
              title="Organization"
              role="menuitem"
            >
              {linkText}
            </Link>
          </div>

          <div className="border-t border-hairline pt-1">
            <button
              type="button"
              onClick={() => signOut()}
              className="flex w-full items-center gap-2 px-2 py-1.5 font-mono text-[10px] uppercase tracking-wider text-muted transition-colors hover:text-critical"
              role="menuitem"
            >
              <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function TopBar({ title, right }: TopBarProps) {
  const { width } = useSidebar();

  return (
    <header
      style={{ left: width }}
      className="fixed right-0 top-0 z-30 flex h-14 items-center justify-between border-b border-hairline bg-canvas-elevated/60 px-5 backdrop-blur-sm transition-[left] duration-200"
    >
      <div className="flex min-w-0 items-baseline gap-3">
        <h1 className="whitespace-nowrap font-mono text-[13px] font-medium uppercase tracking-[0.18em] text-primary">
          {title}
        </h1>
      </div>

      <div className="relative flex items-center gap-3">
        {right && <div className="flex items-center gap-3">{right}</div>}
        <UserDropdown />
        <AgentConsoleTrigger />
      </div>
    </header>
  );
}
