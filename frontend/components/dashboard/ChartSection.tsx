"use client";

import { cn } from "@/lib/utils";
import { useState } from "react";
import { useTheme } from "@/components/theme-provider";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const data = [
  { time: "00:00", incidents: 2, alerts: 12 },
  { time: "04:00", incidents: 5, alerts: 18 },
  { time: "08:00", incidents: 3, alerts: 24 },
  { time: "12:00", incidents: 8, alerts: 32 },
  { time: "16:00", incidents: 6, alerts: 28 },
  { time: "20:00", incidents: 4, alerts: 20 },
];

export function ChartSection({ className }: { className?: string }) {
  const [metric, setMetric] = useState<"incidents" | "alerts">("incidents");
  const { theme } = useTheme();
  const t = theme.tokens;

  return (
    <article className={cn("rounded border border-hairline bg-canvas-subtle p-4", className)}>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-semibold text-primary">Trends</h2>
        <div className="flex gap-2">
          <button
            onClick={() => setMetric("incidents")}
            className={cn(
              "rounded px-2 py-1 text-xs",
              metric === "incidents" ? "bg-accent/20 text-accent" : "text-secondary hover:text-primary"
            )}
          >
            Incidents
          </button>
          <button
            onClick={() => setMetric("alerts")}
            className={cn(
              "rounded px-2 py-1 text-xs",
              metric === "alerts" ? "bg-warning/20 text-warning" : "text-secondary hover:text-primary"
            )}
          >
            Alerts
          </button>
        </div>
      </div>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id="colorMetric" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={t.accent} stopOpacity={0.3} />
                <stop offset="95%" stopColor={t.accent} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={t.textMuted} />
            <XAxis dataKey="time" stroke={t.textSecondary} fontSize={12} tickLine={false} axisLine={false} />
            <YAxis stroke={t.textSecondary} fontSize={12} tickLine={false} axisLine={false} />
            <Tooltip
              contentStyle={{ backgroundColor: t.surface, border: `1px solid ${t.border}` }}
              itemStyle={{ color: t.textPrimary }}
              labelStyle={{ color: t.textSecondary }}
            />
            <Area
              type="monotone"
              dataKey={metric}
              stroke={t.accent}
              fillOpacity={1}
              fill="url(#colorMetric)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </article>
  );
}
