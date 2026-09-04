"""Persistent CLI session state and workspace context."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anvaya.config import settings

_STATE_DIR = Path.home() / ".config" / "anvaya"
_STATE_FILE = _STATE_DIR / "cli.json"

_SECRET_PREFIXES = (
    "/set-key",
    "/api-key",
    "/token",
    "/secret",
)


@dataclass
class CLIState:
    """In-memory and on-disk CLI session state."""

    project_id: str = ""
    project_name: str = ""
    incident_id: str = ""
    model_id: str = ""
    model_display: str = ""
    model_provider: str = ""
    profile_id: str = "sentinel"
    active_execution_id: str = ""
    file_contexts: list[dict[str, Any]] = field(default_factory=list)
    search_context: str = ""
    search_results: list[dict[str, Any]] = field(default_factory=list)
    recent_commands: list[str] = field(default_factory=list)
    debug: bool = False
    mode: str = "agentic"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable state snapshot with no secrets."""
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "incident_id": self.incident_id,
            "model_id": self.model_id,
            "model_display": self.model_display,
            "model_provider": self.model_provider,
            "profile_id": self.profile_id,
            "active_execution_id": self.active_execution_id,
            "file_contexts": self.file_contexts,
            "search_context": self.search_context,
            "search_results": self.search_results[-20:],
            "recent_commands": self.recent_commands[-50:],
            "debug": self.debug,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CLIState:
        """Load from a previously saved state dict."""
        return cls(
            project_id=data.get("project_id", ""),
            project_name=data.get("project_name", ""),
            incident_id=data.get("incident_id", ""),
            model_id=data.get("model_id", ""),
            model_display=data.get("model_display", ""),
            model_provider=data.get("model_provider", ""),
            profile_id=data.get("profile_id", "sentinel"),
            active_execution_id=data.get("active_execution_id", ""),
            file_contexts=data.get("file_contexts", []),
            search_context=data.get("search_context", ""),
            search_results=data.get("search_results", []),
            recent_commands=data.get("recent_commands", []),
            debug=data.get("debug", False),
            mode=data.get("mode", "agentic"),
        )

    def save(self) -> None:
        """Persist state to ``~/.config/anvaya/cli.json``."""
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        os.chmod(_STATE_FILE, 0o600)

    @classmethod
    def load(cls) -> CLIState:
        """Load previously saved state or return a default."""
        if _STATE_FILE.exists():
            try:
                with open(_STATE_FILE) as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return cls.from_dict(data)
            except (json.JSONDecodeError, OSError):
                pass
        return cls()

    @property
    def workspace_root(self) -> Path:
        """Return the repository workspace root."""
        return Path(settings.base_dir).resolve()

    def add_command(self, command: str) -> None:
        """Append a command to recent history unless it carries secrets."""
        command = command.strip()
        if not command:
            return
        if any(command.lower().startswith(p) for p in _SECRET_PREFIXES):
            return
        lower = command.lower()
        if "key" in lower and ("=" in command or "sk-" in lower or "api" in lower):
            return
        self.recent_commands.append(command)
        self.recent_commands = self.recent_commands[-50:]

    def set_project(self, project_id: str, project_name: str = "") -> None:
        self.project_id = project_id
        self.project_name = project_name or project_id
        self.save()

    def set_model(self, model: dict[str, Any]) -> None:
        self.model_id = model.get("id", "")
        self.model_display = model.get("display_name", "")
        self.model_provider = model.get("provider", "")
        self.save()

    def set_profile(self, profile_id: str) -> None:
        self.profile_id = profile_id
        self.save()

    def set_incident(self, incident_id: str) -> None:
        self.incident_id = incident_id
        self.save()

    def set_active_execution(self, execution_id: str) -> None:
        self.active_execution_id = execution_id
        self.save()

    def add_file_context(
        self, path: str, start: int, end: int, snippet: str, full_size: int
    ) -> None:
        """Add a file context entry and trim the working set."""
        self.file_contexts = [c for c in self.file_contexts if c.get("path") != path]
        self.file_contexts.append(
            {
                "path": path,
                "start": start,
                "end": end,
                "snippet_len": len(snippet),
                "full_size": full_size,
            }
        )
        self.file_contexts = self.file_contexts[-5:]

    def remove_file_context(self, path: str) -> None:
        self.file_contexts = [c for c in self.file_contexts if c.get("path") != path]

    def clear_file_context(self) -> None:
        self.file_contexts = []

    def clear_search_context(self) -> None:
        self.search_context = ""
        self.search_results = []

    def context_text(self, max_chars: int = 6000) -> str:
        """Return a concise summary of currently attached file and search contexts."""
        parts: list[str] = []
        remaining = max_chars
        if self.search_context:
            header = f"SEARCH: {self.search_context}"
            parts.append(header)
            for r in self.search_results[:10]:
                line = f"  {r.get('file', '')}:{r.get('line', '')} {r.get('text', '')[:80]}"
                parts.append(line)
            remaining -= 200
        for ctx in reversed(self.file_contexts):
            if remaining <= 0:
                break
            header = f"FILE: {ctx.get('path')} (lines {ctx.get('start')}-{ctx.get('end')})"
            parts.append(header)
            remaining -= len(header) + 40
        return "\n".join(parts)
