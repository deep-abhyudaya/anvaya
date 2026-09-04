"use client";

import React, { useRef } from "react";
import { useSearchParams } from "next/navigation";
import { Tile } from "@/components/tiles/tile-shell";
import { ProjectGuard } from "@/components/project-guard";
import { Chip, Dot, Mono, Panel, Scrubber, TransportBtn } from "@/components/primitives";
import { useAnvaya, useTicker } from "@/lib/store";
import { clockAt, type ReplayEvent } from "@/lib/data";
import { cn, cssStyle } from "@/lib/utils";
import { useProjectArtifactLatest } from "@/lib/api";
import { type ReplayData, toReplayData, useProjectReplay } from "@/app/miss-replay/use-project-replay";
import { ChevronDown, ChevronLeft, ChevronRight, Pause, Play, SkipBack } from "lucide-react";
import { BuildTimeline, BuildStatus } from "@/components/build/build-timeline";
import { useArtifactBuild } from "@/components/build/use-artifact-build";
import { useArtifactSource } from "@/lib/build";

const SPEEDS = [1, 2, 4];

const STAGE_TONE: Record<string, "muted" | "warning" | "accent"> = {
  "PROCESS SPAWN": "muted",
  MISS: "warning",
  "GROUND TRUTH": "warning",
  "RULE PROPOSED": "warning",
  "RE-RUN": "accent",
  CAUGHT: "accent",
};

const EMPTY_REPLAY: ReplayData = {
  incidentId: "—",
  host: "—",
  user: "—",
  status: "missing",
  verified: false,
  startClock: "00:00:00",
  duration: 0.0001,
  events: [],
  preNote: { at: 0, text: "no replay artifact" },
  stages: ["WAITING"],
};

const AXIS_Y = 60;

function stageAt(t: number, duration: number, stages: readonly string[]) {
  if (duration <= 0 || stages.length === 0) return stages[stages.length - 1] || "CAUGHT";
  const idx = Math.min(stages.length - 1, Math.floor((t / duration) * stages.length));
  return stages[idx];
}

function eventColor(tone: ReplayEvent["tone"]) {
  if (tone === "warning") return "var(--color-warning)";
  if (tone === "accent") return "var(--color-accent)";
  return "var(--color-text-muted)";
}

export default function MissReplayTile() {
  const params = useSearchParams();
  const buildId = params.get("build") || "";
  const build = useArtifactBuild(buildId || undefined);

  const { state, dispatch } = useAnvaya();
  const activeProjectId = state.activeProjectId || "";
  const {
    data: replayPayload,
    isLoading,
    isError,
  } = useProjectArtifactLatest(activeProjectId, "replay");
  const payloadReplays = ((replayPayload?.payload as { replays?: any[] } | null | undefined)?.replays) || [];
  const { data: replays, isBuilding } = useArtifactSource<Record<string, unknown>>(
    build,
    payloadReplays,
    isLoading,
    isError,
    "replay"
  );
  const projectReplayFromReplays = replays.length > 0 ? toReplayData(replays[0]) : null;
  const projectReplayFromLatest = useProjectReplay(activeProjectId);
  const projectReplay = isBuilding
    ? projectReplayFromReplays
    : (projectReplayFromReplays ?? projectReplayFromLatest);
  const replayData = projectReplay ?? EMPTY_REPLAY;

  const replay = state.replay;
  const t = replay.t;

  const tRef = useRef(t);
  tRef.current = t;

  const patch = (value: Partial<typeof replay>) =>
    dispatch({ type: "patch", path: "replay", value });

  const duration = replayData.duration;
  const pct = (v: number) => (v / duration) * 100;
  const endClock = clockAt(replayData.startClock, duration);

  useTicker(replay.playing, replay.speed, (dt) => {
    const nt = tRef.current + dt;
    if (nt >= duration) patch({ t: duration, playing: false });
    else patch({ t: nt });
  });

  const stage = stageAt(t, duration, replayData.stages);
  const currentEvent = [...replayData.events].reverse().find((e) => t >= e.t) ?? null;
  const gtEvent = replayData.events.find((e) => e.label === "ground truth");
  const ruleEvent = replayData.events.find((e) => e.label === "rule proposed");
  const evidenceNote = gtEvent?.sub?.split("—")[1]?.trim();

  const seekTo = (nt: number) => patch({ t: Math.min(duration, Math.max(0, nt)) });

  const stepBack = () => {
    const prev = [...replayData.events].reverse().find((e) => e.t < t - 0.5);
    seekTo(prev ? prev.t : 0);
  };
  const stepForward = () => {
    const next = replayData.events.find((e) => e.t > t + 0.5);
    seekTo(next ? next.t : replayData.duration);
  };
  const togglePlay = () => {
    if (!replay.playing && t >= replayData.duration) patch({ t: 0, playing: true });
    else patch({ playing: !replay.playing });
  };
  const cycleSpeed = () => {
    const i = SPEEDS.indexOf(replay.speed);
    patch({ speed: SPEEDS[(i + 1) % SPEEDS.length] });
  };
  const cycleReplay = () =>
    patch({ replayNo: (replay.replayNo % 3) + 1, t: 0, playing: false });

  const areaRef = useRef<HTMLDivElement>(null);
  const seekFromClientX = (clientX: number) => {
    const el = areaRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    seekTo(((clientX - r.left) / r.width) * replayData.duration);
  };
  const onAreaPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    (e.currentTarget as Element).setPointerCapture(e.pointerId);
    seekFromClientX(e.clientX);
    const move = (ev: PointerEvent) => seekFromClientX(ev.clientX);
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const laneEvents = (lane: "pre" | "post") =>
    replayData.events.filter((e) => e.lane === "both" || e.lane === lane);

  const showBuildShell = isBuilding;

  const center = (
    <div className="flex items-center gap-2">
      <Mono>stage:</Mono>
      <span
        className={cn(
          "font-mono text-[10px] uppercase tracking-widest",
          STAGE_TONE[stage] === "warning" && "text-warning",
          STAGE_TONE[stage] === "accent" && "text-accent",
          STAGE_TONE[stage] === "muted" && "text-muted"
        )}
      >
        {stage}
      </span>
    </div>
  );

  const right = (
    <>
      <button
        type="button"
        onClick={() => patch({ details: !replay.details })}
        className={cn(
          "border px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest transition-colors",
          replay.details
            ? "border-accent/60 text-accent glow-accent"
            : "border-hairline text-muted hover:border-accent/40 hover:text-secondary"
        )}
      >
        details
      </button>
      <span className="flex items-center gap-1.5 border border-hairline px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest text-muted">
        view: timeline <ChevronDown className="h-3 w-3" />
      </span>
    </>
  );

  return (
    <Tile
      id="miss-replay"
      title="MISS REPLAY TRACK"
      subtitle="self-healing timeline scrubber"
      center={center}
      right={right}
    >
      <ProjectGuard>
        {build && <BuildStatus state={build} />}
        {showBuildShell && (
          <div className="h-64 shrink-0 overflow-hidden border-b border-hairline">
            {build && <BuildTimeline state={build} />}
          </div>
        )}
        {showBuildShell && !projectReplay ? (
          <ArtifactState message="Building miss replay workspace..." />
        ) : !projectReplay ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center font-mono text-[11px] text-muted">
              <p className="uppercase tracking-widest text-accent">No replay artifact</p>
              <p className="mt-2">Generate one for this project using the agent.</p>
            </div>
          </div>
        ) : (
          <div className="flex h-full w-full flex-col">
            {}
            <div className="flex items-center justify-between border-b border-hairline px-4 py-1.5">
              <Mono>
                incident: {replayData.incidentId} — {replayData.host} — user: {replayData.user}
              </Mono>
              <Mono className="tabular-nums">
                T+{Math.floor(t)}s / {replayData.duration}s
              </Mono>
            </div>

            {}
            <div className="relative flex min-h-0 flex-1 flex-col">
              {}
              <div className="relative h-[96px] shrink-0 border-b border-hairline">
                <div className="absolute inset-y-0 left-0 flex w-[150px] items-center justify-end border-r border-hairline pr-3">
                  <Mono>event timeline</Mono>
                </div>
                <div className="absolute inset-y-0 left-[150px] right-8">
                  {}
                  <div
                    className="absolute left-0 right-0 h-px bg-hairline-bright"
                    style={{ top: AXIS_Y }}
                  />
                  {}
                  {replayData.events.map((e) => {
                    const isCurrent = currentEvent === e;
                    return (
                      <div
                        key={e.label}
                        className="absolute"
                        style={{ left: `${pct(e.t)}%`, top: AXIS_Y }}
                      >
                        <div className="relative flex h-[18px] w-[18px] -translate-x-1/2 -translate-y-1/2 items-center justify-center">
                          {isCurrent && (
                            <span
                              className="absolute inset-0 rounded-full border"
                              style={{ borderColor: eventColor(e.tone) }}
                            />
                          )}
                          {e.hollow ? (
                            <svg width="11" height="11" className="block">
                              <path
                                d="M5.5 0.5v10M0.5 5.5h10"
                                stroke="var(--color-text-muted)"
                                strokeWidth="1.2"
                              />
                            </svg>
                          ) : e === ruleEvent ? (
                            <svg width="18" height="18" className="block">
                              <circle cx="9" cy="9" r="3" fill="var(--color-warning)" />
                              <circle
                                cx="9"
                                cy="9"
                                r="4"
                                fill="none"
                                stroke="var(--color-warning)"
                                strokeWidth="1"
                                className="pulse-ring"
                                style={cssStyle({ "--pulse-r0": "4px", "--pulse-r1": "8.5px" })}
                              />
                            </svg>
                          ) : (
                            <span
                              className="block h-2 w-2 rounded-full"
                              style={{
                                background: eventColor(e.tone),
                                boxShadow:
                                  e.tone === "accent"
                                    ? "0 0 8px var(--color-accent-glow)"
                                    : e.tone === "warning"
                                      ? "0 0 6px var(--color-warning-glow)"
                                      : undefined,
                              }}
                            />
                          )}
                        </div>
                        {}
                        <div className="absolute left-0 top-2 -translate-x-1/2 whitespace-nowrap font-mono text-[9px] tabular-nums text-muted">
                          {clockAt(replayData.startClock, e.t)}
                        </div>
                      </div>
                    );
                  })}
                  {}
                  {gtEvent && (
                    <span
                      className="absolute -translate-x-full whitespace-nowrap pr-2 font-mono text-[9px] uppercase tracking-wider text-warning"
                      style={{ left: `${pct(gtEvent.t)}%`, top: 26 }}
                    >
                      {gtEvent.label} / {gtEvent.sub?.split("—")[0]?.trim()}
                    </span>
                  )}
                  {ruleEvent && (
                    <span
                      className="absolute whitespace-nowrap pl-2 font-mono text-[9px] uppercase tracking-wider text-warning"
                      style={{ left: `${pct(ruleEvent.t)}%`, top: 8 }}
                    >
                      {ruleEvent.label} / {ruleEvent.sub}
                    </span>
                  )}
                  {replayData.events.filter((e) => e.tone === "accent").map((e) => (
                    <span
                      key={e.label}
                      className="absolute -translate-x-full whitespace-nowrap pr-2 font-mono text-[9px] uppercase tracking-wider text-accent"
                      style={{ left: `${pct(e.t)}%`, top: 26 }}
                    >
                      {e.label}
                    </span>
                  ))}
                </div>
              </div>

              {}
              {(["pre", "post"] as const).map((lane) => (
                <div
                  key={lane}
                  className={cn(
                    "relative min-h-[64px] flex-1",
                    lane === "pre" && "border-b border-hairline"
                  )}
                >
                  <div className="absolute inset-y-0 left-0 flex w-[150px] flex-col justify-center gap-0.5 border-r border-hairline px-3">
                    <Mono tone={lane === "post" ? "accent" : "muted"}>
                      {lane === "pre" ? "PRE-PATCH" : "POST-PATCH"}
                    </Mono>
                    <span className="font-mono text-[9px] text-muted">
                      {lane === "pre" ? "(before fix)" : "(after fix)"}
                    </span>
                  </div>
                  <div className="absolute inset-y-0 left-[150px] right-8">
                    <div className="absolute left-0 right-0 top-1/2 h-px -translate-y-1/2 bg-hairline-bright" />
                    {laneEvents(lane).map((e) => {
                      const reached = t >= e.t;
                      const isCurrent = currentEvent === e;
                      return (
                        <div
                          key={e.label}
                          className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 transition-opacity duration-200"
                          style={{ left: `${pct(e.t)}%`, opacity: reached ? 1 : 0.3 }}
                        >
                          <span
                            className={cn(
                              "block h-2 w-2 rounded-full",
                              isCurrent && "ring-1 ring-offset-1 ring-offset-canvas"
                            )}
                            style={cssStyle(
                              { "--tw-ring-color": eventColor(e.tone) },
                              {
                                background: eventColor(e.tone),
                                boxShadow:
                                  e.tone === "accent" && reached
                                    ? "0 0 10px var(--color-accent-glow)"
                                    : undefined,
                              }
                            )}
                          />
                        </div>
                      );
                    })}
                    {lane === "pre" && (
                      <span
                        className="absolute top-1/2 -translate-y-1/2 whitespace-nowrap font-mono text-[9px] uppercase tracking-wider text-muted"
                        style={{ left: `${pct(replayData.preNote.at)}%` }}
                      >
                        {replayData.preNote.text}
                      </span>
                    )}
                  </div>
                </div>
              ))}

              {}
              <div
                ref={areaRef}
                onPointerDown={onAreaPointerDown}
                className="absolute inset-y-0 left-[150px] right-8 cursor-ew-resize touch-none"
              >
                {ruleEvent && (
                  <div
                    className="absolute bottom-0 top-0 border-l border-dashed border-warning/40"
                    style={{ left: `${pct(ruleEvent.t)}%` }}
                  />
                )}
                {gtEvent && t >= gtEvent.t && evidenceNote && (
                  <span
                    className="pointer-events-none absolute -translate-x-1/2 whitespace-nowrap border border-warning/40 bg-canvas-panel px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-warning"
                    style={{ left: `${pct(gtEvent.t)}%`, top: 104 }}
                  >
                    {evidenceNote}
                  </span>
                )}
                {}
                <div
                  className="pointer-events-none absolute bottom-0 top-0 w-px bg-accent shadow-[0_0_8px_var(--color-accent-glow)]"
                  style={{ left: `${pct(t)}%` }}
                />
                <span
                  className="pointer-events-none absolute top-1 whitespace-nowrap font-mono text-[9px] tabular-nums text-accent"
                  style={{ left: `calc(${pct(t)}% + 6px)` }}
                >
                  {clockAt(replayData.startClock, t)}
                </span>
              </div>

              {}
              {replay.details && (
                <aside className="absolute bottom-3 right-3 top-3 z-20 w-[320px] overflow-y-auto">
                  <Panel glow="accent" className="bg-canvas-elevated/95 p-3 backdrop-blur-sm">
                    <div className="flex items-center justify-between">
                      <Mono tone="accent">event detail</Mono>
                      <Mono>{replayData.incidentId}</Mono>
                    </div>
                    <div className="mt-2 divide-y divide-hairline/50">
                      {replayData.events.map((e, i) => {
                        const reached = t >= e.t;
                        return (
                          <div
                            key={e.label}
                            className="flex items-center gap-2 py-1.5 font-mono text-[10px]"
                          >
                            <Dot
                              tone={reached ? e.tone : "muted"}
                              pulse={currentEvent === e}
                              className={reached ? undefined : "opacity-40"}
                            />
                            <div className="min-w-0 flex-1">
                              <div
                                className={cn(
                                  "uppercase tracking-wider",
                                  reached ? "text-primary" : "text-muted"
                                )}
                              >
                                {e.label}
                              </div>
                              <div className="text-[9px] uppercase text-muted">
                                {replayData.stages[i] ?? e.label} — lane: {e.lane}
                              </div>
                            </div>
                            <span className="tabular-nums text-muted">
                              {clockAt(replayData.startClock, e.t)}
                            </span>
                            <Chip tone={reached ? (e.tone === "muted" ? "muted" : e.tone) : "muted"}>
                              {reached ? "reached" : "pending"}
                            </Chip>
                          </div>
                        );
                      })}
                    </div>
                  </Panel>
                </aside>
              )}
            </div>

            {}
            <div className="flex items-center gap-3 border-t border-hairline bg-canvas-elevated/60 px-4 py-2.5">
              <Mono>replay controls</Mono>
              <div className="flex items-center gap-1">
                <TransportBtn label="rewind to start" onClick={() => seekTo(0)}>
                  <SkipBack className="h-3 w-3" />
                </TransportBtn>
                <TransportBtn label="step back" onClick={stepBack}>
                  <ChevronLeft className="h-3 w-3" />
                </TransportBtn>
                <TransportBtn
                  label={replay.playing ? "pause" : "play"}
                  active={replay.playing}
                  onClick={togglePlay}
                >
                  {replay.playing ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                </TransportBtn>
                <TransportBtn label="step forward" onClick={stepForward}>
                  <ChevronRight className="h-3 w-3" />
                </TransportBtn>
              </div>
              <button
                type="button"
                onClick={cycleReplay}
                className="border border-hairline px-2.5 py-1 font-mono text-[10px] uppercase tracking-widest text-muted transition-colors hover:border-accent/40 hover:text-accent"
              >
                REPLAY {replay.replayNo} of 3
              </button>
              <Scrubber
                label="replay scrubber"
                value={t / replayData.duration}
                onChange={(v) => patch({ t: v * replayData.duration })}
                markers={replayData.events.map((e) => ({ at: e.t / replayData.duration, tone: e.tone }))}
              />
              <span className="whitespace-nowrap font-mono text-[10px] tabular-nums text-secondary">
                {clockAt(replayData.startClock, t)} / {endClock}
              </span>
              <button
                type="button"
                onClick={cycleSpeed}
                className="border border-hairline px-2.5 py-1 font-mono text-[10px] tabular-nums text-muted transition-colors hover:border-accent/40 hover:text-accent"
              >
                {replay.speed.toFixed(1)}x
              </button>
            </div>
          </div>
        )}
      </ProjectGuard>
    </Tile>
  );
}

function ArtifactState({ message }: { message: string }) {
  return <div className="flex h-full items-center justify-center p-8 text-center"><Mono className="text-muted">{message}</Mono></div>;
}
