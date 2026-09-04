"""Tests for the /train slash command.

These tests exercise the full training pipeline in a clean in-memory SQLite
session: dataset generation, CSV export, Alertness + What-If model training,
and the Sentinel self-correction cycle.  They also verify the command remains
fully functional when no LLM is configured, using deterministic local
narration and engine outputs.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console
from sqlmodel import Session, SQLModel, create_engine, select

import anvaya.models  # noqa: F401  registers all SQLModel tables
from anvaya.cli.shell import InteractiveShell
from anvaya.cli.state import CLIState
from anvaya.config import settings
from anvaya.models.dataset import DatasetVersion
from anvaya.models.enums import SelfCorrectionStatus
from anvaya.models.incident import Incident
from anvaya.models.model_version import ModelVersion


def _in_memory_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _in_memory_shell(
    session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> InteractiveShell:
    """Return an InteractiveShell wired to a capture console and temp dirs."""
    monkeypatch.setattr(settings, "datasets_dir", tmp_path / "datasets")
    monkeypatch.setattr(settings, "artifacts_dir", tmp_path / "artifacts")

    # Ensure no API keys are configured so the test proves local fallback works.
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "lyzr_api_key", "")
    monkeypatch.setattr(settings, "lyzr_base_url", "")

    console = Console(file=io.StringIO())
    return InteractiveShell(session=session, state=CLIState(), console=console)


def test_train_command_completes_without_llm_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _in_memory_session()
    shell = _in_memory_shell(session, monkeypatch, tmp_path)

    result = shell._do_train([])
    output = shell.console.file.getvalue()

    assert result is True
    assert "local fallback" in output.lower()

    # Exactly one self-correction incident was created and reached a terminal state.
    incidents = list(session.exec(select(Incident)).all())
    assert len(incidents) == 1
    assert incidents[0].self_correction_status in (
        SelfCorrectionStatus.CAUGHT,
        SelfCorrectionStatus.STILL_MISSED,
    )

    # Both models trained and persisted real metrics.
    models = list(session.exec(select(ModelVersion)).all())
    assert len(models) >= 2
    for model in models:
        assert model.f1_score > 0.0

    # A CSV was exported with a header and data rows.
    csv_files = list(settings.datasets_dir.glob("*.csv"))
    assert len(csv_files) == 1
    content = csv_files[0].read_text()
    assert "event_id" in content
    assert content.count("\n") > 1


def test_train_command_writes_csv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _in_memory_session()
    shell = _in_memory_shell(session, monkeypatch, tmp_path)

    result = shell._do_train(["42"])
    output = shell.console.file.getvalue()

    assert result is True
    assert "CSV exported" in output

    csv_files = list(settings.datasets_dir.glob("*.csv"))
    assert len(csv_files) == 1
    lines = csv_files[0].read_text().strip().split("\n")
    assert len(lines) > 1
    assert "event_id" in lines[0]

    # The dataset is reproducible from the same seed.
    datasets = list(session.exec(select(DatasetVersion)).all())
    assert len(datasets) == 1
    assert datasets[0].seed == 42


def test_train_command_does_not_duplicate_incidents_on_rerun(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session = _in_memory_session()
    shell = _in_memory_shell(session, monkeypatch, tmp_path)

    assert shell._do_train(["42"]) is True
    # Second invocation with the same seed must reuse the existing dataset
    # and incident rather than create duplicates.
    assert shell._do_train(["42"]) is True

    incidents = list(session.exec(select(Incident)).all())
    assert len(incidents) == 1
    assert incidents[0].self_correction_status in (
        SelfCorrectionStatus.CAUGHT,
        SelfCorrectionStatus.STILL_MISSED,
    )

    datasets = list(session.exec(select(DatasetVersion)).all())
    assert len(datasets) == 1

    csv_files = list(settings.datasets_dir.glob("*.csv"))
    assert len(csv_files) == 1
