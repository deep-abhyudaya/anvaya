"""Interactive ANVAYA shell."""

from __future__ import annotations

import json
import random
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion, PathCompleter
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import confirm
from rich.console import Console
from rich.table import Table
from sqlalchemy import text
from sqlmodel import Session, select

from anvaya.agent import (
    all_provider_status,
    default_models,
    default_profiles,
    default_tool_registry,
    event_store,
    get_profile,
)
from anvaya.cli.agent_runner import run_agentic, run_chat
from anvaya.cli.artifacts import (
    artifact_type_list,
    delete_artifact,
    delete_artifacts_of_type,
    get_artifact_by_id,
    get_latest_artifact,
    list_artifact_counts,
    list_artifacts_for_project,
    normalize_artifact_type,
)
from anvaya.cli.commands import CommandRegistry, parse_artifact_args, parse_input
from anvaya.cli.files import build_tree, parse_line_range, read_file, search_text
from anvaya.cli.render import AnvayaRenderer
from anvaya.startuped_signals import emit_cli_signal
from anvaya.cli.selectors import (
    select_model,
    select_profile,
    select_project,
)
from anvaya.cli.state import CLIState
from anvaya.data import DataFactory
from anvaya.db import get_session_sync, init_db
from anvaya.ml.alertness import AlertnessEngine
from anvaya.models.agent_context import ExecutionContext
from anvaya.models.audit import AuditRecord
from anvaya.models.dataset import DatasetVersion
from anvaya.models.enums import SelfCorrectionStatus
from anvaya.models.execution import Execution
from anvaya.models.incident import Incident
from anvaya.models.model_version import ModelVersion
from anvaya.models.project import Project
from anvaya.models.telemetry import TelemetryEvent
from anvaya.sentinel import SentinelEngine
from anvaya.simulator.generator import TelemetryGenerator
from anvaya.simulator.scenarios import get_self_correction_scenario
from anvaya.whatif import WhatIfEngine

_HISTORY_DIR = Path.home() / ".local" / "share" / "anvaya" / "cli"
_HISTORY_FILE = _HISTORY_DIR / "history"

# /train local fallback narration templates.  These are deterministic and
# never claim to be produced by an external LLM.
_TRAIN_LOCAL_REASONING: dict[str, str] = {
    "generate": (
        "Generating a fresh synthetic telemetry dataset with balanced normal, "
        "suspicious, and attack scenarios..."
    ),
    "csv": (
        "Persisting the generated or loaded events to a CSV file for "
        "reproducibility and downstream review..."
    ),
    "alertness": (
        "Training the Isolation Forest behavioral anomaly detector on the "
        "dataset..."
    ),
    "whatif": (
        "Training the Logistic Regression counterfactual risk model on the "
        "same events..."
    ),
    "sentinel": (
        "Running a full Sentinel self-correction cycle on the ATK-MISS-001 "
        "incident to validate the miss→catch loop..."
    ),
}

# Valid /train interaction modes.
_TRAIN_MODES = {"auto", "fullquestions", "onlycertainquestions", "allguided"}


def _ensure_history() -> None:
    _HISTORY_DIR.mkdir(parents=True, exist_ok=True)


class _CommandCompleter(Completer):
    """prompt_toolkit completer for slash commands and file/model/path arguments."""

    def __init__(self, shell: "InteractiveShell") -> None:
        self.shell = shell
        self.path_completer = PathCompleter(
            only_directories=False,
            get_paths=lambda: [str(self.shell.state.workspace_root)],
        )

    def get_completions(self, document, complete_event):
        text = document.text
        if not text.startswith("/"):
            return

        first_space = text.find(" ")
        if first_space == -1:
            prefix = text[1:]
            for name in self.shell.registry.complete(prefix):
                yield Completion(name[1:], start_position=-len(prefix))
            return

        cmd_text = text[1:first_space]
        arg_text = text[first_space + 1 :]
        cmd = self.shell.registry.get(cmd_text)
        if not cmd:
            return

        cursor = document.cursor_position - first_space - 1
        if cursor < 0:
            cursor = 0

        if cmd.name in ("read", "tree", "search", "inspect"):
            yield from self.path_completer.get_completions(
                _ArgumentDocument(arg_text, cursor), complete_event
            )

        if cmd.name == "model" and arg_text:
            for m in self.shell._model_list():
                display = m.get("display_name", m["id"])
                if arg_text.lower() in display.lower() or arg_text.lower() in m["id"].lower():
                    yield Completion(display, start_position=-len(arg_text))

        if cmd.name == "project" and arg_text:
            for p in self.shell._project_list():
                name = p.get("name", p["project_id"])
                if arg_text.lower() in name.lower() or arg_text.lower() in p["project_id"].lower():
                    yield Completion(name, start_position=-len(arg_text))


class _ArgumentDocument:
    """Minimal Document-like wrapper for delegating to path completers."""

    def __init__(self, text: str, cursor_position: int) -> None:
        self.text = text
        self.cursor_position = cursor_position


class InteractiveShell:
    """ANVAYA interactive agent terminal."""

    def __init__(
        self,
        *,
        state: CLIState | None = None,
        console: Console | None = None,
        session: Session | None = None,
        workspace: Path | None = None,
    ) -> None:
        self.state = state or CLIState.load()
        self._refresh_state_model_display(persist=state is None)
        self.console = console or Console()
        self.renderer = AnvayaRenderer(self.console)
        self.registry = CommandRegistry()
        self.session = session or get_session_sync()
        self.workspace = workspace or self.state.workspace_root
        self.cancel_event = threading.Event()
        _ensure_history()
        self.prompt_session: PromptSession = PromptSession(
            HTML("<cyan>anvaya</cyan> <gray>›</gray> "),
            history=FileHistory(str(_HISTORY_FILE)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=_CommandCompleter(self),
            bottom_toolbar=self._bottom_toolbar,
            key_bindings=self._key_bindings(),
        )

    def _key_bindings(self) -> KeyBindings:
        bindings = KeyBindings()

        @bindings.add("c-l")
        def _(event):
            self.console.clear()

        @bindings.add("c-c")
        def _(event):
            if not self.cancel_event.is_set():
                self.cancel_event.set()
            event.app.exit(exception=KeyboardInterrupt())

        return bindings

    def _bottom_toolbar(self) -> str:
        """Return a compact status line for the prompt."""
        project = self.state.project_name or self.state.project_id or "—"
        model = self.state.model_display or self.state.model_id or "—"
        profile = self.state.profile_id or "—"
        parts = [
            f"<style fg='cyan'>Project</style> <style fg='white'>{project}</style>",
            f"<style fg='magenta'>Model</style> <style fg='white'>{model}</style>",
            f"<style fg='green'>Profile</style> <style fg='white'>{profile}</style>",
            f"<style fg='yellow'>Mode</style> <style fg='white'>{self.state.mode}</style>",
        ]
        return "  ".join(parts)

    def _refresh_state_model_display(self, persist: bool = False) -> None:
        """Re-derive the stored model display name from the catalog.

        This lets capitalization fixes in the model catalog take effect for
        existing saved CLI state without requiring the user to re-select the
        model.  The local fallback model keeps its explicit display name.
        """
        if (
            not self.state.model_id
            or self.state.model_provider == "anvaya"
            or self.state.model_id == "anvaya-local"
        ):
            return
        from anvaya.llm.catalog_intelligence import display_name_for_model

        refreshed = display_name_for_model(self.state.model_id)
        if refreshed != self.state.model_display:
            self.state.model_display = refreshed
            if persist:
                self.state.save()

    def run(self) -> int:
        """Run the interactive loop."""
        try:
            init_db()
        except Exception as exc:
            self.renderer.error(f"Could not initialize database: {exc}")
            return 1

        if not self._auto_select_defaults():
            self.renderer.warning("No model available. Use /model to select one.")
        self._print_startup()

        while True:
            try:
                self.cancel_event.clear()
                text = self.prompt_session.prompt()
            except KeyboardInterrupt:
                self.console.print("\n[dim]Use /quit to exit.[/dim]")
                continue
            except EOFError:
                break

            if not text.strip():
                continue

            self.state.add_command(text)
            self.state.save()

            try:
                if not self._handle(text):
                    break
            except KeyboardInterrupt:
                self.renderer.warning("Interrupted.")
            except Exception as exc:
                if self.state.debug:
                    self.console.print_exception()
                else:
                    self.renderer.error(str(exc), "Use /debug on for details")

        self._shutdown()
        return 0

    def _print_startup(self) -> None:
        self.renderer.header()
        connected = False
        try:
            self.session.execute(text("SELECT 1"))
            connected = True
        except Exception:
            pass

        project = self.state.project_name or self.state.project_id or None
        model = self.state.model_display or self.state.model_id or None
        self.renderer.status_line(
            {
                "backend": connected,
                "project": project,
                "model": model,
            }
        )
        self.console.print()

    def _auto_select_defaults(self) -> bool:
        """Select a sensible default model if none is configured."""
        if not self.state.model_id:
            self.state.set_model(
                {
                    "id": "anvaya-local",
                    "display_name": "ANVAYA Local",
                    "provider": "anvaya",
                }
            )
            return True
        return bool(self.state.model_id)

    def _handle(self, text: str) -> bool:
        """Dispatch a single user input. Returns False to stop the shell."""
        cmd_name, args = parse_input(text)
        command_label = cmd_name or "prompt"
        emit_cli_signal(command_label, "started", {"argsCount": len(args)})

        if cmd_name:
            command = self.registry.get(cmd_name)
            if command:
                handler = getattr(self, command.handler, None)
                if handler:
                    result = handler(args)
                    emit_cli_signal(command_label, "completed")
                    return result
                self.renderer.error(f"Command handler not implemented: {cmd_name}")
                emit_cli_signal(command_label, "failed", {"reason": "handler_missing"})
                return True
            self.renderer.error(f"Unknown command: /{cmd_name}")
            emit_cli_signal(command_label, "failed", {"reason": "unknown_command"})
            return True

        if self.state.mode == "chat":
            run_chat(self.session, self.state, self.renderer, text, workspace=self.workspace)
            emit_cli_signal(command_label, "completed", {"mode": "chat"})
            return True

        run_agentic(
            self.session,
            self.state,
            self.renderer,
            text,
            workspace=self.workspace,
            cancel_requested=self.cancel_event,
        )
        emit_cli_signal(command_label, "completed", {"mode": "agentic"})
        return True


    def _do_help(self, args: list[str]) -> bool:
        if args:
            cmd = self.registry.get(args[0])
            if cmd:
                self.console.print(f"[bold cyan]/{cmd.name}[/bold cyan] {cmd.args}")
                self.console.print(f"  {cmd.description}")
                if cmd.aliases:
                    self.console.print(f"  Aliases: {', '.join(f'/{a}' for a in cmd.aliases)}")
            else:
                self.renderer.error(f"No help for /{args[0]}")
            return True

        groups = {
            "Agent": ["investigate", "mission", "incident", "profile", "model", "new"],
            "Context": ["read", "tree", "search", "context"],
            "Artifacts": [
                "artifact",
                "orbit",
                "ecosystem",
                "replay",
                "reach",
                "segments",
                "arena",
                "arbor",
                "impact",
                "trophy",
                "ledger",
                "inspect",
                "regenerate",
                "delete",
            ],
            "State": ["status", "blackboard", "hypotheses", "hypothesis", "memory", "history"],
            "System": ["tools", "clear", "debug", "shell", "quit"],
        }
        for group, names in groups.items():
            self.console.print(f"\n[bold cyan]{group}[/bold cyan]")
            for name in names:
                cmd = self.registry.get(name)
                if cmd:
                    self.console.print(f"  /{cmd.name:<12} {cmd.description}")
        self.console.print()
        return True

    def _do_quit(self, _args: list[str]) -> bool:
        self.console.print("[dim]Exiting ANVAYA.[/dim]")
        return False

    def _do_clear(self, _args: list[str]) -> bool:
        self.console.clear()
        return True

    def _do_debug(self, args: list[str]) -> bool:
        if args:
            self.state.debug = args[0].lower() in ("on", "true", "1")
        else:
            self.state.debug = not self.state.debug
        self.state.save()
        self.renderer.success(f"Debug mode {'on' if self.state.debug else 'off'}")
        return True

    def _do_status(self, _args: list[str]) -> bool:
        self.console.print("[bold cyan]ANVAYA STATUS[/bold cyan]")
        tools = default_tool_registry().list_tools()
        incidents = self.session.exec(select(Incident)).all()
        executions = self.session.exec(select(Execution).limit(100)).all()
        self.console.print("  Backend      [green]●[/green] connected")
        self.console.print(
            f"  Model        [cyan]{self.state.model_display or self.state.model_id or '—'}[/cyan]"
        )
        self.console.print(f"  Provider     [cyan]{self.state.model_provider or '—'}[/cyan]")
        self.console.print(f"  Tools        [cyan]{len(tools)}[/cyan] available")
        self.console.print(
            f"  Project      [cyan]{self.state.project_name or self.state.project_id or '—'}[/cyan]"
        )
        self.console.print(f"  Profile      [cyan]{self.state.profile_id}[/cyan]")
        self.console.print(f"  Incidents    [cyan]{len(incidents)}[/cyan]")
        self.console.print(f"  Executions   [cyan]{len(executions)}[/cyan]")
        return True

    def _do_project(self, _args: list[str]) -> bool:
        projects = [p.model_dump() for p in self.session.exec(select(Project)).all()]
        if not projects:
            self.renderer.error("No projects found. Create one in the web app or API.")
            return True
        selected = select_project(projects)
        if selected:
            project_id, name = selected
            self.state.set_project(project_id, name)
            self.renderer.success(f"Project set: {name}")
        return True

    def _do_incident(self, _args: list[str]) -> bool:
        if _args:
            self.state.set_incident(_args[0].upper())
            self.renderer.success(f"Incident set: {self.state.incident_id}")
            return True

        incidents = [i.model_dump() for i in self.session.exec(select(Incident)).all()]
        if not incidents:
            self.renderer.error("No incidents found.")
            return True
        items = [
            (i["incident_id"], f"{i['incident_id']} — {i.get('title', '')}") for i in incidents
        ]
        selected = select_one("SELECT INCIDENT", items)
        if selected:
            self.state.set_incident(selected)
            self.renderer.success(f"Incident set: {selected}")
        return True

    def _do_model(self, args: list[str]) -> bool:
        models = [m.model_dump() for m in default_models()]
        if args:
            q = " ".join(args).lower()
            filtered = [
                m
                for m in models
                if q in (m.get("display_name") or "").lower() or q in m["id"].lower()
            ]
            if not filtered:
                self.renderer.error(f"No models match '{q}'")
                return True
            models = filtered

        selected = select_model(models, self.state.model_id)
        if selected:
            self.state.set_model(selected)
            self.renderer.success(
                f"Model switched: {selected['display_name']} · {selected['provider']}"
            )
        return True

    def _do_models(self, _args: list[str]) -> bool:
        table = Table(title="ANVAYA Models")
        table.add_column("Model", style="white", no_wrap=True)
        table.add_column("Provider", style="cyan")
        table.add_column("Status", style="green")
        for m in default_models():
            status = (
                "[green]●[/green]"
                if m.availability in ("available", "configured")
                else "[red]●[/red]"
            )
            table.add_row(m.display_name, m.provider, status)
        self.console.print(table)
        return True

    def _do_profile(self, _args: list[str]) -> bool:
        if _args:
            profile_id = _args[0]
            if get_profile(profile_id):
                self.state.set_profile(profile_id)
                self.renderer.success(f"Profile set: {profile_id}")
            else:
                self.renderer.error(f"Unknown profile: {profile_id}")
            return True

        profiles = [p.model_dump() for p in default_profiles()]
        selected_id = select_profile(profiles)
        if selected_id:
            self.state.set_profile(selected_id)
            self.renderer.success(f"Profile set: {selected_id}")
        return True

    def _do_provider(self, _args: list[str]) -> bool:
        statuses = all_provider_status()
        table = Table(title="Provider Status")
        table.add_column("Provider", style="white")
        table.add_column("Healthy", style="green")
        table.add_column("Availability", style="cyan")
        for s in statuses:
            healthy = "[green]●[/green]" if s.get("healthy") else "[red]●[/red]"
            table.add_row(s.get("name", ""), healthy, s.get("availability", ""))
        self.console.print(table)
        return True

    def _do_read(self, args: list[str]) -> bool:
        if not args:
            self.renderer.error("Usage: /read <path> [start] [end]")
            return True
        raw = " ".join(args)
        path, start, end = parse_line_range(raw)
        try:
            data = read_file(path, self.workspace, line_start=start, line_end=end)
            snippet = "\n".join(data["lines"])
            self.state.add_file_context(
                data["path"], data["start"], data["end"], snippet, data["total"]
            )
            self.renderer.file_summary(
                data["path"], len(data["lines"]), data["total"], data["start"], data["end"]
            )
            self.renderer.file(data["path"], data["lines"], start=data["start"])
        except (OSError, ValueError) as exc:
            self.renderer.error(str(exc), "/tree or /search")
        return True

    def _do_tree(self, args: list[str]) -> bool:
        target = args[0] if args else "."
        try:
            data = build_tree(target, self.workspace)
            self.renderer.tree(data["path"], data["lines"])
        except (OSError, ValueError) as exc:
            self.renderer.error(str(exc))
        return True

    def _do_search(self, args: list[str]) -> bool:
        if not args:
            self.renderer.error('Usage: /search "query" [scope]')
            return True

        query = args[0]
        scope = " ".join(args[1:]) if len(args) > 1 else ""
        if (query.startswith('"') and query.endswith('"')) or (
            query.startswith("'") and query.endswith("'")
        ):
            query = query[1:-1]

        try:
            results = search_text(query, self.workspace, scope=scope)
            self.renderer.search_results(results)
            self.state.search_context = query
            self.state.search_results = results
            self.state.save()
        except (OSError, ValueError) as exc:
            self.renderer.error(str(exc))
        return True

    def _do_context(self, args: list[str]) -> bool:
        if args and args[0].lower() == "clear":
            self.state.clear_file_context()
            self.state.clear_search_context()
            self.renderer.success("Context cleared")
            return True

        table = Table(title="CONTEXT")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Project", self.state.project_name or self.state.project_id or "—")
        table.add_row("Incident", self.state.incident_id or "—")
        table.add_row("Model", self.state.model_display or self.state.model_id or "—")
        table.add_row("Profile", self.state.profile_id)
        table.add_row("Mode", self.state.mode)
        if self.state.file_contexts:
            table.add_row("Files", ", ".join(c.get("path", "") for c in self.state.file_contexts))
        if self.state.search_context:
            table.add_row("Search", self.state.search_context)
        self.console.print(table)
        return True

    def _do_investigate(self, args: list[str]) -> bool:
        objective = " ".join(args)
        if not objective:
            self.renderer.error("Usage: /investigate <objective>")
            return True
        run_agentic(
            self.session,
            self.state,
            self.renderer,
            objective,
            workspace=self.workspace,
            cancel_requested=self.cancel_event,
        )
        return True

    def _do_mission(self, _args: list[str]) -> bool:
        if not self.state.active_execution_id:
            self.renderer.info("No active execution. Run an agentic query first.")
            return True
        ctx = self._get_execution_context(self.state.active_execution_id)
        if not ctx:
            self.renderer.error("Execution context not found.")
            return True
        mission = ctx.get_mission() or {}
        self.console.print("[bold cyan]MISSION[/bold cyan]")
        self.renderer.json_payload(mission)
        return True

    def _do_blackboard(self, _args: list[str]) -> bool:
        ctx = self._active_context()
        if not ctx:
            return True
        bb = ctx.get_blackboard() or {}
        self.console.print("[bold cyan]BLACKBOARD[/bold cyan]")
        self.renderer.json_payload(bb)
        return True

    def _do_hypotheses(self, _args: list[str]) -> bool:
        ctx = self._active_context()
        if not ctx:
            return True
        hyps = ctx.get_hypotheses() or []
        if not hyps:
            self.renderer.info("No active hypotheses.")
            return True
        table = Table(title="HYPOTHESES")
        table.add_column("ID", style="cyan")
        table.add_column("Statement", style="white")
        table.add_column("Confidence", style="green")
        table.add_column("Status", style="yellow")
        for h in hyps:
            table.add_row(
                str(h.get("id", "")),
                h.get("statement", "")[:40],
                f"{h.get('confidence', 0):.2f}",
                h.get("status", ""),
            )
        self.console.print(table)
        return True

    def _do_hypothesis(self, args: list[str]) -> bool:
        if not args:
            self.renderer.error("Usage: /hypothesis <id>")
            return True
        hyp_id = args[0]
        ctx = self._active_context()
        if not ctx:
            return True
        for h in ctx.get_hypotheses() or []:
            if str(h.get("id")) == hyp_id:
                self.renderer.json_payload(h)
                return True
        self.renderer.error(f"Hypothesis {hyp_id} not found")
        return True

    def _do_memory(self, _args: list[str]) -> bool:
        ctx = self._active_context()
        if not ctx:
            return True
        mem = ctx.get_memory() or {}
        self.console.print("[bold cyan]MEMORY[/bold cyan]")
        self.renderer.json_payload(mem)
        return True

    def _do_history(self, args: list[str]) -> bool:
        limit = int(args[0]) if args and args[0].isdigit() else 20
        rows = self.session.exec(
            select(Execution).order_by(Execution.started_at.desc()).limit(limit)
        ).all()
        if not rows:
            self.renderer.info("No executions yet.")
            return True
        table = Table(title="EXECUTION HISTORY")
        table.add_column("ID", style="cyan")
        table.add_column("Objective", style="white")
        table.add_column("Status", style="green")
        table.add_column("Duration", style="dim")
        for r in rows:
            status_color = (
                "green" if r.status == "completed" else "red" if r.status == "failed" else "yellow"
            )
            table.add_row(
                r.execution_id,
                r.objective[:40],
                f"[{status_color}]{r.status}[/{status_color}]",
                f"{r.duration_ms:.0f}ms",
            )
        self.console.print(table)
        return True

    def _do_open(self, args: list[str]) -> bool:
        if not args:
            self.renderer.error("Usage: /open <execution_id>")
            return True
        execution_id = args[0]
        execution = event_store.get_execution(self.session, execution_id)
        if not execution:
            self.renderer.error(f"Execution not found: {execution_id}")
            return True
        self.state.set_active_execution(execution_id)
        self.renderer.success(f"Loaded execution {execution_id} ({execution.status})")
        return True

    def _do_resume(self, args: list[str]) -> bool:
        if not args:
            self.renderer.error("Usage: /resume <execution_id>")
            return True
        execution_id = args[0]
        execution = event_store.get_execution(self.session, execution_id)
        if not execution:
            self.renderer.error(f"Execution not found: {execution_id}")
            return True
        run_agentic(
            self.session,
            self.state,
            self.renderer,
            execution.objective,
            workspace=self.workspace,
            cancel_requested=self.cancel_event,
        )
        return True

    def _do_tools(self, _args: list[str]) -> bool:
        registry = default_tool_registry()
        table = Table(title="TOOLS")
        table.add_column("Category", style="cyan")
        table.add_column("Tool", style="white")
        table.add_column("Description", style="dim")
        for tool in registry.list_tools():
            table.add_row(tool.category, tool.name, tool.description[:60])
        self.console.print(table)
        return True

    def _do_new(self, _args: list[str]) -> bool:
        self.state.active_execution_id = ""
        self.state.clear_file_context()
        self.state.clear_search_context()
        self.state.save()
        self.renderer.success("New conversation")
        return True

    def _do_chat(self, args: list[str]) -> bool:
        if args:
            self.state.mode = "chat"
            self.state.save()
            message = " ".join(args)
            run_chat(self.session, self.state, self.renderer, message, workspace=self.workspace)
        else:
            self.state.mode = "chat"
            self.state.save()
            self.renderer.success("Switched to chat mode")
        return True

    def _do_ask(self, args: list[str]) -> bool:
        if not args:
            self.renderer.error("Usage: /ask <question>")
            return True

        message = " ".join(args)
        lower = message.lower()
        training_keywords = {
            "train",
            "training",
            "dataset",
            "datasets",
            "csv",
            "model",
            "models",
            "alertness",
            "whatif",
            "what-if",
            "sentinel",
            "self-correction",
            "replay",
            "events",
            "features",
            "pipeline",
        }
        is_training_question = (
            args[0].lower() == "train" or any(kw in lower for kw in training_keywords)
        )

        # Handle explicit "print/show/dump the dataset/CSV" requests directly.
        wants_full_csv = (
            is_training_question
            and any(k in lower for k in ("print", "show", "dump", "entire", "full", "all"))
            and any(k in lower for k in ("csv", "dataset", "data"))
        )
        if wants_full_csv:
            return self._print_latest_dataset()

        extra_context = ""
        if is_training_question:
            extra_context = self._build_training_context()
            if args[0].lower() == "train":
                message = " ".join(args[1:]) or "Tell me about the training pipeline."

        run_chat(
            self.session,
            self.state,
            self.renderer,
            message,
            workspace=self.workspace,
            extra_context=extra_context,
            objective_context=not is_training_question,
        )
        return True

    def _build_training_context(self) -> str:
        """Return a summary of the latest /train outputs for /ask context."""
        from anvaya.config import settings

        lines: list[str] = [
            "Use the following ANVAYA /train context to answer the user's question. "
            "Base your answer strictly on this data.",
            "",
            "TRAINING CONTEXT:",
        ]

        ds = self.session.exec(
            select(DatasetVersion).order_by(DatasetVersion.created_at.desc())
        ).first()
        if ds:
            total = (
                ds.train_count
                + ds.validation_count
                + ds.test_count
                + ds.replay_count
            )
            csv_path = settings.datasets_dir / f"{ds.dataset_id}.csv"
            csv_status = csv_path if csv_path.exists() else "not exported yet"
            lines.append(
                f"Latest dataset: {ds.dataset_id} ({total} total events, "
                f"normal={ds.normal_count}, attack={ds.attack_count}, "
                f"suspicious={ds.suspicious_count}; train={ds.train_count}, "
                f"validation={ds.validation_count}, test={ds.test_count}, "
                f"replay={ds.replay_count}; seed={ds.seed}). CSV: {csv_status}"
            )
        else:
            lines.append("No dataset has been generated yet.")

        for model_type, label in [
            ("isolation_forest", "Alertness"),
            ("logistic_regression", "What-If"),
        ]:
            mv = self.session.exec(
                select(ModelVersion)
                .where(ModelVersion.model_type == model_type)
                .order_by(ModelVersion.created_at.desc())
            ).first()
            if mv:
                lines.append(
                    f"Latest {label} model: {mv.model_id} (precision={mv.precision:.4f}, "
                    f"recall={mv.recall:.4f}, f1={mv.f1_score:.4f}, "
                    f"FPR={mv.false_positive_rate:.4f}, FNR={mv.false_negative_rate:.4f}, "
                    f"latency_ms={mv.inference_latency_ms:.2f}, samples={mv.training_samples})"
                )

        incident = self.session.exec(
            select(Incident)
            .where(Incident.scenario_id == "ATK-MISS-001")
            .order_by(Incident.created_at.desc())
        ).first()
        if incident:
            lines.append(
                f"Sentinel self-correction incident: {incident.incident_id} "
                f"status={incident.self_correction_status.value}, "
                f"attack_family={incident.attack_family}"
            )
        else:
            lines.append("No Sentinel self-correction incident has been created yet.")

        lines.append(
            "The /train pipeline: generate or load a telemetry dataset, export it to CSV, "
            "train an Isolation Forest (Alertness) and a Logistic Regression (What-If) model, "
            "then run a Sentinel self-correction cycle on the ATK-MISS-001 incident."
        )
        return "\n".join(lines)

    def _print_latest_dataset(self) -> bool:
        """Print the full contents of the latest training CSV."""
        from anvaya.config import settings

        ds = self.session.exec(
            select(DatasetVersion).order_by(DatasetVersion.created_at.desc())
        ).first()
        if not ds:
            self.renderer.error("No dataset has been generated or imported yet.")
            return True

        csv_path = settings.datasets_dir / f"{ds.dataset_id}.csv"
        if not csv_path.exists():
            self.renderer.error(f"CSV not found: {csv_path}")
            return True

        try:
            content = csv_path.read_text()
        except OSError as exc:
            self.renderer.error(f"Could not read CSV: {exc}")
            return True

        self.console.print(f"[cyan]Dataset:[/cyan] {ds.dataset_id} — {csv_path}")
        self.console.print(content, soft_wrap=True)
        return True

    def _do_shell(self, args: list[str]) -> bool:
        if not args:
            self.renderer.error("Usage: /shell <command>")
            return True
        cmd = " ".join(args)
        if not confirm("Run shell command? (this is a user action, not the agent)"):
            return True
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            if result.stdout:
                self.console.print(result.stdout[:2000])
            if result.stderr:
                self.console.print(f"[red]{result.stderr[:500]}[/red]")
        except Exception as exc:
            self.renderer.error(str(exc))
        return True

    def _parse_train_args(
        self, args: list[str]
    ) -> tuple[str, int | None, str | None, list[str]]:
        """Parse `/train [mode] [seed|file]` arguments."""
        mode = "allguided"
        seed: int | None = None
        file_path: str | None = None
        unrecognized: list[str] = []
        for arg in args:
            lower = arg.lower()
            if lower in _TRAIN_MODES:
                mode = lower
            elif arg.lstrip("-").isdigit() and arg != "-":
                try:
                    seed = int(arg)
                except ValueError:
                    unrecognized.append(arg)
            elif arg.endswith(".csv"):
                file_path = arg
            else:
                unrecognized.append(arg)
        return mode, seed, file_path, unrecognized

    def _train_prompt(
        self, question: str, choices: list[tuple[str, str]] | None = None
    ) -> str:
        """Ask the user for a training step choice.

        When stdin is not a TTY (tests, piped input) the question is printed
        and the first choice is auto-selected so the pipeline completes without
        blocking.
        """
        choices = choices or [
            ("proceed", "Run this step"),
            ("explain", "Explain more"),
            ("abort", "Cancel"),
        ]
        default_choice = choices[0][0]
        options = " / ".join(f"({key[0]}){key[1:]}" for key, _ in choices)

        if not sys.stdin.isatty():
            self.console.print(
                f"[cyan]?[/cyan] {question} {options} "
                f"[dim](auto-{default_choice})[/dim]"
            )
            return default_choice

        self.console.print(f"[cyan]?[/cyan] {question} {options}")
        valid: dict[str, str] = {}
        for key, _ in choices:
            valid[key] = key
            valid[key[0]] = key
        while True:
            try:
                answer = input("> ").strip().lower()
            except EOFError:
                return "abort"
            if answer in valid:
                return valid[answer]
            self.console.print("[red]Invalid choice.[/red]")

    def _should_prompt(self, mode: str, step: str) -> bool:
        """Return True if the current mode should prompt before this step."""
        if mode == "fullquestions":
            return True
        if mode == "onlycertainquestions" and step in {"generate", "sentinel"}:
            return True
        return False

    def _print_step_explanation(self, step: str) -> None:
        """Print a longer explanation when the user asks for one."""
        explanations = {
            "generate": (
                "A balanced dataset is generated from scenario templates. "
                "Normal, suspicious, and attack scenarios are mixed, then split "
                "into train/validation/test/replay sets. The self-correction "
                "scenario (ATK-MISS-001) provides the replay events used by Sentinel."
            ),
            "csv": (
                "The generated or loaded events are written to "
                "datasets/<dataset_id>.csv so they can be inspected, shared, or "
                "loaded again with /train <mode> <file.csv>."
            ),
            "alertness": (
                "Isolation Forest learns the feature distribution of normal "
                "telemetry and flags outliers. Metrics are computed on the "
                "training set and a new ModelVersion is persisted."
            ),
            "whatif": (
                "Logistic Regression learns which feature combinations drive "
                "attack risk. The resulting model supports the What-If "
                "counterfactual analysis used during incident response."
            ),
            "sentinel": (
                "Sentinel runs the miss→catch loop: confirm miss, backtrack "
                "through attack events, propose and validate a detection rule, "
                "then replay the same attack to verify it is caught."
            ),
        }
        text = explanations.get(step, "")
        if text:
            self.console.print(f"  [dim]{text}[/dim]")

    def _resolve_train_provider(self) -> tuple[Any, str]:
        """Select the active model provider for /train narration.

        Uses the CLI's selected model/provider (e.g. OpenRouter, NVIDIA,
        AgentRouter).  Falls back to deterministic local narration when the
        active provider is local or not configured/healthy.
        """
        from anvaya.llm.providers import create_model_provider

        provider_name = (self.state.model_provider or "").lower()
        model_id = self.state.model_id or ""

        # Infer provider from model_id if the state doesn't carry it.
        if not provider_name and "/" in model_id:
            provider_name = model_id.split("/", 1)[0].lower()

        if not provider_name or provider_name in ("anvaya", "anvaya-local", "local"):
            return None, "local fallback (no LLM configured)"

        try:
            provider = create_model_provider(provider_name, model_id)
        except Exception:
            provider = None

        if (
            provider
            and provider.configured()
            and provider.healthy()
            and provider.name not in ("anvaya", "anvaya-local", "local")
        ):
            return provider, provider.name

        return None, "local fallback (no LLM configured)"

    def _build_train_reasoning_prompt(self, step: str, **ctx) -> str:
        """Build a prompt asking the LLM for one sentence of step narration."""
        base = (
            "You are the ANVAYA training orchestrator. "
            "Produce exactly one plain-language sentence (one or two sentences) "
            "describing the next step. Do not decide whether the step runs, do not "
            "change counts, and do not skip anything. Output only JSON with the key 'reasoning'."
        )
        details = {
            "generate": (
                f"Next step: generate or load a telemetry dataset. "
                f"Context: seed={ctx.get('seed')}, normal={ctx.get('normal_count')}, "
                f"suspicious={ctx.get('suspicious_count')}, attack={ctx.get('attack_count')}, "
                f"file={ctx.get('file_path')}."
            ),
            "csv": (
                f"Next step: export the dataset to CSV. "
                f"Context: dataset_id={ctx.get('dataset_id')}, "
                f"total_events={ctx.get('total_events')}."
            ),
            "alertness": (
                f"Next step: train Isolation Forest. "
                f"Context: dataset_id={ctx.get('dataset_id')}, events={ctx.get('event_count')}."
            ),
            "whatif": (
                f"Next step: train Logistic Regression what-if model. "
                f"Context: dataset_id={ctx.get('dataset_id')}, events={ctx.get('event_count')}."
            ),
            "sentinel": (
                f"Next step: run Sentinel self-correction. "
                f"Context: incident_id={ctx.get('incident_id')}, "
                f"scenario_id={ctx.get('scenario_id')}, current_status={ctx.get('current_status')}."
            ),
        }
        return f"{base}\n\n{details.get(step, '')}"

    def _train_reasoning(self, step: str, provider: Any | None, **ctx) -> str:
        """Return narration for the next training step.

        Uses the resolved model provider's chat completion if available; falls
        back to a deterministic local template if no provider is configured or
        the provider call fails.
        """
        # Deterministic local fallback
        if provider is None:
            if step == "generate" and ctx.get("file_path"):
                return f"Loading the provided CSV dataset from {ctx['file_path']}..."
            if step == "csv" and ctx.get("dataset_id"):
                return f"Persisting the events to datasets/{ctx['dataset_id']}.csv..."
            return _TRAIN_LOCAL_REASONING.get(step, "Running next training step...")

        prompt = self._build_train_reasoning_prompt(step, **ctx)
        try:
            response = provider.chat_completion(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are the ANVAYA training orchestrator. "
                            "Output JSON with the key 'reasoning'."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
            )
            if isinstance(response, Iterator):
                response = next(response)
        except Exception:
            response = None

        if response and not response.error and response.text:
            try:
                data = json.loads(response.text)
                reasoning = data.get("reasoning", "").strip()
                if reasoning:
                    return reasoning
            except Exception:
                text = response.text.strip()
                if text:
                    return text

        # Provider failed — fall back to local template.
        if step == "generate" and ctx.get("file_path"):
            return f"Loading the provided CSV dataset from {ctx['file_path']}..."
        if step == "csv" and ctx.get("dataset_id"):
            return f"Persisting the events to datasets/{ctx['dataset_id']}.csv..."
        return _TRAIN_LOCAL_REASONING.get(step, "Running next training step...")

    def _print_model_metrics(self, label: str, metrics: dict[str, Any]) -> None:
        """Render a model's training metrics like the ``anvaya evaluate`` table."""
        self.renderer.metrics_table(
            f"{label} — {metrics.get('model_id', '')}",
            ["Metric", "Value"],
            [
                ["Precision", f"{metrics.get('precision', 0):.4f}"],
                ["Recall", f"{metrics.get('recall', 0):.4f}"],
                ["F1", f"{metrics.get('f1_score', 0):.4f}"],
                ["FPR", f"{metrics.get('false_positive_rate', 0):.4f}"],
                ["FNR", f"{metrics.get('false_negative_rate', 0):.4f}"],
                ["Latency (ms)", f"{metrics.get('inference_latency_ms', 0):.2f}"],
            ],
        )

    def _get_or_create_self_correction_incident(self) -> Incident:
        """Return the ATK-MISS-001 incident, creating it (and replay events) if absent."""
        scenario = get_self_correction_scenario()
        incident = self.session.exec(
            select(Incident).where(Incident.scenario_id == scenario.scenario_id)
        ).first()
        if incident:
            return incident

        events = list(
            self.session.exec(
                select(TelemetryEvent).where(TelemetryEvent.scenario_id == scenario.scenario_id)
            ).all()
        )
        if not events:
            generator = TelemetryGenerator(seed=42)
            pre = generator.generate_for_scenario(
                scenario,
                base_time=datetime(2026, 1, 4, tzinfo=timezone.utc),
                replay_id=f"REPLAY-{scenario.scenario_id}-PRE",
                is_replay=True,
            )
            post = generator.generate_for_scenario(
                scenario,
                base_time=datetime(2026, 1, 4, tzinfo=timezone.utc),
                replay_id=f"REPLAY-{scenario.scenario_id}-POST",
                is_replay=True,
            )
            for evt_data in pre + post:
                event = TelemetryEvent(
                    event_id=evt_data["event_id"],
                    scenario_id=evt_data["scenario_id"],
                    event_type=evt_data["event_type"],
                    timestamp=datetime.fromisoformat(evt_data["timestamp"]),
                    actor=evt_data["actor"],
                    host=evt_data["host"],
                    process=evt_data["process"],
                    source=evt_data["source"],
                    destination=evt_data["destination"],
                    command=evt_data["command"],
                    is_off_hours=evt_data["is_off_hours"],
                    is_new_device=evt_data["is_new_device"],
                    is_privilege_escalation=evt_data["is_privilege_escalation"],
                    is_anomalous_process=evt_data["is_anomalous_process"],
                    is_unusual_network=evt_data["is_unusual_network"],
                    is_lateral_movement=evt_data["is_lateral_movement"],
                    is_attack=evt_data["is_attack"],
                    attack_family=evt_data["attack_family"],
                    ground_truth_label=evt_data["ground_truth_label"],
                    seed=evt_data["seed"],
                    replay_id=evt_data["replay_id"],
                    is_replay=evt_data["is_replay"],
                )
                self.session.add(event)
            self.session.commit()
            events = list(
                self.session.exec(
                    select(TelemetryEvent).where(TelemetryEvent.scenario_id == scenario.scenario_id)
                ).all()
            )

        anchor = next((e for e in events if e.is_attack), events[0])
        severity_by_family = {
            "lateral_movement": "high",
            "privilege_escalation": "high",
            "data_exfiltration": "high",
            "persistence": "medium",
            "credential_abuse": "medium",
            "unusual_network": "medium",
            "suspicious_login": "low",
        }
        incident = Incident(
            incident_id=f"INC-{uuid4().hex[:8].upper()}",
            title=f"Lateral Movement Attack — {scenario.scenario_id}",
            description=scenario.description,
            severity=severity_by_family.get(scenario.attack_family, "medium"),
            attack_family=scenario.attack_family,
            scenario_id=scenario.scenario_id,
            scenario_seed=scenario.seed,
            host=anchor.host or "WS-001",
            user=anchor.actor or "eve",
        )
        self.session.add(incident)
        self.session.commit()
        self.session.refresh(incident)

        for evt in events:
            if not evt.incident_id:
                evt.incident_id = incident.incident_id
                self.session.add(evt)
        self.session.commit()
        return incident

    def _print_sentinel_transitions(self, incident_id: str) -> None:
        """Print the Sentinel self-correction state transition chain."""
        records = list(
            self.session.exec(
                select(AuditRecord)
                .where(AuditRecord.incident_id == incident_id)
                .where(AuditRecord.actor == "sentinel")
                .order_by(AuditRecord.timestamp.asc())
            ).all()
        )
        if not records:
            self.renderer.info("No Sentinel transitions recorded.")
            return

        states = ["none"] + [r.new_state for r in records]
        self.console.print("  [dim]Self-correction transitions:[/dim]")
        for prev, nxt in zip(states, states[1:]):
            self.console.print(f"  {prev} → {nxt}")

    def _do_train(self, args: list[str]) -> bool:
        """Agent-orchestrated training: generate dataset, train models, Sentinel."""
        try:
            mode, seed, file_path, unrecognized = self._parse_train_args(args)
        except ValueError as exc:
            self.renderer.error(str(exc))
            return True

        if unrecognized:
            self.renderer.warning(
                f"Ignored unrecognized argument(s): {', '.join(unrecognized)}"
            )

        if mode == "allguided":
            choice = self._train_prompt(
                "I will generate or load a dataset, export it to CSV, train the "
                "Isolation Forest and What-If models, and run a Sentinel "
                "self-correction cycle. How would you like to proceed?",
                choices=[
                    ("proceed", "Run the pipeline"),
                    ("explain", "Explain each step"),
                    ("abort", "Cancel"),
                ],
            )
            if choice == "abort":
                self.renderer.info("/train cancelled.")
                return True
            if choice == "explain":
                mode = "fullquestions"

        provider, provider_name = self._resolve_train_provider()
        self.console.print(f"[cyan]Provider:[/cyan] {provider_name}")

        factory = DataFactory(self.session)

        # Step 1: dataset
        step = "generate"
        reasoning = self._train_reasoning(
            step,
            provider,
            seed=seed,
            file_path=file_path,
            normal_count=3,
            suspicious_count=2,
            attack_count=4,
            include_self_correction=True,
        )
        if self._should_prompt(mode, step):
            choice = self._train_prompt(reasoning)
            if choice == "abort":
                self.renderer.info("/train cancelled before dataset generation.")
                return True
            if choice == "explain":
                self._print_step_explanation(step)
        else:
            self.console.print(f"  [magenta]●[/magenta] {reasoning}")

        try:
            if file_path:
                ds_result = factory.import_csv(file_path, seed=seed or 0)
            else:
                config = {
                    "seed": seed or random.randint(1, 1_000_000),
                    "normal_count": 3,
                    "suspicious_count": 2,
                    "attack_count": 4,
                    "include_self_correction": True,
                }
                ds_result = factory.generate(config)
        except (FileNotFoundError, ValueError) as exc:
            self.renderer.error(f"Dataset preparation failed: {exc}")
            return True

        dataset_id = ds_result["dataset_id"]
        meta = ds_result["metadata"]
        total_events = (
            meta["train_count"]
            + meta["validation_count"]
            + meta["test_count"]
            + meta["replay_count"]
        )
        self.renderer.success(
            f"Dataset ready: {dataset_id} ({total_events} events)"
        )

        # Step 2: CSV export
        step = "csv"
        reasoning = self._train_reasoning(
            step, provider, dataset_id=dataset_id, total_events=total_events
        )
        if self._should_prompt(mode, step):
            choice = self._train_prompt(reasoning)
            if choice == "abort":
                self.renderer.info("/train cancelled before CSV export.")
                return True
            if choice == "explain":
                self._print_step_explanation(step)
        else:
            self.console.print(f"  [magenta]●[/magenta] {reasoning}")

        csv_path = factory.export_events_csv(
            dataset_id,
            events=cast(list[dict[str, Any] | TelemetryEvent], factory._last_dataset_events),
        )
        self.renderer.success(f"CSV exported: {csv_path}")

        # Step 3: Alertness
        events = list(self.session.exec(select(TelemetryEvent)).all())
        step = "alertness"
        reasoning = self._train_reasoning(
            step, provider, dataset_id=dataset_id, event_count=len(events)
        )
        if self._should_prompt(mode, step):
            choice = self._train_prompt(reasoning)
            if choice == "abort":
                self.renderer.info("/train cancelled before Alertness training.")
                return True
            if choice == "explain":
                self._print_step_explanation(step)
        else:
            self.console.print(f"  [magenta]●[/magenta] {reasoning}")

        alertness = AlertnessEngine(self.session)
        alertness_metrics = alertness.train(events)
        self._print_model_metrics("Alertness", alertness_metrics)

        # Step 4: What-If
        step = "whatif"
        reasoning = self._train_reasoning(
            step, provider, dataset_id=dataset_id, event_count=len(events)
        )
        if self._should_prompt(mode, step):
            choice = self._train_prompt(reasoning)
            if choice == "abort":
                self.renderer.info("/train cancelled before What-If training.")
                return True
            if choice == "explain":
                self._print_step_explanation(step)
        else:
            self.console.print(f"  [magenta]●[/magenta] {reasoning}")

        whatif = WhatIfEngine(self.session)
        whatif_metrics = whatif.train(events)
        self._print_model_metrics("What-If", whatif_metrics)

        # Step 5: Sentinel self-correction
        incident = self._get_or_create_self_correction_incident()
        step = "sentinel"
        reasoning = self._train_reasoning(
            step,
            provider,
            incident_id=incident.incident_id,
            scenario_id=incident.scenario_id,
            current_status=incident.self_correction_status.value,
        )
        if self._should_prompt(mode, step):
            choice = self._train_prompt(reasoning)
            if choice == "abort":
                self.renderer.info("/train cancelled before Sentinel cycle.")
                return True
            if choice == "explain":
                self._print_step_explanation(step)
        else:
            self.console.print(f"  [magenta]●[/magenta] {reasoning}")

        if incident.self_correction_status in (
            SelfCorrectionStatus.CAUGHT,
            SelfCorrectionStatus.STILL_MISSED,
        ):
            self.console.print(
                f"  [dim]Incident {incident.incident_id} already at "
                f"{incident.self_correction_status.value}; skipping cycle.[/dim]"
            )
            sentinel_result = {
                "final_status": incident.self_correction_status.value,
                "success": incident.self_correction_status == SelfCorrectionStatus.CAUGHT,
            }
        else:
            sentinel = SentinelEngine(
                self.session,
                model_provider=self.state.model_provider,
                model_id=self.state.model_id,
            )
            sentinel_result = sentinel.run_full_cycle(incident.incident_id)
            self._print_sentinel_transitions(incident.incident_id)

        sentinel_status = sentinel_result.get(
            "final_status", incident.self_correction_status.value
        )

        # Step 6: final summary
        summary = {
            "dataset_id": dataset_id,
            "csv_path": str(csv_path),
            "counts": {
                "normal": meta.get("normal_count", 0),
                "attack": meta.get("attack_count", 0),
                "suspicious": meta.get("suspicious_count", 0),
                "train": meta.get("train_count", 0),
                "validation": meta.get("validation_count", 0),
                "test": meta.get("test_count", 0),
                "replay": meta.get("replay_count", 0),
            },
            "alertness": {
                "model_id": alertness_metrics.get("model_id", ""),
                "precision": alertness_metrics.get("precision", 0.0),
                "recall": alertness_metrics.get("recall", 0.0),
                "f1_score": alertness_metrics.get("f1_score", 0.0),
                "false_positive_rate": alertness_metrics.get("false_positive_rate", 0.0),
                "false_negative_rate": alertness_metrics.get("false_negative_rate", 0.0),
                "inference_latency_ms": alertness_metrics.get("inference_latency_ms", 0.0),
            },
            "whatif": {
                "model_id": whatif_metrics.get("model_id", ""),
                "precision": whatif_metrics.get("precision", 0.0),
                "recall": whatif_metrics.get("recall", 0.0),
                "f1_score": whatif_metrics.get("f1_score", 0.0),
                "false_positive_rate": whatif_metrics.get("false_positive_rate", 0.0),
                "false_negative_rate": whatif_metrics.get("false_negative_rate", 0.0),
                "inference_latency_ms": whatif_metrics.get("inference_latency_ms", 0.0),
            },
            "sentinel_status": sentinel_status,
            "incident_id": incident.incident_id,
            "provider": provider_name,
        }
        self.renderer.train_summary(summary)
        return True


    def _do_artifact(self, args: list[str]) -> bool:
        artifact_type, action, target = parse_artifact_args(args)
        if not self._require_project():
            return True

        if not artifact_type or artifact_type == "all":
            self._artifact_menu()
            return True

        return self._run_artifact_command(artifact_type, action, target)

    def _do_orbit(self, args: list[str]) -> bool:
        return self._run_artifact_command("orbits", *parse_artifact_args(args, "orbits")[1:])

    def _do_ecosystem(self, args: list[str]) -> bool:
        return self._run_artifact_command("ecosystem", *parse_artifact_args(args, "ecosystem")[1:])

    def _do_replay(self, args: list[str]) -> bool:
        return self._run_artifact_command("replay", *parse_artifact_args(args, "replay")[1:])

    def _do_reach(self, args: list[str]) -> bool:
        return self._run_artifact_command("reach", *parse_artifact_args(args, "reach")[1:])

    def _do_segments(self, args: list[str]) -> bool:
        return self._run_artifact_command("segments", *parse_artifact_args(args, "segments")[1:])

    def _do_arena(self, args: list[str]) -> bool:
        return self._run_artifact_command("arena", *parse_artifact_args(args, "arena")[1:])

    def _do_arbor(self, args: list[str]) -> bool:
        return self._run_artifact_command("arbor", *parse_artifact_args(args, "arbor")[1:])

    def _do_impact(self, args: list[str]) -> bool:
        return self._run_artifact_command("impacts", *parse_artifact_args(args, "impacts")[1:])

    def _do_trophy(self, args: list[str]) -> bool:
        return self._run_artifact_command(
            "trophy_wall", *parse_artifact_args(args, "trophy_wall")[1:]
        )

    def _do_ledger(self, args: list[str]) -> bool:
        return self._run_artifact_command("ledger", *parse_artifact_args(args, "ledger")[1:])

    def _artifact_menu(self) -> None:
        if not self._require_project():
            return
        counts = list_artifact_counts(self.session, self.state.project_id)
        table = Table(title="ARTIFACTS")
        table.add_column("Type", style="cyan")
        table.add_column("Count", style="green")
        for atype in artifact_type_list():
            table.add_row(atype, str(counts.get(atype, 0)))
        self.console.print(table)

    def _run_artifact_command(self, artifact_type: str, action: str, target: str) -> bool:
        if not self._require_project():
            return True
        artifact_type = normalize_artifact_type(artifact_type)

        if action in ("list", "") and not target:
            items = list_artifacts_for_project(self.session, self.state.project_id)
            filtered = (
                [i for i in items if i["artifact_type"] == artifact_type]
                if artifact_type != "all"
                else items
            )
            if not filtered:
                self.renderer.info(f"No {artifact_type} artifacts yet.")
                return True
            table = Table(title=f"{artifact_type.upper()} ARTIFACTS")
            table.add_column("ID", style="cyan")
            table.add_column("Type", style="white")
            table.add_column("Created", style="dim")
            for item in filtered[:20]:
                table.add_row(
                    item["artifact_id"],
                    item["artifact_type"],
                    str(item.get("created_at", ""))[:19],
                )
            self.console.print(table)
            return True

        if action == "inspect":
            artifact_id = target or self._latest_artifact_id(artifact_type)
            if not artifact_id:
                self.renderer.error(f"No {artifact_type} artifact to inspect")
                return True
            data = get_artifact_by_id(
                self.session, self.state.project_id, artifact_type, artifact_id
            )
            if not data:
                data = get_latest_artifact(self.session, self.state.project_id, artifact_type)
            if data:
                self.renderer.json_payload(data.get("payload", {}))
            else:
                self.renderer.error(f"Artifact not found: {target}")
            return True

        if action in ("generate", "regenerate"):
            verb = "Regenerate" if action == "regenerate" else "Generate"
            objective = f"{verb} {artifact_type} for project {self.state.project_id}"
            run_agentic(
                self.session,
                self.state,
                self.renderer,
                objective,
                workspace=self.workspace,
                cancel_requested=self.cancel_event,
            )
            return True

        if action == "delete":
            if target:
                if delete_artifact(self.session, self.state.project_id, artifact_type, target):
                    self.renderer.success(f"Deleted {target}")
                else:
                    self.renderer.error(f"Artifact not found: {target}")
            else:
                count = delete_artifacts_of_type(self.session, self.state.project_id, artifact_type)
                self.renderer.success(f"Deleted {count} {artifact_type} artifacts")
            return True

        self.renderer.error(f"Unknown artifact action: {action}")
        return True

    def _do_inspect(self, args: list[str]) -> bool:
        if not args:
            self.renderer.error("Usage: /inspect <artifact_id> or /inspect <path>")
            return True
        target = args[0]

        if self._require_project():
            for atype in artifact_type_list():
                data = get_artifact_by_id(self.session, self.state.project_id, atype, target)
                if data:
                    self.renderer.json_payload(data.get("payload", {}))
                    return True

        try:
            data = build_tree(target, self.workspace)
            if len(data["lines"]) == 0 and data["path"]:
                return self._do_read([target])
            self.renderer.tree(data["path"], data["lines"])
        except (OSError, ValueError) as exc:
            self.renderer.error(str(exc))
        return True

    def _do_regenerate(self, args: list[str]) -> bool:
        if not args:
            self.renderer.error("Usage: /regenerate <artifact_id|type>")
            return True
        target = args[0]
        if not self._require_project():
            return True

        atype = normalize_artifact_type(target)
        if atype in artifact_type_list():
            return self._run_artifact_command(atype, "regenerate", "")

        for t in artifact_type_list():
            data = get_artifact_by_id(self.session, self.state.project_id, t, target)
            if data:
                return self._run_artifact_command(t, "regenerate", target)

        self.renderer.error(f"Could not resolve artifact: {target}")
        return True

    def _do_delete(self, args: list[str]) -> bool:
        if not args:
            self.renderer.error("Usage: /delete <artifact_id|type>")
            return True
        target = args[0]
        if not self._require_project():
            return True

        atype = normalize_artifact_type(target)
        if atype in artifact_type_list():
            return self._run_artifact_command(atype, "delete", "")

        for t in artifact_type_list():
            data = get_artifact_by_id(self.session, self.state.project_id, t, target)
            if data:
                return self._run_artifact_command(t, "delete", target)

        self.renderer.error(f"Could not resolve artifact: {target}")
        return True


    def _require_project(self) -> bool:
        if not self.state.project_id:
            self.renderer.error("No project selected. Use /project first.")
            return False
        return True

    def _active_context(self) -> ExecutionContext | None:
        if not self.state.active_execution_id:
            self.renderer.info("No active execution. Run an agentic query first.")
            return None
        return self._get_execution_context(self.state.active_execution_id)

    def _get_execution_context(self, execution_id: str) -> ExecutionContext | None:
        return self.session.exec(
            select(ExecutionContext).where(ExecutionContext.execution_id == execution_id)
        ).first()

    def _latest_artifact_id(self, artifact_type: str) -> str | None:
        data = get_latest_artifact(self.session, self.state.project_id, artifact_type)
        return data.get("artifact_id") if data else None

    def _model_list(self) -> list[dict[str, Any]]:
        return [m.model_dump() for m in default_models()]

    def _project_list(self) -> list[dict[str, Any]]:
        return [p.model_dump() for p in self.session.exec(select(Project)).all()]

    def _shutdown(self) -> None:
        self.session.close()


def select_one(title: str, items: list[tuple[str, str]]) -> str | None:
    """Thin wrapper reused by incident selection in the shell."""
    from anvaya.cli.selectors import select_one as _select_one

    return _select_one(title, items)
