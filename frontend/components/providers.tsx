"use client";

import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnvayaProvider } from "@/lib/store";
import { SidebarProvider } from "@/components/sidebar";
import { AgentProvider } from "@/components/agent/agent-context";
import { AuthProvider } from "@/components/auth/auth-provider";
import { ThemeProvider } from "@/components/theme-provider";
import { StartupedProvider } from "@/components/startuped-provider";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { refetchInterval: 4000, retry: 1, staleTime: 2000 },
  },
});

export function Providers({
  children,
  initialThemeId,
}: {
  children: React.ReactNode;
  initialThemeId?: string;
}) {
  return (
    <QueryClientProvider client={queryClient}>
      <StartupedProvider>
        <AuthProvider>
          <AnvayaProvider>
            <ThemeProvider initialThemeId={initialThemeId}>
              <SidebarProvider>
                <AgentProvider>{children}</AgentProvider>
              </SidebarProvider>
            </ThemeProvider>
          </AnvayaProvider>
        </AuthProvider>
      </StartupedProvider>
    </QueryClientProvider>
  );
}
