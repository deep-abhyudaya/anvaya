"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-provider";
import { cn } from "@/lib/utils";

export default function SignUpPage() {
  const { signUp } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const { error: err } = await signUp(name, email, password);
    if (err) setError(err);
    setLoading(false);
  };

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-canvas bg-grid">
      <div className="w-full max-w-md rounded-lg border border-hairline bg-canvas-panel p-8 shadow-2xl">
        <h1 className="mb-1 text-center font-mono text-2xl font-semibold uppercase tracking-widest text-primary">
          ANVAYA
        </h1>
        <p className="mb-6 text-center font-mono text-[11px] uppercase tracking-wider text-muted">
          Create your account
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded border border-hairline bg-canvas-subtle px-3 py-2 text-sm text-primary outline-none focus:border-accent"
              required
            />
          </div>
          <div>
            <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
              Email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded border border-hairline bg-canvas-subtle px-3 py-2 text-sm text-primary outline-none focus:border-accent"
              required
            />
          </div>
          <div>
            <label className="mb-1 block font-mono text-[10px] uppercase tracking-wider text-muted">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded border border-hairline bg-canvas-subtle px-3 py-2 text-sm text-primary outline-none focus:border-accent"
              required
              minLength={8}
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
            {loading ? "Creating account..." : "Sign Up"}
          </button>
        </form>

        <p className="mt-4 text-center font-mono text-[11px] text-muted">
          Already have an account?{" "}
          <Link href="/sign-in" className="text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
