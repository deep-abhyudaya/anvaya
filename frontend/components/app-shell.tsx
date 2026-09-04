"use client";

import React from "react";
import { Sidebar, useSidebar } from "./sidebar";
import { TopBar } from "./top-bar";
import { AgentConsole } from "@/components/agent/agent-console";
import { useAgent } from "@/components/agent/agent-context";
import { TextSelectionTooltip } from "@/components/text-selection-tooltip";

interface AppShellProps {
  title: string;
  subtitle?: string;
  live?: boolean;
  center?: React.ReactNode;
  right?: React.ReactNode;
  children: React.ReactNode;
}

export function AppShell({ title, subtitle, live, center, right, children }: AppShellProps) {
  const { width } = useSidebar();
  const { state } = useAgent();
  const consoleWidth = state.open ? state.width : 0;

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-canvas text-primary">
      <Sidebar />
      <TopBar
        title={title}
        subtitle={subtitle}
        live={live}
        center={center}
        right={right}
      />
      <main
        style={{ left: width, right: consoleWidth }}
        className="fixed bottom-0 top-14 overflow-y-auto overflow-x-hidden"
      >
        {children}
      </main>
      <AgentConsole />
      <TextSelectionTooltip />
    </div>
  );
}
