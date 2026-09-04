"use client";

import React, { useEffect } from "react";
import Link from "next/link";
import { FolderPlus, Upload } from "lucide-react";
import { useProjects } from "@/lib/api";
import { useAnvaya } from "@/lib/store";
import { Mono } from "@/components/primitives";

export function ProjectGuard({ children }: { children: React.ReactNode }) {
  const { state, dispatch } = useAnvaya();
  const { data: projectsData, isLoading } = useProjects();
  const projects = React.useMemo(
    () => (projectsData?.items || []) as { project_id: string; name: string }[],
    [projectsData?.items]
  );
  const activeId = state.activeProjectId;
  const activeProject = projects.find((p) => p.project_id === activeId);

  useEffect(() => {
    if (!activeId && projects.length > 0) {
      dispatch({
        type: "set-active-project",
        value: projects[0].project_id,
      });
    }
  }, [activeId, projects, dispatch]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Mono className="text-muted">Loading projects...</Mono>
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-canvas">
        <div className="w-full max-w-md rounded border border-hairline bg-canvas-panel p-6 text-center shadow-lg">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-accent-dim text-accent">
            <FolderPlus className="h-5 w-5" strokeWidth={1.5} />
          </div>
          <h2 className="mt-4 font-mono text-sm font-semibold uppercase tracking-widest text-primary">
            No project yet
          </h2>
          <p className="mt-2 font-mono text-[11px] leading-relaxed text-muted">
            Create a project and upload data to get started.
          </p>
          <Link
            href="/projects"
            className="mt-4 inline-flex items-center gap-2 rounded bg-accent px-4 py-2 font-mono text-[11px] font-medium text-black transition-colors hover:bg-accent/90"
          >
            <Upload className="h-3.5 w-3.5" />
            Go to Projects
          </Link>
        </div>
      </div>
    );
  }

  if (!activeProject) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-canvas">
        <div className="w-full max-w-md rounded border border-hairline bg-canvas-panel p-6 text-center shadow-lg">
          <h2 className="font-mono text-sm font-semibold uppercase tracking-widest text-primary">
            Select a project
          </h2>
          <p className="mt-2 font-mono text-[11px] leading-relaxed text-muted">
            Choose a project to view this page.
          </p>
          <Link
            href="/projects"
            className="mt-4 inline-flex items-center gap-2 rounded border border-hairline px-4 py-2 font-mono text-[11px] uppercase tracking-widest text-secondary transition-colors hover:border-accent/40 hover:text-accent"
          >
            View projects
          </Link>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
