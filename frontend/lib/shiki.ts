"use client";

import { createHighlighterCoreSync } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import githubDark from "@shikijs/themes/github-dark";

import bash from "@shikijs/langs/bash";
import c from "@shikijs/langs/c";
import cpp from "@shikijs/langs/cpp";
import csharp from "@shikijs/langs/csharp";
import css from "@shikijs/langs/css";
import diff from "@shikijs/langs/diff";
import dockerfile from "@shikijs/langs/dockerfile";
import go from "@shikijs/langs/go";
import html from "@shikijs/langs/html";
import http from "@shikijs/langs/http";
import ini from "@shikijs/langs/ini";
import java from "@shikijs/langs/java";
import javascript from "@shikijs/langs/javascript";
import json from "@shikijs/langs/json";
import jsx from "@shikijs/langs/jsx";
import markdown from "@shikijs/langs/markdown";
import php from "@shikijs/langs/php";
import powershell from "@shikijs/langs/powershell";
import python from "@shikijs/langs/python";
import ruby from "@shikijs/langs/ruby";
import rust from "@shikijs/langs/rust";
import scss from "@shikijs/langs/scss";
import sql from "@shikijs/langs/sql";
import toml from "@shikijs/langs/toml";
import tsx from "@shikijs/langs/tsx";
import typescript from "@shikijs/langs/typescript";
import yaml from "@shikijs/langs/yaml";

const THEME_NAME = "github-dark";

const highlighter = createHighlighterCoreSync({
  themes: [githubDark],
  langs: [
    bash,
    c,
    cpp,
    csharp,
    css,
    diff,
    dockerfile,
    go,
    html,
    http,
    ini,
    java,
    javascript,
    json,
    jsx,
    markdown,
    php,
    powershell,
    python,
    ruby,
    rust,
    scss,
    sql,
    toml,
    tsx,
    typescript,
    yaml,
  ],
  engine: createJavaScriptRegexEngine(),
});

const LOADED_LANGS = new Set([
  "bash",
  "c",
  "cpp",
  "csharp",
  "css",
  "diff",
  "dockerfile",
  "go",
  "html",
  "http",
  "ini",
  "java",
  "javascript",
  "json",
  "jsx",
  "markdown",
  "php",
  "powershell",
  "python",
  "ruby",
  "rust",
  "scss",
  "sql",
  "toml",
  "tsx",
  "typescript",
  "yaml",
]);

const LANG_ALIASES: Record<string, string> = {
  py: "python",
  py3: "python",
  python3: "python",
  js: "javascript",
  node: "javascript",
  ts: "typescript",
  jsx: "jsx",
  tsx: "tsx",
  sh: "bash",
  shell: "bash",
  zsh: "bash",
  yml: "yaml",
  jsonc: "json",
  "c#": "csharp",
  cs: "csharp",
  "c++": "cpp",
  cpp: "cpp",
  py2: "python",
  javascriptreact: "jsx",
  typescriptreact: "tsx",
  ps: "powershell",
  ps1: "powershell",
  docker: "dockerfile",
  md: "markdown",
  mdwn: "markdown",
  mkd: "markdown",
  golang: "go",
};

export function resolveLang(raw?: string): string | undefined {
  if (!raw) return undefined;
  const lower = raw.toLowerCase().trim();
  const mapped = LANG_ALIASES[lower] || lower;
  if (LOADED_LANGS.has(mapped)) return mapped;
  return undefined;
}

export function highlightCode(code: string, lang?: string): string | null {
  const resolved = resolveLang(lang);
  if (!resolved) return null;
  try {
    const html = highlighter.codeToHtml(code, { lang: resolved, theme: THEME_NAME });
    return html;
  } catch (err) {
    console.warn("Shiki highlight failed", { lang: resolved, err });
    return null;
  }
}

export { highlighter, THEME_NAME };
