"use client";

import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from "react";
import { THEMES, DEFAULT_THEME_ID, getTheme, applyTheme } from "@/lib/themes";

export { THEMES, DEFAULT_THEME_ID };

interface ThemeContextValue {
  themeId: string;
  setThemeId: (id: string) => void;
  theme: (typeof THEMES)[number];
  themes: typeof THEMES;
}

const ThemeCtx = createContext<ThemeContextValue | null>(null);

const STORAGE_KEY = "anvaya-theme";
const COOKIE_NAME = "anvaya-theme";

function writeCookie(name: string, value: string) {
  const maxAge = 60 * 60 * 24 * 365;
  try {
    document.cookie = `${name}=${encodeURIComponent(value)};path=/;max-age=${maxAge};SameSite=Lax`;
  } catch {
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function readStorage(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function writeStorage(id: string) {
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
  }
}

export function ThemeProvider({
  children,
  initialThemeId,
}: {
  children: ReactNode;
  initialThemeId?: string;
}) {
  const resolved = (id?: string | null) => (id && getTheme(id) ? id : DEFAULT_THEME_ID);
  const [themeId, setThemeIdState] = useState<string>(resolved(initialThemeId));

  const applyAndPersist = useCallback((id: string) => {
    const safe = resolved(id);
    applyTheme(safe);
    setThemeIdState(safe);
    writeStorage(safe);
    writeCookie(COOKIE_NAME, safe);
  }, []);

  useEffect(() => {
    const saved = readStorage() || readCookie(COOKIE_NAME);
    const id = resolved(saved);
    if (id !== themeId) applyAndPersist(id);
  }, [applyAndPersist, themeId]);

  const theme = getTheme(themeId) ?? getTheme(DEFAULT_THEME_ID)!;

  return (
    <ThemeCtx.Provider
      value={{ themeId, setThemeId: applyAndPersist, theme, themes: THEMES }}
    >
      {children}
    </ThemeCtx.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeCtx);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
