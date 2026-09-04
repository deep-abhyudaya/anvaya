"""Rich rendering helpers for the ANVAYA interactive CLI."""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.table import Table


class AnvayaRenderer:
    """Terminal renderer tuned for the ANVAYA visual identity."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def header(self, title: str = "ANVAYA") -> None:
        """Print the startup header."""
        self.console.print(f"[bold cyan]{title}[/bold cyan] — Autonomous Cyber SOC")
        self.console.print("[dim]Type /help for commands.[/dim]\n")

    def status_line(self, state: dict[str, Any]) -> None:
        """Print a compact status block used at startup."""
        backend = (
            "[green]●[/green] connected" if state.get("backend") else "[red]✗[/red] not connected"
        )
        project = (
            f"[cyan]{state.get('project', '—')}[/cyan]"
            if state.get("project")
            else "[dim]none[/dim]"
        )
        model = (
            f"[cyan]{state.get('model', '—')}[/cyan]" if state.get("model") else "[dim]none[/dim]"
        )
        self.console.print(f"  Backend    {backend}")
        self.console.print(f"  Project    {project}")
        self.console.print(f"  Model      {model}")

    def event(self, event: dict[str, Any], compact: bool = True) -> None:
        """Render a single execution event to the terminal."""
        etype = event.get("type", "")
        label = event.get("label", "") or etype
        tool = event.get("tool_name", "")
        payload = event.get("payload") or {}
        artifact = event.get("artifact_ref", "")
        error = event.get("error_message", "")

        if etype == "agent.started":
            self.console.print("\n[bold cyan]AGENT · WORKING[/bold cyan]")
            self.console.print(f"  Objective\n    {payload.get('objective', label)}")
            return

        if etype == "agent.plan_created":
            steps = payload.get("steps", [])
            if steps:
                self.console.print(f"  [dim]Plan:[/dim] {' → '.join(str(s) for s in steps[:12])}")
            return

        if etype in ("agent.reasoning_started",):
            self.console.print(f"  [magenta]●[/magenta] {label}")
            return

        if etype == "agent.reasoning_completed":
            summary = payload.get("summary", "") or label
            if summary:
                self.console.print(f"  [magenta]↳[/magenta] {self._truncate(summary, 120)}")
            return

        if etype == "agent.decision_started":
            self.console.print(f"  [yellow]●[/yellow] {label}")
            return

        if etype == "agent.tool_requested":
            self.console.print(f"  [cyan]TOOL[/cyan] {tool}")
            return

        if etype == "tool.started":
            self.console.print(f"    [dim]→[/dim] {label}")
            return

        if etype == "tool.progress":
            if not compact:
                self.console.print(f"    [dim]...[/dim] {label}")
            return

        if etype == "tool.completed":
            out = payload.get("output_summary", "") or label
            self.console.print(f"    [green]✓[/green] {out}")
            return

        if etype == "tool.failed":
            msg = error or payload.get("output_summary", "") or label
            self.console.print(f"    [red]✗[/red] {msg}")
            return

        if etype == "agent.observation_created":
            summary = payload.get("summary", "") or label
            self.console.print(f"  [blue]↳[/blue] {self._truncate(summary, 120)}")
            return

        if etype == "generation.started":
            self.console.print(f"\n  [bold cyan]BUILD[/bold cyan] {label}")
            if not compact:
                target = payload.get("target", "")
                manifest_length = payload.get("manifest_length")
                if target or manifest_length is not None:
                    self.console.print(
                        f"    [dim]target: {target or '—'}  "
                        f"steps: {manifest_length if manifest_length is not None else '—'}[/dim]"
                    )
            return

        if etype == "generation.analyzing":
            self.console.print(f"  [dim]{label}[/dim]")
            return

        if etype == "artifact.world_build_started":
            self.console.print(f"  [dim]→ {label}[/dim]")
            return

        if etype == "artifact.world_build_completed":
            self.console.print(f"    [green]✓[/green] {label}")
            if not compact:
                entities = payload.get("entities")
                events = payload.get("events")
                incidents = payload.get("incidents")
                if entities is not None or events is not None or incidents is not None:
                    self.console.print(
                        f"      [dim]entities {entities or '—'}  "
                        f"events {events or '—'}  "
                        f"incidents {incidents or '—'}[/dim]"
                    )
            return

        if etype == "artifact.generating":
            if not compact:
                self.console.print(f"  [dim]→ {label}[/dim]")
            return

        if etype == "artifact.saved":
            if not compact:
                self.console.print(f"    [green]✓[/green] {label}")
            return

        if etype == "navigation.started":
            if not compact:
                self.console.print(f"  [dim]→ {label}[/dim]")
            return

        if etype == "navigation.completed":
            return

        if etype == "artifact.queued":
            return

        if etype == "artifact.thinking":
            index = payload.get("index", 0) or 0
            name = payload.get("name") or label
            live_reason = payload.get("live_reason", "")
            purpose = payload.get("purpose", "")
            building = payload.get("building", "")
            reason = live_reason or purpose or building or label
            self.console.print(
                f"  [magenta]●[/magenta] {index + 1:02d} {name} — "
                f"{self._truncate(reason, 100)}"
            )
            return

        if etype == "artifact.creating":
            self.console.print("    [dim]building...[/dim]")
            return

        if etype == "artifact.created":
            if artifact:
                self.console.print(
                    f"  [green]✓[/green] Artifact [cyan]{artifact}[/cyan] {label}"
                )
            else:
                index = payload.get("index")
                name = payload.get("name") or label
                if isinstance(index, int):
                    self.console.print(f"  [green]✓[/green] {index + 1:02d} {name}")
                else:
                    self.console.print(f"  [green]✓[/green] {name}")
            return

        if etype == "element.thinking":
            display = (
                payload.get("display")
                or payload.get("element_id")
                or payload.get("name")
                or label
            )
            reason = payload.get("reason", "")
            if reason and reason.startswith(f"Preparing {display}"):
                tail = reason[len(f"Preparing {display}") :].lstrip()
                if tail.startswith("—"):
                    tail = tail[1:].lstrip()
                reason = tail or reason
            reason = reason or label
            self.console.print(
                f"      [cyan]·[/cyan] {display} — {self._truncate(reason, 90)}"
            )
            return

        if etype == "element.mounted":
            if not compact:
                display = (
                    payload.get("display")
                    or payload.get("element_id")
                    or payload.get("name")
                    or label
                )
                self.console.print(f"      [dim]· {display} mounted[/dim]")
            return

        if etype == "artifact.attaching":
            if not compact:
                self.console.print(f"    [dim]→ {label}[/dim]")
            return

        if etype == "artifact.completed":
            if not compact:
                self.console.print(f"  [green]✓[/green] {label}")
            return

        if etype == "artifact.failed":
            msg = payload.get("error") or error or label
            self.console.print(f"  [red]✗[/red] {label} — {self._truncate(msg, 120)}")
            return

        if etype == "artifact.retrying":
            self.console.print(f"  [yellow]↻[/yellow] {label}")
            return

        if etype == "artifact.regenerating":
            self.console.print(f"  [yellow]↻[/yellow] {label}")
            return

        if etype == "artifact.deleted":
            self.console.print(f"  [green]✓[/green] {label}")
            return

        if etype == "artifact.progress":
            if not compact:
                status = payload.get("status", "")
                progress = payload.get("progress", 0.0)
                self.console.print(
                    f"  [dim]{label}[/dim] {status} {progress:.0%}"
                )
            return

        if etype == "agent.artifact_action_complete":
            if not compact:
                self.console.print(f"  [green]✓[/green] {label}")
            return

        if etype == "generation.finishing":
            if not compact:
                self.console.print(f"  [dim]{label}[/dim]")
            return

        if etype == "generation.completed":
            self.console.print(f"\n  [bold green]{label}[/bold green]")
            target = payload.get("target_artifact_type") or payload.get("target") or ""
            total = payload.get("total_artifacts")
            if target or total is not None:
                self.console.print(
                    f"    [dim]{target or '—'} · "
                    f"{total if total is not None else '—'} steps[/dim]"
                )
            return

        if etype == "generation.failed":
            self.console.print(f"\n  [bold red]{label}[/bold red]")
            msg = payload.get("error") or error
            if msg:
                self.console.print(f"  [red]{self._truncate(msg, 160)}[/red]")
            return

        if etype == "agent.message":
            message = payload.get("message", "") or label
            self.console.print(f"  [dim]{self._truncate(message, 140)}[/dim]")
            return

        if etype == "agent.verification_passed":
            conf = payload.get("confidence", "")
            self.console.print(f"  [green]✓ VERIFY[/green] confidence {conf}")
            return

        if etype == "agent.verification_failed":
            reason = payload.get("reason", error) or label
            self.console.print(f"  [yellow]⚠ VERIFY[/yellow] {reason}")
            return

        if etype == "agent.completed":
            self.console.print(f"\n[bold green]✓ {label}[/bold green]")
            summary = payload.get("result_summary", "") or ""
            if summary:
                self.console.print(f"  [dim]{self._truncate(summary, 160)}[/dim]")
            return

        if etype == "agent.failed":
            self.console.print(f"\n[bold red]✗ {label}[/bold red]")
            if error:
                self.console.print(f"  [red]{self._truncate(error, 160)}[/red]")
            return

        if etype == "agent.execution_interrupted":
            self.console.print(f"\n[yellow]● {label}[/yellow]")
            return

        if etype == "chat.user":
            self.console.print(f"[cyan]›[/cyan] {payload.get('message', label)}")
            return

        if etype == "chat.assistant":
            self.console.print(f"[magenta]ANVAYA[/magenta] {payload.get('message', label)}")
            return

        if not compact:
            self.console.print(f"  [dim]{etype} {label}[/dim]")

    def file(self, path: str, lines: list[str], start: int = 1) -> None:
        """Render a source file with line numbers and syntax highlighting."""
        ext = path.split(".")[-1] if "." in path else "text"
        code = "\n".join(lines)
        syntax = Syntax(
            code,
            ext,
            theme="monokai",
            line_numbers=True,
            start_line=start,
            background_color="default",
        )
        self.console.print(syntax)

    def file_summary(self, path: str, lines_read: int, total: int, start: int, end: int) -> None:
        self.console.print(
            f"[green]✓[/green] Loaded [cyan]{path}[/cyan] "
            f"({lines_read} of {total} lines, {start}-{end})"
        )

    def error(self, message: str, suggestion: str = "") -> None:
        self.console.print(f"[bold red]✗[/bold red] {message}")
        if suggestion:
            self.console.print(f"[dim]Try: {suggestion}[/dim]")

    def success(self, message: str) -> None:
        self.console.print(f"[green]✓[/green] {message}")

    def warning(self, message: str) -> None:
        self.console.print(f"[yellow]●[/yellow] {message}")

    def info(self, message: str) -> None:
        self.console.print(f"[dim]{message}[/dim]")

    def table(self, title: str, rows: list[list[str]]) -> None:
        table = Table(title=title, title_style="bold cyan")
        if rows:
            for _ in rows[0]:
                table.add_column()
            for row in rows:
                table.add_row(*row)
        self.console.print(table)

    def metrics_table(self, title: str, headers: list[str], rows: list[list[str]]) -> None:
        """Render a metrics table with explicit column headers."""
        table = Table(title=title, title_style="bold cyan")
        for header in headers:
            table.add_column(header, style="white")
        for row in rows:
            table.add_row(*row)
        self.console.print(table)

    def train_summary(self, summary: dict[str, Any]) -> None:
        """Render the final ``/train`` summary as a single panel of tables."""
        from rich.console import Group
        from rich.panel import Panel

        dataset_table = Table(title="Dataset", title_style="bold cyan")
        dataset_table.add_column("Item", style="white")
        dataset_table.add_column("Value", style="green")
        dataset_table.add_row("Dataset ID", str(summary.get("dataset_id", "")))
        dataset_table.add_row("CSV path", str(summary.get("csv_path", "")))
        counts = summary.get("counts", {})
        dataset_table.add_row("Normal events", str(counts.get("normal", 0)))
        dataset_table.add_row("Attack events", str(counts.get("attack", 0)))
        dataset_table.add_row("Suspicious events", str(counts.get("suspicious", 0)))
        dataset_table.add_row("Train events", str(counts.get("train", 0)))
        dataset_table.add_row("Validation events", str(counts.get("validation", 0)))
        dataset_table.add_row("Test events", str(counts.get("test", 0)))
        dataset_table.add_row("Replay events", str(counts.get("replay", 0)))

        alertness = summary.get("alertness", {})
        whatif = summary.get("whatif", {})
        metrics_table = Table(title="Model Metrics", title_style="bold cyan")
        metrics_table.add_column("Metric", style="white")
        metrics_table.add_column("Alertness", style="green")
        metrics_table.add_column("What-If", style="green")
        metrics_table.add_row(
            "Model ID", alertness.get("model_id", ""), whatif.get("model_id", "")
        )
        metrics_table.add_row(
            "Precision",
            f"{alertness.get('precision', 0):.4f}",
            f"{whatif.get('precision', 0):.4f}",
        )
        metrics_table.add_row(
            "Recall",
            f"{alertness.get('recall', 0):.4f}",
            f"{whatif.get('recall', 0):.4f}",
        )
        metrics_table.add_row(
            "F1",
            f"{alertness.get('f1_score', 0):.4f}",
            f"{whatif.get('f1_score', 0):.4f}",
        )
        metrics_table.add_row(
            "FPR",
            f"{alertness.get('false_positive_rate', 0):.4f}",
            f"{whatif.get('false_positive_rate', 0):.4f}",
        )
        metrics_table.add_row(
            "FNR",
            f"{alertness.get('false_negative_rate', 0):.4f}",
            f"{whatif.get('false_negative_rate', 0):.4f}",
        )
        metrics_table.add_row(
            "Latency (ms)",
            f"{alertness.get('inference_latency_ms', 0):.2f}",
            f"{whatif.get('inference_latency_ms', 0):.2f}",
        )

        sentinel_table = Table(title="Sentinel Cycle", title_style="bold cyan")
        sentinel_table.add_column("Item", style="white")
        sentinel_table.add_column("Value", style="green")
        sentinel_table.add_row("Incident ID", str(summary.get("incident_id", "")))
        sentinel_table.add_row("Final status", str(summary.get("sentinel_status", "")))

        provider_table = Table(title="Narration Provider", title_style="bold cyan")
        provider_table.add_column("Provider", style="white")
        provider_table.add_row(str(summary.get("provider", "")))

        group = Group(dataset_table, metrics_table, sentinel_table, provider_table)
        self.console.print(
            Panel(group, title="TRAINING SUMMARY", border_style="cyan")
        )

    def tree(self, path: str, tree_lines: list[str]) -> None:
        self.console.print(f"[bold cyan]{path}[/bold cyan]")
        for line in tree_lines:
            self.console.print(line)

    def search_results(self, results: list[dict[str, Any]]) -> None:
        if not results:
            self.console.print("[dim]No matches.[/dim]")
            return
        for r in results:
            file = r.get("file", "")
            line = r.get("line", 0)
            text = r.get("text", "")
            self.console.print(f"[cyan]{file}[/cyan]:[dim]{line}[/dim]  {text[:120]}")

    def markdown(self, text: str) -> None:
        self.console.print(Markdown(text))

    def json_payload(self, payload: dict[str, Any]) -> None:
        self.console.print(
            Syntax(json.dumps(payload, indent=2, default=str), "json", theme="monokai")
        )

    @staticmethod
    def _truncate(text: str, max_len: int = 120) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "…"


def get_console() -> Console:
    """Return the CLI's shared Rich console."""
    return Console()
