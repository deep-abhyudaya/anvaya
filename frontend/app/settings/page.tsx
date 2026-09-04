"use client";

import React, { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { Dot, Mono, Panel, Segmented } from "@/components/primitives";
import { ThemePicker } from "@/components/theme-picker";
import { HEADER_DEFAULTS } from "@/lib/data";
import { useAnvaya } from "@/lib/store";

export default function SettingsPage() {
  const { state } = useAnvaya();
  const [poll, setPoll] = useState("5s");
  const [reduced, setReduced] = useState("OFF");

  return (
    <AppShell title="SETTINGS" subtitle="soc node configuration">
      <div className="bg-grid h-full overflow-auto p-6">
        <div className="max-w-[640px] space-y-4">
          <Panel className="p-4">
            <Mono tone="accent" className="mb-3 block">
              telemetry
            </Mono>
            <SettingRow label="polling interval" hint="backend probe cadence">
              <select
                aria-label="polling interval"
                value={poll}
                onChange={(e) => setPoll(e.target.value)}
                className="border border-hairline bg-canvas-panel px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-primary outline-none focus:border-accent/50"
              >
                <option value="3s">3s</option>
                <option value="5s">5s</option>
                <option value="10s">10s</option>
              </select>
            </SettingRow>
            <SettingRow label="connectivity" hint="backend reachability probe">
              <span className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wider">
                <Dot tone={state.connected ? "success" : "critical"} pulse={state.connected} />
                <span className={state.connected ? "text-success" : "text-critical"}>
                  {state.connected ? "online" : "offline"}
                </span>
              </span>
            </SettingRow>
          </Panel>

          <Panel className="p-4">
            <Mono tone="accent" className="mb-3 block">
              identity
            </Mono>
            <SettingRow label="analyst id" hint="read-only — assigned by soc">
              <span className="font-mono text-[10px] tracking-wider text-secondary">{HEADER_DEFAULTS.analyst}</span>
            </SettingRow>
            <SettingRow label="soc node" hint="read-only — current node">
              <span className="font-mono text-[10px] tracking-wider text-secondary">{HEADER_DEFAULTS.socNode}</span>
            </SettingRow>
          </Panel>

          <Panel className="p-4">
            <Mono tone="accent" className="mb-3 block">
              display
            </Mono>
            <SettingRow label="reduced motion" hint="dampen pulses and transitions">
              <Segmented items={["ON", "OFF"]} value={reduced} onChange={setReduced} />
            </SettingRow>
            <div className="py-2">
              <div className="font-mono text-[10px] uppercase tracking-wider text-primary">appearance</div>
              <div className="font-mono text-[9px] lowercase tracking-wider text-muted">choose a color theme</div>
              <div className="mt-3">
                <ThemePicker />
              </div>
            </div>
          </Panel>
        </div>
      </div>
    </AppShell>
  );
}

function SettingRow({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-hairline/50 py-2.5 last:border-b-0">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-wider text-primary">{label}</div>
        <div className="font-mono text-[9px] lowercase tracking-wider text-muted">{hint}</div>
      </div>
      {children}
    </div>
  );
}
