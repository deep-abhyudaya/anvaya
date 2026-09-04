"use client";

import React, { useState } from "react";
import { useAuth } from "@/components/auth/auth-provider";
import { cn } from "@/lib/utils";

export default function CreateOrganizationPage() {
  const { createOrganization } = useAuth();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [logo, setLogo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const { error: err } = await createOrganization({
      name,
      slug,
      logo,
    });
    if (err) setError(err);
    setLoading(false);
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-canvas bg-grid">
      <div className="w-full max-w-md rounded-lg border border-hairline bg-canvas-panel p-8 shadow-2xl">
        <h1 className="mb-1 text-center font-mono text-2xl font-semibold uppercase tracking-widest text-primary">
          Create Organization
        </h1>
        <p className="mb-6 text-center font-mono text-[11px] uppercase tracking-wider text-muted">
          Your team workspace in ANVAYA
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
              Organization Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (!slug) {
                  setSlug(
                    e.target.value
                      .toLowerCase()
                      .replace(/\s+/g, "-")
                      .replace(/[^a-z0-9-]/g, "")
                  );
                }
              }}
              className="w-full rounded border border-hairline bg-canvas-subtle px-3 py-2 text-sm text-primary outline-none focus:border-accent"
              required
            />
          </div>
          <div>
            <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
              Slug
            </label>
            <input
              type="text"
              value={slug}
              onChange={(e) => setSlug(e.target.value.replace(/[^a-z0-9-]/g, ""))}
              className="w-full rounded border border-hairline bg-canvas-subtle px-3 py-2 text-sm text-primary outline-none focus:border-accent"
              required
            />
          </div>
          <div>
            <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
              Logo URL (optional)
            </label>
            <input
              type="url"
              value={logo}
              onChange={(e) => setLogo(e.target.value)}
              className="w-full rounded border border-hairline bg-canvas-subtle px-3 py-2 text-sm text-primary outline-none focus:border-accent"
            />
          </div>

          {error && <p className="font-mono text-[11px] text-critical">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className={cn(
              "w-full rounded bg-accent py-2 text-sm font-medium text-black transition-colors hover:bg-accent/90",
              loading && "opacity-50"
            )}
          >
            {loading ? "Creating..." : "Create Organization"}
          </button>
        </form>
      </div>
    </div>
  );
}
