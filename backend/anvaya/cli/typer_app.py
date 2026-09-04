"""Typer-based ANVAYA commands."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from sqlmodel import select

from anvaya.db import get_session_sync, init_db
from anvaya.startuped_signals import emit_cli_signal

app = typer.Typer(name="anvaya", help="ANVAYA — Autonomous Cyber SOC Platform")
console = Console()


def _format_scenario_description(scenario: dict[str, Any]) -> str:
    """Return a plain-language description of the simulated attack."""
    description = scenario.get("description", "")
    if not description:
        return f"{scenario.get('attack_family', 'attack')} scenario"
    if not description.endswith("."):
        description += "."
    return description


def _model_metrics_table(metrics: dict[str, Any], title: str) -> Table:
    """Build the shared Rich metrics table used by train and demo."""
    table = Table(title=title)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Precision", f"{metrics.get('precision', 0):.4f}")
    table.add_row("Recall", f"{metrics.get('recall', 0):.4f}")
    table.add_row("F1", f"{metrics.get('f1_score', 0):.4f}")
    table.add_row("FPR", f"{metrics.get('false_positive_rate', 0):.4f}")
    table.add_row("FNR", f"{metrics.get('false_negative_rate', 0):.4f}")
    table.add_row("Latency (ms)", f"{metrics.get('inference_latency_ms', 0):.2f}")
    return table


def _print_dataset_generation(step: dict[str, Any]) -> None:
    """Narrate the background dataset generation step."""
    console.print("\n[bold cyan]Generating background telemetry[/bold cyan]")
    console.print(
        "  Building normal traffic patterns the detector will be trained against, "
        "plus a mix of suspicious and attack-like events so the models learn the difference."
    )
    persisted = step.get("events_persisted", 0)
    meta = step.get("metadata") or {}
    if meta:
        console.print(
            f"  [green]Events persisted:[/green] {persisted}  "
            f"[dim](train {meta.get('train_count', 0)} / "
            f"validation {meta.get('validation_count', 0)} / "
            f"test {meta.get('test_count', 0)})[/dim]"
        )
        console.print(
            f"  [dim]Mix: {meta.get('normal_count', 0)} normal, "
            f"{meta.get('attack_count', 0)} attack, "
            f"{meta.get('suspicious_count', 0)} suspicious[/dim]"
        )
    else:
        console.print(f"  [green]Events persisted:[/green] {persisted}")


def _print_train_models(step: dict[str, Any]) -> None:
    """Narrate the model training step and print metric tables."""
    console.print("\n[bold cyan]Training models[/bold cyan]")
    console.print(
        "  Training the Alertness Engine (Isolation Forest) and What-If model "
        "(Logistic Regression) on this dataset."
    )
    alertness = step.get("alertness_metrics") or {}
    whatif = step.get("whatif_metrics") or {}
    if alertness:
        console.print(
            _model_metrics_table(alertness, f"Alertness — {alertness.get('model_id', '')}")
        )
    if whatif:
        console.print(_model_metrics_table(whatif, f"What-If — {whatif.get('model_id', '')}"))


def _print_generate_telemetry(step: dict[str, Any]) -> None:
    """Narrate the live attack telemetry generation step."""
    console.print("\n[bold cyan]Simulating a live attack[/bold cyan]")
    description = _format_scenario_description(step)
    console.print(f"  {description}")
    console.print(
        f"  [green]Events generated:[/green] {step.get('events_generated', 0)}  "
        f"[dim]({step.get('events_persisted', 0)} new events persisted)[/dim]"
    )
    console.print(f"  [dim]Scenario:[/dim] {step.get('scenario_id', '')}")


def _print_create_incident(step: dict[str, Any]) -> None:
    """Narrate incident creation."""
    console.print("\n[bold cyan]Opening incident[/bold cyan]")
    console.print(f"  Incident [bold]{step.get('incident_id', '')}[/bold] opened for tracking.")
    if step.get("user"):
        console.print(f"  [dim]User:[/dim] {step['user']}  [dim]Host:[/dim] {step.get('host', '')}")


def _print_pre_patch_detection(step: dict[str, Any]) -> None:
    """Narrate the pre-patch detection result."""
    console.print(
        "\n[bold cyan]Checking whether today's detection rules catch this attack[/bold cyan]"
    )
    if step.get("detected"):
        console.print("  [bold green]🟢 DETECTED[/bold green]")
        console.print(
            "  The attack matched an existing detection rule and was flagged immediately."
        )
    else:
        console.print("  [bold red]🔴 MISSED[/bold red]")
        console.print(
            "  The attacker's actions matched normal-looking traffic patterns, "
            "so the current rules did not fire. This is the failure the self-correction "
            "loop is designed to close."
        )
        if step.get("events_processed") is not None:
            console.print(
                f"  [dim]Events examined: {step['events_processed']}  "
                f"Flagged as suspicious: {step.get('events_flagged', 0)}[/dim]"
            )


def _print_self_correction(step: dict[str, Any]) -> None:
    """Narrate the Sentinel self-correction cycle in detail."""
    if step.get("status") == "skipped":
        console.print("\n[bold cyan]Self-correction[/bold cyan]")
        reason = step.get("reason", "")
        if reason == "pre_patch_detected":
            console.print(
                "  [green]No self-correction needed — the incident was already caught "
                "by the pre-patch rules.[/green]"
            )
        else:
            console.print(f"  [dim]Self-correction skipped: {reason}[/dim]")
        return

    sc = step.get("result") or {}
    console.print("\n[bold cyan]Self-correction: backtracking from the miss[/bold cyan]")
    console.print(
        "  Sentinel walks backward through the attack telemetry, extracts the "
        "features that should have triggered, proposes a new rule, validates it, "
        "and replays the same attack to confirm it is now caught."
    )

    for inner in sc.get("steps", []):
        name = inner.get("step", "")
        result = inner.get("result") or {}
        if name == "backtrack":
            evidence = result.get("evidence", [])
            features: list[str] = []
            for ev in evidence:
                suspicious = ev.get("suspicious_features") or {}
                features.extend(sorted(suspicious.keys()))
            unique_features = sorted(set(features))
            console.print(
                f"  [magenta]↺ backtrack[/magenta]: found {result.get('evidence_count', 0)} "
                f"attack-related events. Extracted suspicious features: "
                f"{', '.join(unique_features) if unique_features else 'none'}."
            )
        elif name == "propose_rule":
            conditions = result.get("conditions", {})
            cond_list = conditions.get("conditions", [])
            console.print(
                f"  [magenta]✎ propose_rule[/magenta]: candidate rule "
                f"[bold]{result.get('rule_name', '')}[/bold] — "
                f"{len(cond_list)} condition(s)."
            )
            for cond in cond_list[:3]:
                field = cond.get("field", "")
                operator = cond.get("operator", "")
                value = cond.get("value", "")
                console.print(f"    [dim]• {field} {operator} {value}[/dim]")
        elif name == "validate_rule":
            precision = result.get("precision", 0.0)
            recall = result.get("recall", 0.0)
            f1 = result.get("f1_score", 0.0)
            verdict = (
                "this rule reliably catches the real attack "
                "without raising false alarms on normal traffic"
                if precision >= 0.9 and recall >= 0.9
                else "this rule catches the attack but may need review"
            )
            console.print(
                f"  [magenta]✓ validate_rule[/magenta]: precision {precision:.4f}, "
                f"recall {recall:.4f}, F1 {f1:.4f} — {verdict}."
            )
        elif name == "replay":
            caught = result.get("post_patch_detected", False)
            status = (
                "[bold green]🟢 CAUGHT[/bold green]"
                if caught
                else "[bold red]🔴 STILL MISSED[/bold red]"
            )
            console.print(
                f"  [magenta]↻ replay_attack[/magenta]: replaying the identical attack... {status}"
            )


def _print_blastscope(step: dict[str, Any]) -> None:
    """Narrate the BlastScope blast-radius step."""
    result = step.get("result") or {}
    console.print("\n[bold cyan]BlastScope: what could the attacker have reached?[/bold cyan]")
    if result.get("error"):
        console.print(f"  [red]BlastScope failed:[/red] {result['error']}")
        return
    reachable = result.get("total_reachable", 0)
    critical = result.get("critical_exposed", 0)
    depth = result.get("max_depth", 0)
    impact = result.get("impact_score", 0.0)
    console.print(
        f"  The attack could have reached [bold]{reachable}[/bold] systems within "
        f"[bold]{depth}[/bold] hops, including [bold]{critical}[/bold] critical asset(s)."
    )
    console.print(
        f"  [dim]Composite impact score: {impact:.4f} — "
        f"systems the organization cannot afford to lose.[/dim]"
    )


def _print_whatif(step: dict[str, Any]) -> None:
    """Narrate the What-If counterfactual step."""
    result = step.get("result") or {}
    console.print("\n[bold cyan]What-If analysis[/bold cyan]")
    if result.get("error"):
        console.print(f"  [red]What-If analysis failed:[/red] {result['error']}")
        return
    original = result.get("original_score", 0.0)
    counter = result.get("counterfactual_score", 0.0)
    delta = result.get("score_delta", 0.0)
    console.print(
        "  Testing a hypothetical defensive change: what if this login had required "
        "a second factor and came from a known device?"
    )
    console.print(
        f"  This single change would have reduced the risk score from "
        f"[bold]{original:.4f}[/bold] to [bold]{counter:.4f}[/bold] "
        f"(delta [bold]{delta:.4f}[/bold])."
    )
    if result.get("explanation"):
        console.print(f"  [dim]{result['explanation']}[/dim]")


def _print_seal(step: dict[str, Any]) -> None:
    """Narrate the incident seal step."""
    console.print("\n[bold cyan]Sealing the case file[/bold cyan]")
    console.print(
        "  Sealing the complete case file — the miss, the fix, the retest, "
        "the blast radius, the what-if — into a tamper-evident record."
    )
    console.print(f"  [green]Audit record:[/green] {step.get('record_id', '')}")


def _print_verify_audit(step: dict[str, Any]) -> None:
    """Narrate the audit chain verification step."""
    console.print("\n[bold cyan]Verifying the audit chain[/bold cyan]")
    if step.get("chain_valid"):
        records = step.get('audit_records', 0)
        console.print(
            f"  [bold green]✓ verified[/bold green] — {records} records, chain intact."
        )
    else:
        console.print(
            f"  [bold red]✗ chain validation failed[/bold red] — "
            f"{step.get('audit_records', 0)} records present."
        )


def _print_demo_step(step_name: str, step: dict[str, Any], *, delay: float = 0.0) -> None:
    """Dispatch to the right narration for a single demo step."""
    if step_name == "generate_background_dataset":
        _print_dataset_generation(step)
    elif step_name == "train_models":
        _print_train_models(step)
    elif step_name == "generate_telemetry":
        _print_generate_telemetry(step)
    elif step_name == "create_incident":
        _print_create_incident(step)
    elif step_name == "pre_patch_detection":
        _print_pre_patch_detection(step)
    elif step_name == "self_correction":
        _print_self_correction(step)
    elif step_name == "blastscope":
        _print_blastscope(step)
    elif step_name == "whatif":
        _print_whatif(step)
    elif step_name == "seal":
        _print_seal(step)
    elif step_name == "verify_audit":
        _print_verify_audit(step)
    else:
        console.print(f"  [dim]{step_name}: {step.get('status', '')}[/dim]")
    if delay:
        time.sleep(delay)


@app.command()
def demo(
    delay: float = typer.Option(
        0.35,
        help="Seconds to pause between narration blocks for live-demo pacing (0 = no delay)",
    ),
):
    """Run the complete self-correction demo with step-by-step narration."""
    console.print("[bold cyan]ANVAYA — Self-Correction Demo[/bold cyan]\n")
    console.print(
        "This demo runs a complete attack through the ANVAYA pipeline: "
        "miss → backtrack → new rule → replay caught → blast radius → what-if → sealed audit.\n"
    )
    init_db()
    session = get_session_sync()

    from anvaya.demo.orchestrator import DemoOrchestrator

    orchestrator = DemoOrchestrator(session)

    def on_step(step_name: str, step: dict[str, Any]) -> None:
        _print_demo_step(step_name, step, delay=delay)

    result = orchestrator.run_full_demo(on_step=on_step)

    console.print("\n" + "=" * 60)
    if result.get("success"):
        console.print("[bold green]✓ DEMO SUCCESS[/bold green]")
        console.print(f"  Incident: {result.get('incident_id')}")
        console.print(f"  Scenario: {result.get('scenario_id')}")
        console.print(f"  Audit Valid: {result.get('audit_valid')}")
    else:
        console.print("[bold red]✗ DEMO FAILED[/bold red]")
        console.print(f"  Error: {result.get('error', 'Unknown')}")

    session.close()


def _print_incident_compact(incident: dict[str, Any]) -> None:
    """Print one compact line for a batch incident."""
    steps = {s.get("step"): s for s in incident.get("steps", [])}
    pre = steps.get("pre_patch_detection", {})
    blast = steps.get("blastscope", {}).get("result") or {}
    whatif = steps.get("whatif", {}).get("result") or {}
    sc = steps.get("self_correction", {}).get("result") or {}

    scenario_id = incident.get("scenario_id", "")
    incident_id = incident.get("incident_id", "")
    pre_result = "DETECTED" if pre.get("detected") else "MISSED"
    final = "caught" if pre.get("detected") else sc.get("final_status", "-")
    if not pre.get("detected") and sc.get("final_status") != "caught":
        final = sc.get("final_status", "failed")
    reach = blast.get("total_reachable", 0)
    delta = whatif.get("score_delta", 0.0)
    color = "green" if pre.get("detected") or final == "caught" else "red"
    console.print(
        f"  [{color}]{incident_id}[/{color}]  {scenario_id}  "
        f"pre:{pre_result}  final:{final}  "
        f"reach:{reach}  Δ:{delta:.4f}"
    )


def _print_batch_summary(result: dict[str, Any]) -> None:
    """Print the final batch summary and table."""
    summary = result.get("summary", {})
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]Batch Summary[/bold cyan]")
    console.print(
        f"  Total incidents: [bold]{summary.get('total', 0)}[/bold]  "
        f"([green]{summary.get('caught_immediately', 0)}[/green] caught immediately, "
        f"[yellow]{summary.get('missed_then_corrected', 0)}[/yellow] missed then corrected, "
        f"[red]{summary.get('failed_self_correction', 0)}[/red] failed to self-correct)"
    )
    templates = summary.get("templates_used", [])
    if templates:
        console.print(f"  Scenario templates used: {', '.join(templates)}")
    if summary.get("variations_per_template"):
        per = summary["variations_per_template"]
        rem = summary.get("remainder", 0)
        detail = f"{per} variation(s) × {len(templates)} template(s)"
        if rem:
            detail += f" + {rem} extra"
        console.print(f"  Batch composition: {detail} = {summary.get('total', 0)} incidents")

    table = Table(title="Batch Results")
    table.add_column("Incident ID", style="cyan")
    table.add_column("Scenario", style="white")
    table.add_column("Pre-Patch", style="yellow")
    table.add_column("Final Status", style="green")
    table.add_column("Blast Reach", justify="right")
    table.add_column("What-If Δ", justify="right")

    for incident in result.get("incidents", []):
        steps = {s.get("step"): s for s in incident.get("steps", [])}
        pre = steps.get("pre_patch_detection", {})
        blast = steps.get("blastscope", {}).get("result") or {}
        whatif = steps.get("whatif", {}).get("result") or {}
        sc = steps.get("self_correction", {}).get("result") or {}

        pre_result = "DETECTED" if pre.get("detected") else "MISSED"
        if pre.get("detected"):
            final = "caught (pre-patch)"
        elif sc.get("final_status") == "caught":
            final = "caught (self-corrected)"
        else:
            final = sc.get("final_status", "-")

        table.add_row(
            incident.get("incident_id", ""),
            incident.get("scenario_id", ""),
            pre_result,
            final,
            str(blast.get("total_reachable", 0)),
            f"{whatif.get('score_delta', 0.0):.4f}",
        )

    console.print(table)


@app.command(name="demo-batch")
def demo_batch(
    count: int = typer.Option(20, help="Number of incidents to run through the full cycle"),
    scenarios: str = typer.Option(
        "all", help="Comma-separated scenario IDs to draw from, or 'all' for every ATK-* template"
    ),
    delay: float = typer.Option(
        0.1,
        help="Seconds to pause between compact incident lines.",
    ),
    full_detail_count: int = typer.Option(
        2,
        help="Number of incidents to narrate in full detail before switching to one-line summaries",
    ),
):
    """Run the full self-correction cycle across a batch of varied incidents."""
    console.print("[bold cyan]ANVAYA — Multi-Incident Batch Demo[/bold cyan]\n")
    console.print(
        "Training once, then running many distinct-looking incidents through the same "
        "detection and self-correction pipeline."
    )
    console.print(
        "[dim]Batch composition: the 4 base attack templates are varied by actor, host, "
        "and timestamp to produce the requested number of incidents.[/dim]\n"
    )

    init_db()
    session = get_session_sync()

    from anvaya.demo.orchestrator import DemoOrchestrator

    orchestrator = DemoOrchestrator(session)
    detail_remaining = full_detail_count

    def on_step(step_name: str, step: dict[str, Any]) -> None:
        # During full-detail mode, the per-step narration is handled by on_incident.
        # When compact, we intentionally do not stream every sub-step to keep output readable.
        pass

    def on_incident(incident: dict[str, Any]) -> None:
        nonlocal detail_remaining
        if detail_remaining > 0:
            console.print(
                f"\n[bold cyan]Incident {incident['incident_id']} — full detail "
                f"({detail_remaining} of {full_detail_count})[/bold cyan]"
            )
            for step in incident.get("steps", []):
                _print_demo_step(step.get("step", ""), step, delay=0.0)
            detail_remaining -= 1
        else:
            if delay:
                time.sleep(delay)
            _print_incident_compact(incident)

    result = orchestrator.run_batch_demo(
        count=count,
        scenarios=scenarios,
        on_step=on_step,
        on_incident=on_incident,
    )

    _print_batch_summary(result)

    if result.get("success"):
        console.print("\n[bold green]✓ BATCH DEMO SUCCESS[/bold green]")
    else:
        console.print("\n[bold red]✗ BATCH DEMO FAILED[/bold red]")
        console.print(
            f"  Error: {result.get('error', 'One or more incidents failed self-correction')}"
        )

    session.close()


@app.command()
def data(
    action: str = typer.Argument(help="generate|validate|summarize"),
    seed: int = typer.Option(42, help="Random seed"),
):
    """Dataset operations."""
    init_db()
    session = get_session_sync()

    if action == "generate":
        from anvaya.data import DataFactory

        factory = DataFactory(session)
        result = factory.generate({"seed": seed})
        console.print(f"[green]Dataset generated:[/green] {result['dataset_id']}")
        console.print(f"  Events persisted: {result['persisted_events']}")
        meta = result["metadata"]
        console.print(
            f"  Train: {meta['train_count']}, "
            f"Val: {meta['validation_count']}, "
            f"Test: {meta['test_count']}"
        )
        console.print(f"  Normal: {meta['normal_count']}, Attack: {meta['attack_count']}")
    elif action == "validate":
        from sqlmodel import select

        from anvaya.models.dataset import DatasetVersion

        datasets = session.exec(select(DatasetVersion)).all()
        for ds in datasets:
            from anvaya.data import DataFactory

            factory = DataFactory(session)
            result = factory.validate(ds.dataset_id)
            status_color = "green" if result["valid"] else "red"
            console.print(f"[{status_color}]{ds.dataset_id}[/]: valid={result['valid']}")
    elif action == "summarize":
        from sqlmodel import select

        from anvaya.models.dataset import DatasetVersion

        datasets = session.exec(select(DatasetVersion)).all()
        for ds in datasets:
            console.print(
                f"{ds.dataset_id}: train={ds.train_count} "
                f"val={ds.validation_count} test={ds.test_count}"
            )
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)

    session.close()


def _print_sentinel_history(session, incident_id: str, scenario_id: str) -> None:
    """Print the real detail from a previously completed self-correction cycle."""
    from anvaya.models.audit import AuditRecord
    from anvaya.models.replay import ReplayRun
    from anvaya.models.rule import DetectionRule
    from anvaya.models.telemetry import TelemetryEvent

    console.print(
        "\n[bold cyan]A self-correction cycle has already been completed "
        "for this scenario[/bold cyan]"
    )
    console.print("  Here's what it found:")

    rules = session.exec(
        select(DetectionRule).where(DetectionRule.incident_id == incident_id)
    ).all()
    if rules:
        rule = rules[-1]
        console.print(f"  [green]Rule:[/green] {rule.name} ({rule.rule_id})")
        try:
            conds = json.loads(rule.conditions_json)
            for cond in conds.get("conditions", [])[:3]:
                field = cond.get("field", "")
                operator = cond.get("operator", "")
                value = cond.get("value", "")
                console.print(f"    [dim]• {field} {operator} {value}[/dim]")
        except Exception:
            pass

    replay = session.exec(select(ReplayRun).where(ReplayRun.incident_id == incident_id)).first()
    if replay:
        console.print(
            f"  [green]Replay:[/green] pre-patch detected={replay.pre_patch_detected}, "
            f"post-patch detected={replay.post_patch_detected}, status={replay.status.value}"
        )

    attack_events = session.exec(
        select(TelemetryEvent)
        .where(TelemetryEvent.incident_id == incident_id)
        .where(TelemetryEvent.is_attack == True)  # noqa: E712
        .order_by(TelemetryEvent.timestamp.asc())
    ).all()
    if attack_events:
        feature_keys: set[str] = set()
        for evt in attack_events:
            from anvaya.ml.features import extract_features

            features = extract_features(evt)
            feature_keys.update(k for k, v in features.items() if v != 0)
        console.print(f"  [green]Backtracked features:[/green] {', '.join(sorted(feature_keys))}")

    audit_count = len(
        session.exec(select(AuditRecord).where(AuditRecord.incident_id == incident_id)).all()
    )
    console.print(f"  [dim]Audit records in chain: {audit_count}[/dim]")


@app.command()
def train():
    """Train ML models on existing telemetry data with full narration."""
    emit_cli_signal("train", "started")
    init_db()
    session = get_session_sync()

    from sqlmodel import select

    from anvaya.data import DataFactory
    from anvaya.ml.alertness import AlertnessEngine
    from anvaya.models.enums import SelfCorrectionStatus
    from anvaya.models.incident import Incident
    from anvaya.models.telemetry import TelemetryEvent
    from anvaya.sentinel import SentinelEngine
    from anvaya.simulator.scenarios import get_self_correction_scenario
    from anvaya.whatif import WhatIfEngine

    console.print("[bold cyan]ANVAYA — Train Models[/bold cyan]\n")

    events = session.exec(select(TelemetryEvent)).all()

    if not events:
        console.print(
            "[yellow]No telemetry events found. Generating a fresh dataset first...[/yellow]"
        )
        factory = DataFactory(session)
        ds_result = factory.generate(
            {
                "seed": 42,
                "normal_count": 3,
                "suspicious_count": 2,
                "attack_count": 4,
                "include_self_correction": True,
            }
        )
        meta = ds_result.get("metadata", {})
        console.print("[green]Dataset generated:[/green] " + ds_result.get("dataset_id", ""))
        console.print(
            f"  Events: {ds_result.get('persisted_events', 0)}  "
            f"[dim](train {meta.get('train_count', 0)} / "
            f"val {meta.get('validation_count', 0)} / "
            f"test {meta.get('test_count', 0)} / "
            f"replay {meta.get('replay_count', 0)})[/dim]"
        )
        events = session.exec(select(TelemetryEvent)).all()
        emit_cli_signal("train", "dataset_generated", {"datasetId": ds_result.get("dataset_id")})

    console.print("\n[bold cyan]Training the Alertness Engine[/bold cyan]")
    console.print(
        "  Isolation Forest learns normal vs. anomalous patterns from the "
        f"{len(events)} telemetry events."
    )
    alertness = AlertnessEngine(session)
    alertness_metrics = alertness.train(events)
    emit_cli_signal(
        "train",
        "alertness_completed",
        {"modelId": alertness_metrics.get("model_id")},
    )
    console.print(
        _model_metrics_table(
            alertness_metrics, f"Alertness — {alertness_metrics.get('model_id', '')}"
        )
    )

    console.print("\n[bold cyan]Training the What-If model[/bold cyan]")
    console.print(
        "  Logistic Regression learns which features drive risk so we can test "
        "counterfactual defensive changes."
    )
    whatif = WhatIfEngine(session)
    whatif_metrics = whatif.train(events)
    emit_cli_signal(
        "train",
        "whatif_completed",
        {"modelId": whatif_metrics.get("model_id")},
    )
    console.print(
        _model_metrics_table(whatif_metrics, f"What-If — {whatif_metrics.get('model_id', '')}")
    )

    console.print("\n[bold cyan]Sentinel self-correction cycle[/bold cyan]")
    scenario = get_self_correction_scenario()
    incident = session.exec(
        select(Incident).where(Incident.scenario_id == scenario.scenario_id)
    ).first()

    if not incident:
        console.print(f"  Creating the self-correction incident for {scenario.scenario_id}...")
        from anvaya.demo.orchestrator import DemoOrchestrator

        orchestrator = DemoOrchestrator(session)
        # Generate the replay telemetry for the self-correction scenario.
        events_data = orchestrator.generator.generate_for_scenario(
            scenario,
            base_time=datetime(2026, 1, 4, tzinfo=timezone.utc),
            replay_id=f"REPLAY-{scenario.scenario_id}-PRE",
            is_replay=True,
        )
        orchestrator._persist_telemetry_events(events_data)
        persisted = session.exec(select(TelemetryEvent)).all()
        scenario_events = [e for e in persisted if e.scenario_id == scenario.scenario_id]
        if not scenario_events:
            console.print("[red]Failed to create self-correction telemetry.[/red]")
            session.close()
            raise typer.Exit(1)
        incident = orchestrator._create_incident_for_scenario(scenario, scenario_events)

    if incident.self_correction_status in (
        SelfCorrectionStatus.CAUGHT,
        SelfCorrectionStatus.STILL_MISSED,
    ):
        console.print(
            f"  Incident {incident.incident_id} is already at "
            f"[bold]{incident.self_correction_status.value}[/bold]."
        )
        _print_sentinel_history(session, incident.incident_id, scenario.scenario_id)
    else:
        console.print(
            f"  Running the full self-correction cycle on incident {incident.incident_id}..."
        )
        sentinel = SentinelEngine(session)
        emit_cli_signal("train", "sentinel_started", {"incidentId": incident.incident_id})
        sc_result = sentinel.run_full_cycle(incident.incident_id)
        emit_cli_signal(
            "train",
            "sentinel_completed",
            {"incidentId": incident.incident_id, "success": bool(sc_result.get("success"))},
        )

        if sc_result.get("success"):
            console.print("  [bold green]✓ Self-correction reached CAUGHT[/bold green]")
        else:
            console.print(
                f"  [bold red]✗ Self-correction ended at {sc_result.get('final_status')}[/bold red]"
            )

        for inner in sc_result.get("steps", []):
            name = inner.get("step", "")
            result = inner.get("result") or {}
            if name == "backtrack":
                evidence = result.get("evidence", [])
                features: set[str] = set()
                for ev in evidence:
                    suspicious = ev.get("suspicious_features") or {}
                    features.update(suspicious.keys())
                feature_str = ", ".join(sorted(features)) if features else "none"
                console.print(
                    f"    [magenta]↺ backtrack[/magenta]: {result.get('evidence_count', 0)} "
                    f"attack events; features: {feature_str}"
                )
            elif name == "propose_rule":
                console.print(
                    f"    [magenta]✎ propose_rule[/magenta]: {result.get('rule_name', '')} "
                    f"({len((result.get('conditions') or {}).get('conditions', []))} conditions)"
                )
            elif name == "validate_rule":
                console.print(
                    f"    [magenta]✓ validate_rule[/magenta]: precision "
                    f"{result.get('precision', 0):.4f}, recall {result.get('recall', 0):.4f}, "
                    f"F1 {result.get('f1_score', 0):.4f}"
                )
            elif name == "replay":
                caught = result.get("post_patch_detected", False)
                status = (
                    "[bold green]🟢 CAUGHT[/bold green]"
                    if caught
                    else "[bold red]🔴 MISSED[/bold red]"
                )
                console.print(f"    [magenta]↻ replay[/magenta]: ... {status}")

    session.close()
    emit_cli_signal("train", "completed")


@app.command()
def evaluate():
    """Evaluate ML models and print metrics."""
    init_db()
    session = get_session_sync()

    from sqlmodel import select

    from anvaya.models.model_version import ModelVersion

    models = session.exec(select(ModelVersion).order_by(ModelVersion.created_at.desc())).all()

    if not models:
        console.print("[red]No trained models found. Run 'anvaya train' first.[/red]")
        raise typer.Exit(1)

    table = Table(title="Model Evaluation Results")
    table.add_column("Model ID", style="cyan")
    table.add_column("Type", style="white")
    table.add_column("Precision", style="green")
    table.add_column("Recall", style="green")
    table.add_column("F1", style="green")
    table.add_column("FPR", style="yellow")
    table.add_column("FNR", style="yellow")
    table.add_column("Latency(ms)", style="dim")

    for m in models:
        table.add_row(
            m.model_id,
            m.model_type,
            f"{m.precision:.4f}",
            f"{m.recall:.4f}",
            f"{m.f1_score:.4f}",
            f"{m.false_positive_rate:.4f}",
            f"{m.false_negative_rate:.4f}",
            f"{m.inference_latency_ms:.2f}",
        )
    console.print(table)
    session.close()


@app.command()
def world(
    seed: int = typer.Option(2026, help="Random seed for the world"),
    normal_count: int = typer.Option(3, help="Normal background scenarios"),
    suspicious_count: int = typer.Option(2, help="Suspicious scenarios"),
    attack_count: int = typer.Option(3, help="Attack scenarios"),
    include_self_correction: bool = typer.Option(
        True, help="Include the intentional self-correction miss scenario"
    ),
):
    """Build the complete ANVAYA world from a fresh synthetic dataset.

    This is the World Architect entry point: it generates a clean background
    dataset, trains models, builds the asset graph, raises incidents, and runs
    each incident through detection/self-correction, BlastScope, What-If and
    sealed audit.
    """
    init_db()
    session = get_session_sync()

    from anvaya.world_architect import WorldArchitect

    architect = WorldArchitect(session)
    config = {
        "seed": seed,
        "normal_count": normal_count,
        "suspicious_count": suspicious_count,
        "attack_count": attack_count,
        "include_self_correction": include_self_correction,
    }

    console.print("[bold cyan]ANVAYA — World Architect[/bold cyan]")
    console.print(f"  seed: {seed}, normal: {normal_count}, attack: {attack_count}")

    try:
        manifest = architect.build(config)
        console.print("[bold green]World built.[/bold green]")
        table = Table(title="World Manifest")
        table.add_column("Module", style="cyan")
        table.add_column("Count", style="green")
        for key, value in manifest.items():
            if key in (
                "incident_ids",
                "scenarios",
                "source_type",
                "leakage_check_passed",
                "domain",
                "audit_chain_errors",
                "audit_chain_valid",
            ):
                continue
            if isinstance(value, int):
                table.add_row(key, str(value))
        console.print(table)

        console.print(f"[cyan]Scenarios:[/cyan] {', '.join(manifest.get('scenarios', []))}")
        console.print(f"[cyan]Incidents:[/cyan] {', '.join(manifest.get('incident_ids', []))}")
        console.print(f"[cyan]Audit chain valid:[/cyan] {manifest.get('audit_chain_valid')}")
    except Exception as exc:
        console.print(f"[bold red]World build failed:[/bold red] {exc}")
        raise typer.Exit(1)
    finally:
        session.close()


def _cost_score(cost_class: str) -> float:
    return {"free": 1.0, "low": 0.75, "standard": 0.5, "high": 0.25, "premium": 0.1}.get(
        cost_class, 0.4
    )


def _format_ctx(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n // 1_000}K"
    return str(n)


def _format_price(p: float | None) -> str:
    return f"${p:.4f}" if p is not None else "—"


@app.command()
def models(
    search: str = typer.Option(
        "", "--search", "-s", help="Search display name, id, provider, maker, family"
    ),
    provider: list[str] = typer.Option(
        [], "--provider", "-p", help="Filter by provider (repeatable)"
    ),
    maker: list[str] = typer.Option([], "--maker", "-m", help="Filter by maker (repeatable)"),
    free: bool = typer.Option(False, "--free", help="Show only free models"),
    configured: bool = typer.Option(False, "--configured", help="Show only configured models"),
    available: bool = typer.Option(False, "--available", help="Show only available models"),
    tools: bool = typer.Option(False, "--tools", help="Require tool support"),
    streaming: bool = typer.Option(False, "--streaming", help="Require streaming"),
    reasoning: bool = typer.Option(False, "--reasoning", help="Require reasoning"),
    multimodal: bool = typer.Option(False, "--multimodal", help="Require multimodal"),
    group: str = typer.Option(
        "provider",
        "--group",
        "-g",
        help="Group by provider|maker|family|cost|availability|latency|context|none",
    ),
    sort: str = typer.Option(
        "recommended",
        "--sort",
        "-r",
        help="Sort by recommended|provider|maker|cost|context|latency",
    ),
    profile: str = typer.Option("sentinel", "--profile", help="Profile used for recommendations"),
    top: int = typer.Option(0, "--top", help="Limit to N recommendations (0 = all)"),
):
    """List, search, filter, group, and sort the ANVAYA model catalog."""
    from anvaya.agent.profiles import default_models, get_profile
    from anvaya.llm.providers import select_model_provider_for_profile

    all_models = default_models()

    recommended = None
    try:
        recommended_model, _, _ = select_model_provider_for_profile(profile, all_models)
        recommended = recommended_model
    except Exception:
        recommended = None

    q = search.strip().lower()
    filtered = all_models

    if q:
        filtered = [
            m
            for m in filtered
            if q in m.display_name.lower()
            or q in m.id.lower()
            or q in m.provider.lower()
            or q in (m.maker or "").lower()
            or q in (m.family or "").lower()
            or q in (m.description or "").lower()
            or q in (m.purpose or "").lower()
            or any(q in c.lower() for c in (m.capabilities or []))
        ]

    if provider:
        filtered = [m for m in filtered if m.provider in provider]
    if maker:
        filtered = [m for m in filtered if (m.maker or "") in maker]
    if free:
        filtered = [m for m in filtered if m.cost_class == "free"]
    if configured:
        filtered = [m for m in filtered if m.configured]
    if available:
        filtered = [m for m in filtered if m.availability == "available"]
    if tools:
        filtered = [m for m in filtered if m.supports_tools]
    if streaming:
        filtered = [m for m in filtered if m.supports_streaming]
    if reasoning:
        filtered = [m for m in filtered if m.supports_reasoning]
    if multimodal:
        filtered = [m for m in filtered if m.supports_multimodal]

    if sort == "recommended" or (sort == "recommended" and not top):
        profile_obj = get_profile(profile)
        filtered = sorted(
            filtered, key=lambda m: _recommendation_score(m, profile_obj, recommended), reverse=True
        )
    elif sort == "provider":
        filtered = sorted(filtered, key=lambda m: (m.provider, m.display_name))
    elif sort == "maker":
        filtered = sorted(filtered, key=lambda m: (m.maker or "", m.display_name))
    elif sort == "cost":
        filtered = sorted(filtered, key=lambda m: _cost_score(m.cost_class), reverse=True)
    elif sort == "context":
        filtered = sorted(filtered, key=lambda m: m.context_window, reverse=True)
    elif sort == "latency":
        latency_order = {"instant": 0, "fast": 1, "standard": 2, "slow": 3, "unknown": 9}
        filtered = sorted(
            filtered, key=lambda m: (latency_order.get(m.latency_class, 9), m.display_name)
        )

    if top:
        filtered = filtered[:top]

    if group == "none":
        _print_model_table(filtered, title="ANVAYA Model Catalog")
    else:
        groups: dict[str, list] = {}
        for m in filtered:
            if group == "provider":
                key = m.provider
            elif group == "maker":
                key = m.maker or "Unknown maker"
            elif group == "family":
                key = m.family or "Unknown family"
            elif group == "cost":
                key = m.cost_class or "unknown"
            elif group == "context":
                n = m.context_window
                if not n:
                    key = "Unknown"
                elif n < 32_000:
                    key = "0–32K"
                elif n < 128_000:
                    key = "32K–128K"
                elif n < 500_000:
                    key = "128K–500K"
                elif n < 1_000_000:
                    key = "500K–1M"
                else:
                    key = "1M+"
            else:
                key = getattr(m, group, None) or "unknown"
            groups.setdefault(key, []).append(m)

        for gkey in sorted(
            groups.keys(), key=lambda k: (0 if k in ("anvaya", "agentrouter") else 1, k)
        ):
            _print_model_table(groups[gkey], title=f"{group.upper()}: {gkey}")


def _recommendation_score(m, profile, recommended):
    score = 0.0
    if recommended and m.id == recommended.id:
        score += 100
    if m.availability == "available":
        score += 40
    elif m.availability == "configured":
        score += 20
    if m.configured:
        score += 15
    if m.cost_class == "free":
        score += 10
    if m.profile_fit and profile and profile.id in m.profile_fit:
        fit = m.profile_fit[profile.id]
        if fit is not None:
            score += fit * 30
    if m.recommended_for and profile and profile.id in m.recommended_for:
        score += 15
    if m.supports_tools and m.supports_streaming:
        score += 5
    return score


def _role_fit_str(m) -> str:
    """Render profile-fit scores as S/P/R/A percentages or N/A."""
    if not m.profile_fit:
        return "N/A"
    parts = []
    for k in ("sentinel", "pathfinder", "responder", "auditor"):
        v = m.profile_fit.get(k)
        if v is None:
            parts.append("N/A")
        else:
            parts.append(f"{int(round(v * 100))}")
    return "/".join(parts)


def _print_model_table(models, title: str):
    if not models:
        return
    table = Table(title=title, title_style="bold cyan")
    table.add_column("Model", style="white", no_wrap=True)
    table.add_column("Provider", style="cyan")
    table.add_column("Maker", style="magenta")
    table.add_column("Ctx", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Role fit (S/P/R/A)", justify="right")
    table.add_column("Evidence", justify="center")
    table.add_column("Caps")

    for m in models:
        caps = ", ".join(m.capabilities or [])
        if m.supports_tools:
            caps += ", tools" if caps else "tools"
        if m.supports_streaming:
            caps += ", stream" if caps else "stream"
        if m.supports_reasoning:
            caps += ", reasoning" if caps else "reasoning"
        if m.supports_multimodal:
            caps += ", vision" if caps else "vision"

        status = (
            "[green]●[/green]"
            if m.availability == "available"
            else "[cyan]●[/cyan]"
            if m.availability == "configured"
            else "[red]●[/red]"
            if m.availability == "unavailable"
            else "[yellow]●[/yellow]"
        )
        table.add_row(
            m.display_name,
            m.provider,
            m.maker or "—",
            _format_ctx(m.context_window),
            m.cost_class,
            _format_price(getattr(m.pricing, "input_per_million", None) if m.pricing else None),
            _format_price(getattr(m.pricing, "output_per_million", None) if m.pricing else None),
            status,
            _role_fit_str(m),
            m.evidence_confidence or "Unknown",
            caps,
        )

    console.print(table)


@app.command()
def watch(
    source: str = typer.Option(
        ..., help="Path to a log file to tail, or 'synthetic' for a simulated live feed"
    ),
    interval: float = typer.Option(1.0, help="Poll interval in seconds for file-based sources"),
    max_events: int = typer.Option(0, help="Stop after N events (0 = unlimited)"),
):
    """Watch a real-time log source and score events as they arrive.

    File sources are tailed like `tail -f`. Each line may be JSON or pipe-
    delimited; see `anvaya/cli/watch.py` for the supported field order.

    The 'synthetic' source generates attack-scenario events at a realistic
    pace and is honest about being synthetic.
    """
    from anvaya.cli.watch import run_watch

    run_watch(source=source, interval=interval, max_events=max_events)


@app.command()
def serve():
    """Start the FastAPI server."""
    import uvicorn

    from anvaya.config import settings

    uvicorn.run(
        "anvaya.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )


def main() -> None:
    """Dispatch between the interactive shell and the existing Typer commands."""
    from anvaya.config import settings
    from anvaya.logging import configure_logging

    configure_logging(settings.cli_log_level, human=True)

    if len(sys.argv) == 1:
        from anvaya.cli.main import run_interactive_shell

        raise SystemExit(run_interactive_shell())

    app()


if __name__ == "__main__":
    main()
