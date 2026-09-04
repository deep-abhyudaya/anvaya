"use client";

import React, { useState } from "react";
import Link from "next/link";
import { FolderPlus } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CreateProjectDialog } from "@/components/create-project-dialog";
import { useAuth } from "@/components/auth/auth-provider";
import { useProjects } from "@/lib/api";

export default function ProjectsPage() {
  const { activeOrganization } = useAuth();
  const { data, isLoading, refetch } = useProjects();
  const [showCreate, setShowCreate] = useState(false);

  const projects = (data?.items || []) as {
    project_id: string;
    name: string;
    description: string;
    created_at: string;
  }[];

  return (
    <AppShell
      title="Projects"
      subtitle={activeOrganization?.name || "No organization"}
    >
      <div className="h-full overflow-auto bg-canvas p-6">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="font-mono text-sm font-semibold uppercase tracking-widest text-primary">
              Workspaces
            </h2>
            <p className="font-mono text-[11px] text-muted">
              Projects isolate datasets, generations, and artifacts for one domain.
            </p>
          </div>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 rounded border border-hairline bg-canvas-panel px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-accent transition-colors hover:bg-canvas-subtle"
          >
            <FolderPlus className="h-3.5 w-3.5" />
            New Project
          </button>
        </div>

        {isLoading ? (
          <p className="font-mono text-[11px] text-muted">Loading projects...</p>
        ) : projects.length === 0 ? (
          <div className="rounded border border-dashed border-hairline bg-canvas-panel p-8 text-center">
            <p className="font-mono text-sm text-secondary">No projects yet.</p>
            <p className="mt-1 font-mono text-[11px] text-muted">
              Create a project to start generating attack scenarios and datasets.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {projects.map((p) => (
              <Link
                key={p.project_id}
                href={`/projects/${p.project_id}`}
                className="group rounded border border-hairline bg-canvas-panel p-5 transition-colors hover:border-accent/40"
              >
                <h3 className="font-mono text-sm font-medium text-primary group-hover:text-accent">
                  {p.name}
                </h3>
                <p className="mt-1 line-clamp-2 font-mono text-[11px] text-muted">
                  {p.description || "No description"}
                </p>
                <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-muted">
                  ID: {p.project_id}
                </p>
              </Link>
            ))}
          </div>
        )}

        <CreateProjectDialog
          open={showCreate}
          onClose={() => setShowCreate(false)}
          onSuccess={() => refetch()}
        />
      </div>
    </AppShell>
  );
}
