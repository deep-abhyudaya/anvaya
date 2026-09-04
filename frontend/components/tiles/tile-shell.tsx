"use client";

import React from "react";
import { Panel, Mono } from "@/components/primitives";
import { cn } from "@/lib/utils";

export interface TileProps {
  id: string;
  title: string;
  subtitle?: string;
  center?: React.ReactNode;
  right?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function Tile({
  id,
  title,
  subtitle,
  center,
  right,
  children,
  className,
}: TileProps) {
  return (
    <section id={id} className="h-full min-h-0 scroll-mt-14">
      <Panel
        className={cn(
          "flex h-full min-h-0 flex-col overflow-hidden",
          className
        )}
      >
        <div className="tile-drag-handle grid shrink-0 cursor-move grid-cols-[1fr_auto_auto] items-center gap-3 border-b border-hairline px-3 py-2">
          <div className="flex min-w-0 items-baseline gap-2">
            <Mono tone="accent" className="truncate">
              {title}
            </Mono>
            {subtitle && (
              <Mono className="hidden truncate text-[9px] normal-case tracking-wider text-muted sm:block">
                {subtitle}
              </Mono>
            )}
          </div>
          {center && (
            <div className="no-drag hidden min-w-0 cursor-default truncate md:block">
              {center}
            </div>
          )}
          {right && <div className="no-drag shrink-0 cursor-default">{right}</div>}
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          <div className="h-full w-full overflow-y-auto overflow-x-hidden">
            {children}
          </div>
        </div>
      </Panel>
    </section>
  );
}

export function TileSkeleton({
  title,
  subtitle,
}: {
  title: string;
  subtitle?: string;
}) {
  return (
    <section className="h-full min-h-0">
      <Panel className="flex h-full min-h-0 flex-col overflow-hidden">
        <div className="flex shrink-0 items-center justify-between border-b border-hairline px-3 py-2">
          <div className="flex min-w-0 flex-1 items-baseline gap-2">
            <Mono tone="accent" className="shrink-0">
              {title}
            </Mono>
            {subtitle && (
              <Mono className="truncate text-[9px] normal-case tracking-wider text-muted">
                {subtitle}
              </Mono>
            )}
          </div>
        </div>
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <Mono className="text-muted">Loading tile...</Mono>
        </div>
      </Panel>
    </section>
  );
}
