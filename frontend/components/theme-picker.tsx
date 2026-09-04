"use client";

import React, { useMemo, useState } from "react";
import { useTheme } from "@/components/theme-provider";
import { Panel, Mono, Tabs } from "@/components/primitives";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

type Category = "all" | "dark" | "light" | "brand";

const CATEGORIES: { key: Category; label: string }[] = [
  { key: "all", label: "ALL" },
  { key: "dark", label: "DARK" },
  { key: "light", label: "LIGHT" },
  { key: "brand", label: "BRAND" },
];

export function ThemePicker() {
  const { themeId, setThemeId, theme, themes } = useTheme();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<Category>("all");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return themes.filter((t) => {
      const matchesQuery = t.name.toLowerCase().includes(q);
      const matchesCategory = category === "all" || t.category === category;
      return matchesQuery && matchesCategory;
    });
  }, [query, category, themes]);

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <Mono tone="accent">current</Mono>
          <div className="mt-1 font-mono text-[11px] uppercase tracking-wider text-primary">
            {theme.name}
          </div>
        </div>
        <div
          className="h-8 w-24 rounded border border-hairline"
          style={{
            background: theme.tokens.bg,
            borderColor: theme.tokens.border,
          }}
        >
          <div
            className="h-full w-full"
            style={{
              background: `linear-gradient(90deg, ${theme.tokens.accent} 0%, ${theme.tokens.accentCool} 50%, ${theme.tokens.textPrimary} 100%)`,
              opacity: 0.9,
            }}
          />
        </div>
      </div>

      <Tabs
        items={CATEGORIES.map((c) => c.label)}
        value={category.toUpperCase()}
        onChange={(v) => {
          const cat = CATEGORIES.find((c) => c.label === v)?.key ?? "all";
          setCategory(cat);
        }}
      />

      <div className="relative">
        <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="filter themes..."
          className="w-full border border-hairline bg-surface-input py-1.5 pl-7 pr-2 font-mono text-[10px] text-primary placeholder:text-muted outline-none focus:border-accent/50"
        />
      </div>

      <Panel className="max-h-[320px] overflow-auto p-2">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {filtered.map((t) => (
            <button
              key={t.id}
              onClick={() => setThemeId(t.id)}
              className={cn(
                "flex items-center gap-3 border px-2 py-2 text-left transition-colors",
                themeId === t.id
                  ? "border-accent/60 bg-accent/[0.08]"
                  : "border-hairline bg-canvas-panel/30 hover:border-accent/40"
              )}
            >
              <div
                className="h-8 w-8 shrink-0 rounded-sm border"
                style={{
                  background: t.tokens.bg,
                  borderColor: t.tokens.border,
                }}
              >
                <div
                  className="h-full w-full"
                  style={{
                    background: `linear-gradient(135deg, ${t.tokens.accent} 0%, ${t.tokens.accentCool} 100%)`,
                    opacity: 0.85,
                  }}
                />
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-[10px] uppercase tracking-wider text-primary">
                  {t.name}
                </div>
                <div className="mt-0.5 font-mono text-[9px] lowercase tracking-wider text-muted">
                  {t.category}
                </div>
              </div>
              {themeId === t.id && (
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
              )}
            </button>
          ))}
        </div>

        {filtered.length === 0 && (
          <div className="py-4 text-center font-mono text-[10px] uppercase tracking-wider text-muted">
            no themes match
          </div>
        )}
      </Panel>
    </div>
  );
}
