"use client";

import React, { useState } from "react";
import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth/auth-provider";
import { AnvayaAPI } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function OrganizationSettingsPage() {
  const { activeOrganization, organizations, setActiveOrganization } = useAuth();
  const [name, setName] = useState(activeOrganization?.name || "");
  const [slug, setSlug] = useState(activeOrganization?.slug || "");
  const [logo, setLogo] = useState(activeOrganization?.logo || "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeOrganization) return;
    setSaving(true);
    setError(null);
    try {
      await AnvayaAPI.updateOrganization(activeOrganization.id, {
        name,
        slug,
        logo,
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppShell title="Organization" subtitle="Settings">
      <div className="h-full overflow-auto bg-canvas p-6">
        <div className="mb-6 rounded border border-hairline bg-canvas-panel p-5">
          <h2 className="mb-4 font-mono text-sm font-semibold uppercase tracking-widest text-primary">
            Active Organization
          </h2>
          <div className="space-y-3">
            {organizations.map((org) => (
              <button
                key={org.id}
                onClick={() => setActiveOrganization(org.id)}
                className={cn(
                  "flex w-full items-center justify-between rounded border px-3 py-2 font-mono text-[11px] text-left transition-colors",
                  activeOrganization?.id === org.id
                    ? "border-accent/40 bg-accent-dim text-accent"
                    : "border-hairline bg-canvas-subtle text-primary hover:bg-canvas-elevated"
                )}
              >
                <span>{org.name}</span>
                <span className="text-[10px] uppercase text-muted">{org.role}</span>
              </button>
            ))}
          </div>
        </div>

        {activeOrganization && (
          <form
            onSubmit={handleSave}
            className="rounded border border-hairline bg-canvas-panel p-5"
          >
            <h2 className="mb-4 font-mono text-sm font-semibold uppercase tracking-widest text-primary">
              Branding
            </h2>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
                  Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded border border-hairline bg-canvas-subtle px-3 py-2 text-sm text-primary outline-none focus:border-accent"
                />
              </div>
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
                  Slug
                </label>
                <input
                  type="text"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  className="w-full rounded border border-hairline bg-canvas-subtle px-3 py-2 text-sm text-primary outline-none focus:border-accent"
                />
              </div>
              <div>
                <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
                  Logo URL
                </label>
                <input
                  type="url"
                  value={logo}
                  onChange={(e) => setLogo(e.target.value)}
                  className="w-full rounded border border-hairline bg-canvas-subtle px-3 py-2 text-sm text-primary outline-none focus:border-accent"
                />
              </div>
            </div>

            {error && <p className="mt-4 font-mono text-[11px] text-critical">{error}</p>}

            <button
              type="submit"
              disabled={saving}
              className={cn(
                "mt-6 rounded bg-accent px-4 py-2 font-mono text-[11px] font-medium uppercase text-black hover:bg-accent/90",
                saving && "opacity-50"
              )}
            >
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </form>
        )}
      </div>
    </AppShell>
  );
}
