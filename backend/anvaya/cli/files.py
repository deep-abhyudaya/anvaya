"""Local file tooling for the ANVAYA interactive CLI."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_IGNORE = {
    ".git",
    ".github",
    ".venv",
    ".env",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".next",
    "build",
    "dist",
    ".ruff_cache",
    ".DS_Store",
    "*.pyc",
    "*.pyo",
    "*.egg-info",
}


def resolve_workspace_path(input_path: str, workspace: Path) -> Path:
    """Resolve a user-supplied path against the workspace root.

    Raises ``ValueError`` if the resolved path escapes the workspace or
    points to a sensitive location.
    """
    input_path = input_path.strip()
    workspace = workspace.resolve()

    if input_path.startswith("~/"):
        candidate = Path.home() / input_path[2:]
    else:
        candidate = Path(input_path)

    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (workspace / input_path).resolve()

    try:
        resolved.relative_to(workspace)
    except ValueError:
        raise ValueError(f"Path escapes workspace: {input_path}")

    sensitive = {"/etc", "/proc", "/sys", "/dev", "/var/log"}
    for parent in resolved.parents:
        if any(str(parent).startswith(s) for s in sensitive):
            raise ValueError(f"Access denied: {input_path}")
    return resolved


def _is_ignored(path: Path, workspace: Path) -> bool:
    """Return True for ignored names and gitignore-style patterns we can cheaply match."""
    name = path.name
    if name in DEFAULT_IGNORE:
        return True
    if any(path.match(pattern) for pattern in DEFAULT_IGNORE if pattern.startswith("*")):
        return True
    return False


def _try_read(path: Path, encoding: str = "utf-8") -> str | None:
    try:
        with open(path, "r", encoding=encoding) as f:
            return f.read()
    except (UnicodeDecodeError, OSError):
        return None


def read_file(
    input_path: str,
    workspace: Path,
    line_start: int = 1,
    line_end: int = 0,
    max_lines: int = 200,
    max_bytes: int = 128_000,
) -> dict[str, Any]:
    """Read a text file from the workspace with bounded size and line ranges."""
    resolved = resolve_workspace_path(input_path, workspace)
    if not resolved.is_file():
        raise FileNotFoundError(f"File not found: {input_path}")

    if resolved.stat().st_size > max_bytes:
        raise ValueError(
            f"File too large ({resolved.stat().st_size} bytes). Use a line range to read a portion."
        )

    text = _try_read(resolved, encoding="utf-8")
    if text is None:
        text = _try_read(resolved, encoding="latin-1") or ""

    all_lines = text.splitlines()
    total = len(all_lines)

    end = line_end or (line_start + max_lines - 1)
    if end > total:
        end = total
    if line_start < 1:
        line_start = 1
    if end < line_start:
        end = line_start

    selected = all_lines[line_start - 1 : end]
    if line_start == 1 and end == total:
        summary = f"{total} lines"
    else:
        summary = f"lines {line_start}-{end} of {total}"

    return {
        "path": str(resolved.relative_to(workspace)),
        "lines": selected,
        "start": line_start,
        "end": end,
        "total": total,
        "summary": summary,
    }


def parse_line_range(input_path: str) -> tuple[str, int, int]:
    """Parse ``path:1-120`` and ``path 1 120`` syntax into (path, start, end)."""
    if ":" in input_path and " " not in input_path.split(":")[0]:
        head, _, range_spec = input_path.rpartition(":")
        if head:
            if "-" in range_spec:
                parts = range_spec.split("-")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    return head, int(parts[0]), int(parts[1])
            elif range_spec.isdigit():
                return head, int(range_spec), 0

    tokens = input_path.split()
    if len(tokens) >= 3 and tokens[-2].isdigit() and tokens[-1].isdigit():
        return " ".join(tokens[:-2]), int(tokens[-2]), int(tokens[-1])
    if len(tokens) == 2 and tokens[-1].isdigit():
        return tokens[0], int(tokens[1]), 0

    return input_path, 1, 0


def build_tree(input_path: str, workspace: Path, max_depth: int = 6) -> dict[str, Any]:
    """Build a concise directory tree, honoring ignore rules."""
    resolved = resolve_workspace_path(input_path, workspace)
    if resolved.is_file():
        return {
            "path": str(resolved.relative_to(workspace)),
            "lines": [resolved.name],
        }

    lines: list[str] = []

    def _walk(root: Path, prefix: str = "", depth: int = 0) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(
                [p for p in root.iterdir() if not _is_ignored(p, workspace)],
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                _walk(entry, prefix + extension, depth + 1)

    _walk(resolved)
    return {
        "path": str(resolved.relative_to(workspace)),
        "lines": lines,
    }


def search_text(
    query: str,
    workspace: Path,
    scope: str = "",
    max_results: int = 40,
) -> list[dict[str, Any]]:
    """Search the workspace for ``query`` using ripgrep when available."""
    target = workspace if not scope else resolve_workspace_path(scope, workspace)
    if not target.is_dir():
        raise ValueError(f"Search scope is not a directory: {scope or workspace}")

    try:
        cmd = [
            "rg",
            "--fixed-strings",
            "--line-number",
            "--no-heading",
            "--with-filename",
            "--max-columns=160",
            "--max-count=5",
            "--glob=!.git",
            "--glob=!node_modules",
            "--glob=!__pycache__",
            "--glob=!.venv",
            "--glob=!*.pyc",
            "-e",
            query,
            str(target),
        ]
        raw = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=30)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        raw = ""

    results: list[dict[str, Any]] = []
    if raw:
        for line in raw.splitlines()[:max_results]:
            if ":" not in line:
                continue
            file, rest = line.split(":", 1)
            if ":" not in rest:
                continue
            ln, text = rest.split(":", 1)
            rel = Path(file).relative_to(workspace) if file.startswith(str(workspace)) else file
            results.append({"file": str(rel), "line": int(ln), "text": text.strip()})

    if not results:
        results = _search_fallback(query, target, workspace, max_results)

    return results


def _search_fallback(
    query: str,
    target: Path,
    workspace: Path,
    max_results: int,
) -> list[dict[str, Any]]:
    """Slow but safe text search when ripgrep is unavailable."""
    results: list[dict[str, Any]] = []
    query_lower = query.lower()
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if not _is_ignored(Path(root) / d, workspace)]
        for filename in files:
            path = Path(root) / filename
            if _is_ignored(path, workspace):
                continue
            if path.stat().st_size > 1_000_000:
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, start=1):
                        if query_lower in line.lower():
                            rel = path.relative_to(workspace)
                            results.append(
                                {"file": str(rel), "line": i, "text": line.strip()[:120]}
                            )
                            if len(results) >= max_results:
                                return results
            except OSError:
                continue
    return results


def extract_at_refs(text: str) -> list[str]:
    """Return ``@path`` references from a natural-language message."""
    import re

    refs: list[str] = []
    for match in re.finditer(r"@([A-Za-z0-9_./~\-]+)", text):
        refs.append(match.group(1))
    return refs
