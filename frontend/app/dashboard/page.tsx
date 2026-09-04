"use client";

import { useState } from "react";
import { DashboardLayout } from "@/components/dashboard/DashboardLayout";
import { DashboardHeader } from "@/components/dashboard/DashboardHeader";
import { StatCard } from "@/components/dashboard/StatCard";
import { ChartSection } from "@/components/dashboard/ChartSection";
import { BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { AnvayaAPI } from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { Shield, AlertTriangle, Activity, Users, Sparkles } from "lucide-react";

export default function DashboardPage() {
  const { state } = useAnvaya();
  const projectId = state.activeProjectId || "";
  const [prompt, setPrompt] = useState("");
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const build = useArtifactBuild(executionId || undefined);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || !projectId) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = (await AnvayaAPI.createBuildSession(projectId, { prompt: prompt.trim() })) as {
        execution_id: string;
        generation_id: string;
        target: string;
      };
      setExecutionId(result.execution_id);
    } catch (err: any) {
      setError(err?.detail || "Failed to start build");
    } finally {
      setSubmitting(false);
    }
  };

  const stats = [
    { label: "Incidents", value: 42, change: "+12%", icon: Shield, color: "text-accent" },
    { label: "Alerts", value: 128, change: "-5%", icon: AlertTriangle, color: "text-warning" },
    { label: "Events", value: "8.4k", change: "+8%", icon: Activity, color: "text-emerald-500" },
    { label: "Assets", value: 96, change: "+2%", icon: Users, color: "text-violet-500" },
  ];

  return (
    <DashboardLayout>
      <DashboardHeader title="SOC Dashboard" subtitle="Real-time visibility into your security posture" />

      <section className="p-4">
        <form onSubmit={handleSubmit} className="flex max-w-2xl flex-col gap-3 rounded border border-hairline bg-canvas-subtle p-4">
          <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-accent">
            <Sparkles className="h-3.5 w-3.5" />
            Ask ANVAYA to build
          </div>
          <input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder='Try "Make Orbits"'
            className="h-10 border border-hairline bg-canvas px-3 text-sm text-primary outline-none placeholder:text-muted focus:border-accent/40"
          />
          <button
            type="submit"
            disabled={submitting || !prompt.trim() || !projectId}
            className="h-9 border border-accent/40 bg-accent/10 px-4 text-xs font-medium text-accent hover:bg-accent/20 disabled:opacity-50"
          >
            {submitting ? "Starting..." : "Build"}
          </button>
          {error && <div className="text-[10px] text-rose-500">{error}</div>}
        </form>
      </section>

      {executionId && build && <BuildStatus state={build} />}

      <section className="grid gap-4 p-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <StatCard
            key={stat.label}
            label={stat.label}
            value={stat.value}
            change={stat.change}
            icon={stat.icon}
            color={stat.color}
          />
        ))}
      </section>

      <section className="p-4">
        <ChartSection />
      </section>
    </DashboardLayout>
  );
}
