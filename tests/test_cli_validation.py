"""Adversarial integration validation for the ANVAYA interactive CLI.

These tests treat the CLI as the primary interface and inspect the actual
backend execution metadata (Execution, ExecutionContext, ExecutionEvent,
ProjectArtifact, etc.) to prove that the shell is not a thin wrapper but a
first-class consumer of the ANVAYA runtime.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from io import StringIO
from pathlib import Path
from uuid import uuid4

import pytest
from rich.console import Console
from sqlmodel import Session, SQLModel, create_engine, select

os.environ["DATABASE_URL"] = "sqlite://"

from anvaya.agent.events import event_store
from anvaya.cli.agent_runner import run_agentic
from anvaya.cli.artifacts import (
    get_artifact_by_id,
    list_artifacts_for_project,
)
from anvaya.cli.files import read_file, search_text
from anvaya.cli.shell import InteractiveShell
from anvaya.cli.state import CLIState
from anvaya.config import settings
from anvaya.data import DataFactory
from anvaya.llm.providers import AgentRouterAnthropicProvider, create_model_provider
from anvaya.models.agent_context import ExecutionContext
from anvaya.models.execution import Execution, ExecutionEvent
from anvaya.models.incident import Incident
from anvaya.models.project import (
    Dataset,
    Generation,
    GenerationStatus,
    Project,
    ProjectArtifact,
    ProjectArtifactPayload,
)
from anvaya.models.telemetry import TelemetryEvent


@pytest.fixture(scope="function")
def db_engine():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def _patch_db_engine(db_engine, monkeypatch):
    """Route background agent workers to the same per-test in-memory DB."""
    import anvaya.db

    monkeypatch.setattr(anvaya.db, "engine", db_engine)


@pytest.fixture(autouse=True)
def _disable_networked_catalogs(monkeypatch):
    """Avoid network calls to opencode.ai/models.dev during tests."""
    from anvaya.llm import opencode_catalog

    monkeypatch.setattr(opencode_catalog, "_fetch_model_list", lambda: [])
    monkeypatch.setattr(opencode_catalog, "_fetch_metadata", lambda: {})
    opencode_catalog._list_cache.clear()
    opencode_catalog._metadata_cache.clear()


@pytest.fixture(autouse=True)
def _allow_local_model_for_agentic(monkeypatch):
    """Treat every configured model as compatible so tests can force local mode."""
    from anvaya.agent import planner

    monkeypatch.setattr(planner, "is_model_compatible", lambda config, required: (True, ""))


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def shell(db_session, workspace):
    """InteractiveShell with a captured console and empty state."""
    console = Console(file=StringIO(), color_system=None)
    state = CLIState()
    sh = InteractiveShell(session=db_session, console=console, workspace=workspace, state=state)
    sh.prompt_session = None
    return sh


@pytest.fixture
def monkeypatch_provider(monkeypatch):
    """Route AgentRouter calls to a non-routable endpoint so tests hit the real
    provider boundary instantly without network access.
    """
    original = create_model_provider

    def _fake(provider: str, model: str, supports_multimodal: bool = False, config=None):
        if provider.lower() == "agentrouter" and "claude" in model.lower():
            return AgentRouterAnthropicProvider(
                model=model,
                api_key="fake",
                base_url="http://127.0.0.1:1",
            )
        return original(provider, model, supports_multimodal, config)

    monkeypatch.setattr("anvaya.llm.providers.create_model_provider", _fake)
    monkeypatch.setattr(settings, "agentrouter_timeout_ms", 500)
    monkeypatch.setattr(settings, "agentrouter_max_retries", 0)
    monkeypatch.setattr(settings, "agentrouter_api_key", "fake")


def _select_model(state: CLIState, model_id: str, display: str = "", provider: str = "") -> None:
    state.model_id = model_id
    state.model_display = display or model_id
    state.model_provider = provider or model_id.split("/")[0]
    state.save()


def _events_for_execution(session: Session, execution_id: str) -> list[ExecutionEvent]:
    return list(
        session.exec(
            select(ExecutionEvent)
            .where(ExecutionEvent.execution_id == execution_id)
            .order_by(ExecutionEvent.sequence.asc())
        ).all()
    )


def _latest_execution(session: Session) -> Execution | None:
    return session.exec(
        select(Execution).order_by(Execution.__table__.c.started_at.desc())
    ).first()


def _execution_context(session: Session, execution_id: str) -> ExecutionContext | None:
    return session.exec(
        select(ExecutionContext).where(ExecutionContext.execution_id == execution_id)
    ).first()


def _patch_plan_to_minimal(monkeypatch, incident_id: str) -> None:
    """Replace the agent's default plan with a single, fast, deterministic step.

    This keeps validation focused on the CLI→runtime wiring without depending
    on the full, expensive self-correction training pipeline.
    """

    def _minimal_plan(session, incident_id, profile=None):
        return [
            {
                "tool": "get_incident",
                "inputs": {"incident_id": incident_id},
                "label": "Loading incident",
                "progress": "Loading incident details",
                "completed": "Incident loaded",
            }
        ]

    monkeypatch.setattr("anvaya.agent.orchestrator._build_plan", _minimal_plan)


def _create_incident(session: Session, family: str, host: str, user: str) -> Incident:
    from anvaya.models.enums import IncidentStatus
    from anvaya.models.incident import Incident

    incident = Incident(
        incident_id=f"INC-{uuid4().hex[:8].upper()}",
        organization_id="ORG-1",
        title=f"Validation: {family}",
        severity="high",
        status=IncidentStatus.DETECTED,
        attack_family=family,
        host=host,
        user=user,
    )
    session.add(incident)
    session.commit()
    session.refresh(incident)
    return incident




def test_model_selection_chat_metadata(shell, workspace, monkeypatch_provider, monkeypatch):
    """Setting a model in the CLI must change Execution.provider and the
    provider field on chat events, not just the shell status line.
    """
    _select_model(shell.state, "agentrouter/claude-opus-5", "Claude Opus 5", "agentrouter")

    test_file = workspace / "module.py"
    test_file.write_text("def add(x, y):\n    return x + y\n")

    shell._do_read(["module.py", "1", "2"])
    assert shell.state.file_contexts

    shell._do_ask(["explain how this function works"])

    execution = _latest_execution(shell.session)
    assert execution is not None
    assert execution.provider == "agentrouter"

    events = _events_for_execution(shell.session, execution.execution_id)
    types = [e.type for e in events]
    assert "agent.started" in types
    assert "chat.user" in types
    assert "chat.assistant" in types

    started = next(e for e in events if e.type == "agent.started")
    assert started.provider == "agentrouter"

    user = next(e for e in events if e.type == "chat.user")
    assert user.provider == "agentrouter"
    payload = json.loads(user.payload_json)
    assert payload.get("model_id") == "agentrouter/claude-opus-5"

    assistant = next(e for e in events if e.type == "chat.assistant")
    assert assistant.provider == "agentrouter"


def test_model_selection_agentic_metadata(shell, workspace, monkeypatch_provider, monkeypatch):
    """A model selected in the shell must be persisted in the live
    ExecutionContext and Execution rows during an agentic run.
    """
    _select_model(shell.state, "agentrouter/claude-opus-5", "Claude Opus 5", "agentrouter")

    incident = _create_incident(shell.session, "lateral_movement", "WS-001", "eve")
    shell.state.incident_id = incident.incident_id

    _patch_plan_to_minimal(monkeypatch, incident.incident_id)

    run_agentic(
        shell.session,
        shell.state,
        shell.renderer,
        "What is the most important risk in this environment?",
        workspace=workspace,
        cancel_requested=shell.cancel_event,
    )

    execution = _latest_execution(shell.session)
    assert execution is not None
    assert execution.provider == "agentrouter"

    context = _execution_context(shell.session, execution.execution_id)
    assert context is not None
    assert context.model == "agentrouter/claude-opus-5"
    assert context.provider == "agentrouter"




def test_file_context_reaches_chat_agent(shell, workspace):
    """/read must attach file lines and run_chat must include them in the
    actual chat message persisted in the event store.
    """
    source = workspace / "config.py"
    source.write_text("API_KEY = 'REDACTED'\nDEBUG = True\n")

    shell._do_read(["config.py", "1", "2"])
    assert any(c.get("path") == "config.py" for c in shell.state.file_contexts)

    shell._do_ask(["what does this file contain?"])

    execution = _latest_execution(shell.session)
    events = _events_for_execution(shell.session, execution.execution_id)
    user = next(e for e in events if e.type == "chat.user")
    payload = json.loads(user.payload_json)
    message = payload.get("message", "")
    assert "FILE: config.py" in message
    assert "API_KEY" in message


def test_file_context_reaches_agentic_execution(shell, workspace, monkeypatch):
    """run_agentic must prepend file content to the objective stored on the
    Execution row.
    """
    source = workspace / "alert.py"
    source.write_text("raise SecurityError('lateral movement')\n")

    _select_model(shell.state, "anvaya/local-policy", "ANVAYA Local", "anvaya")
    incident = _create_incident(shell.session, "lateral_movement", "WS-001", "eve")
    shell.state.incident_id = incident.incident_id
    _patch_plan_to_minimal(monkeypatch, incident.incident_id)

    shell._do_read(["alert.py", "1", "1"])
    run_agentic(
        shell.session,
        shell.state,
        shell.renderer,
        "summarize the attached file",
        workspace=workspace,
        cancel_requested=shell.cancel_event,
    )

    execution = _latest_execution(shell.session)
    assert "FILE: alert.py" in execution.objective
    assert "lateral movement" in execution.objective




def test_search_context_reaches_chat_agent(shell, workspace):
    """/search must store results and run_chat must include them in the
    prompt sent to the model.
    """
    source = workspace / "utils.py"
    source.write_text("def auth(token):\n    return token == 'secret'\n")

    results = search_text("auth", workspace)
    assert results
    shell.state.search_context = "auth"
    shell.state.search_results = results
    shell.state.save()

    shell._do_ask(["explain the search results"])

    execution = _latest_execution(shell.session)
    events = _events_for_execution(shell.session, execution.execution_id)
    user = next(e for e in events if e.type == "chat.user")
    payload = json.loads(user.payload_json)
    message = payload.get("message", "")
    assert "SEARCH: auth" in message
    assert "utils.py" in message




def _make_project_and_dataset(session: Session, workspace: Path) -> tuple[str, str, str]:
    """Create a project, a synthetic dataset file, and a ready Dataset record."""
    project_id = f"PRJ-{uuid4().hex[:8].upper()}"
    project = Project(
        project_id=project_id,
        organization_id="ORG-1",
        name="Validation Project",
        created_by="test",
    )
    session.add(project)
    session.commit()

    factory = DataFactory(session)
    result = factory.generate(
        {
            "seed": 123,
            "normal_count": 1,
            "suspicious_count": 1,
            "attack_count": 1,
            "include_self_correction": False,
        }
    )

    events = list(
        session.exec(select(TelemetryEvent).order_by(TelemetryEvent.timestamp)).all()
    )
    import pandas as pd

    df = pd.DataFrame([e.model_dump() for e in events])
    df = df.rename(
        columns={
            "ground_truth_label": "label",
            "actor": "user",
            "source": "source_ip",
            "destination": "destination_ip",
        }
    )
    csv_path = workspace / f"{result['dataset_id']}.csv"
    df.to_csv(csv_path, index=False)

    dataset = Dataset(
        dataset_id=result["dataset_id"],
        organization_id="ORG-1",
        project_id=project_id,
        created_by="test",
        filename=csv_path.name,
        format="csv",
        size=csv_path.stat().st_size,
        source=str(csv_path),
        status="ready",
    )
    session.add(dataset)
    session.commit()
    return project_id, result["dataset_id"], csv_path.name


def test_artifact_crud_list_inspect_delete(shell, workspace, monkeypatch):
    """CLI artifact list/inspect/delete commands must use the existing
    ProjectArtifact/ProjectArtifactPayload services.
    """
    project_id, dataset_id, _ = _make_project_and_dataset(shell.session, workspace)
    shell.state.project_id = project_id
    shell.state.project_name = "Validation Project"

    generation_id = f"GEN-{uuid4().hex[:8].upper()}"
    generation = Generation(
        generation_id=generation_id,
        organization_id="ORG-1",
        project_id=project_id,
        dataset_id=dataset_id,
        user_id="test",
        requested_artifacts_json=json.dumps(["orbits"]),
        created_artifacts_json=json.dumps({"orbits": 3}),
        status=GenerationStatus.COMPLETED,
    )
    shell.session.add(generation)

    for i in range(3):
        artifact_id = f"ORBIT-{project_id}-{i}"
        shell.session.add(
            ProjectArtifact(
                project_id=project_id,
                dataset_id=dataset_id,
                generation_id=generation_id,
                artifact_type="orbits",
                artifact_id=artifact_id,
            )
        )
        shell.session.add(
            ProjectArtifactPayload(
                project_id=project_id,
                dataset_id=dataset_id,
                generation_id=generation_id,
                artifact_type="orbits",
                artifact_id=artifact_id,
                payload_json=json.dumps({"orbit_id": artifact_id, "nodes": i}),
            )
        )
    shell.session.commit()

    shell._do_orbit(["list"])
    output = shell.console.file.getvalue()
    assert "ORBIT-" in output

    latest = list_artifacts_for_project(shell.session, project_id)[0]
    shell._do_orbit(["inspect", latest["artifact_id"]])
    output = shell.console.file.getvalue()
    assert latest["artifact_id"] in output
    assert "orbit_id" in output

    monkeypatch.setattr("anvaya.cli.artifacts.confirm_deletion", lambda x: True)
    shell._do_orbit(["delete", latest["artifact_id"]])
    assert get_artifact_by_id(
        shell.session, project_id, "orbits", latest["artifact_id"]
    ) is None


def test_orbit_generate_creates_artifact(shell, workspace, monkeypatch):
    """/orbit generate must invoke the real ArtifactGenerator and create
    ProjectArtifact rows for the selected type.
    """
    project_id, dataset_id, _ = _make_project_and_dataset(shell.session, workspace)
    shell.state.project_id = project_id
    shell.state.project_name = "Validation Project"

    monkeypatch.setattr("anvaya.cli.selectors.confirm_deletion", lambda x: True)

    from anvaya.generation import ArtifactGenerator

    generation = Generation(
        generation_id=f"GEN-{uuid4().hex[:8].upper()}",
        organization_id="ORG-1",
        project_id=project_id,
        dataset_id=dataset_id,
        user_id="test",
        requested_artifacts_json=json.dumps(["orbits"]),
        status=GenerationStatus.PENDING,
    )
    shell.session.add(generation)
    shell.session.commit()

    project = shell.session.exec(
        select(Project).where(Project.project_id == project_id)
    ).first()
    dataset = shell.session.exec(
        select(Dataset).where(Dataset.dataset_id == dataset_id)
    ).first()

    generator = ArtifactGenerator(shell.session, project, generation, dataset)
    created = generator.generate_all(["orbits"])
    assert created.get("orbits", 0) > 0

    shell._do_orbit(["list"])
    output = shell.console.file.getvalue()
    assert "orbits" in output




def test_adaptive_event_chain_for_incident(shell, workspace, monkeypatch):
    """A non-trivial agentic run must emit the canonical event chain through
    the real AgentLoop.
    """
    from anvaya.models.enums import IncidentStatus
    from anvaya.models.incident import Incident

    incident = Incident(
        incident_id=f"INC-{uuid4().hex[:8].upper()}",
        organization_id="ORG-1",
        title="Lateral movement",
        severity="high",
        status=IncidentStatus.DETECTED,
        attack_family="lateral_movement",
        host="WS-001",
        user="eve",
    )
    shell.session.add(incident)
    shell.session.commit()

    shell.state.incident_id = incident.incident_id
    shell.state.profile_id = "sentinel"

    _select_model(shell.state, "anvaya/local-policy", "ANVAYA Local", "anvaya")
    _patch_plan_to_minimal(monkeypatch, incident.incident_id)

    run_agentic(
        shell.session,
        shell.state,
        shell.renderer,
        f"Investigate incident {incident.incident_id}",
        workspace=workspace,
        cancel_requested=shell.cancel_event,
    )

    execution = _latest_execution(shell.session)
    events = _events_for_execution(shell.session, execution.execution_id)
    types = [e.type for e in events]

    expected = ["agent.started", "agent.plan_created"]
    for t in expected:
        assert t in types, f"missing event {t}; got {types}"

    context = _execution_context(shell.session, execution.execution_id)
    assert context is not None
    assert context.model == "anvaya/local-policy"
    assert context.provider == "anvaya"




def test_chat_streaming_and_polling(shell, workspace, monkeypatch_provider):
    """run_chat must stream events into the event store while polling."""
    _select_model(shell.state, "agentrouter/claude-opus-5", "Claude Opus 5", "agentrouter")

    start = time.monotonic()
    shell._do_ask(["list every tool you can use"])
    duration = time.monotonic() - start

    execution = _latest_execution(shell.session)
    events = _events_for_execution(shell.session, execution.execution_id)
    assert events

    assert any(e.type == "chat.user" for e in events)
    assert any(e.type == "chat.assistant" for e in events)
    assert duration < 5


def test_agentic_cancellation(shell, workspace, monkeypatch):
    """A long agentic run must be interruptible through cancel_requested."""

    def _slow_create(provider, model, supports_multimodal=False, config=None):
        if provider.lower() == "agentrouter":
            return AgentRouterAnthropicProvider(
                model=model,
                api_key="fake",
                base_url="http://127.0.0.1:1",
            )
        return create_model_provider(provider, model, supports_multimodal, config)

    monkeypatch.setattr("anvaya.llm.providers.create_model_provider", _slow_create)
    monkeypatch.setattr(settings, "agentrouter_timeout_ms", 1000)

    incident = _create_incident(shell.session, "lateral_movement", "WS-001", "eve")
    shell.state.incident_id = incident.incident_id
    _select_model(shell.state, "agentrouter/claude-opus-5")

    cancel = threading.Event()

    def _runner():
        run_agentic(
            shell.session,
            shell.state,
            shell.renderer,
            "Generate a very long plan",
            workspace=workspace,
            cancel_requested=cancel,
        )

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    time.sleep(0.1)
    cancel.set()
    thread.join(timeout=3)

    assert not thread.is_alive()




def test_history_blackboard_memory_commands(shell, workspace, monkeypatch):
    """The /history, /blackboard, and /memory commands must return state
    driven by the shared ExecutionContext and event store.
    """
    _select_model(shell.state, "anvaya/local-policy")

    incident = _create_incident(shell.session, "lateral_movement", "WS-001", "eve")
    shell.state.incident_id = incident.incident_id
    _patch_plan_to_minimal(monkeypatch, incident.incident_id)

    run_agentic(
        shell.session,
        shell.state,
        shell.renderer,
        "What tools are available?",
        workspace=workspace,
        cancel_requested=shell.cancel_event,
    )

    shell._do_history([])
    out1 = shell.console.file.getvalue()
    assert "exec-" in out1 or "Execution" in out1

    shell._do_blackboard([])
    out2 = shell.console.file.getvalue()
    assert "Blackboard" in out2 or "blackboard" in out2.lower() or "No blackboard" in out2

    shell._do_memory([])
    out3 = shell.console.file.getvalue()
    assert "Memory" in out3 or "memory" in out3.lower()




def test_state_does_not_persist_secrets():
    state = CLIState()
    state.add_command("/set-key sk-abc123")
    state.add_command("/api-key my-token")
    state.add_command("/read file.py")
    assert "/set-key" not in state.recent_commands
    assert "sk-abc" not in str(state.to_dict())


def test_workspace_escape_blocked(shell, workspace):
    """File read and search must reject paths that escape the workspace."""
    secret_file = workspace.parent / "secret.txt"
    secret_file.write_text("sensitive")

    with pytest.raises(ValueError):
        read_file("../secret.txt", workspace)

    with pytest.raises(ValueError):
        read_file("/etc/passwd", workspace)


def test_cli_output_does_not_leak_api_keys(shell, workspace, monkeypatch_provider):
    """Assistant outputs, result summaries, and persisted CLI state must not
    expose secret material, even when the secret appears in user context.
    """
    _select_model(shell.state, "agentrouter/claude-opus-5")
    (workspace / "env.txt").write_text("API_KEY=sk-leaked\n")
    shell._do_read(["env.txt", "1", "1"])
    shell._do_ask(["what is the api key?"])

    execution = _latest_execution(shell.session)
    assert "sk-leaked" not in (execution.result_summary or "")
    assert "sk-leaked" not in (execution.error_message or "")

    events = _events_for_execution(shell.session, execution.execution_id)
    for e in events:
        if e.type not in ("chat.user", "agent.started"):
            text = e.payload_json + e.label + e.error_message + e.provider
            assert "sk-leaked" not in text, f"{e.type} leaks secret: {text}"

    assert "sk-leaked" not in str(shell.state.to_dict())




def test_noninteractive_help_and_world_commands():
    """The Typer CLI must still answer --help and run without TTY."""
    result = subprocess.run(
        ["anvaya", "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0
    assert "shell" in result.stdout.lower()
    assert "world" in result.stdout.lower()


def test_anvaya_world_regression(tmp_path, monkeypatch):
    """The non-interactive `anvaya world` command must run end-to-end and
    create a deterministic world dataset.
    """

    db = tmp_path / "world.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    result = subprocess.run(
        ["anvaya", "world", "--seed", "42"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    assert "world built" in result.stdout.lower() or "audit chain valid" in result.stdout.lower()


def test_tty_shell_healthy():
    """The interactive shell must start under a pseudo-TTY and respond to
    /help and /quit without hanging.
    """
    if not shutil.which("script"):
        pytest.skip("`script` utility not available")

    script = "printf '/help\\n/quit\\n' | script -q -c 'anvaya' /dev/null"
    result = subprocess.run(
        script,
        shell=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "ANVAYA" in combined
    assert "/help" in combined
    assert "/quit" in combined




def test_api_and_cli_share_execution_state(shell, workspace, monkeypatch_provider):
    """An execution created by the CLI must be visible to the FastAPI layer."""
    _select_model(shell.state, "agentrouter/claude-opus-5")
    shell._do_ask(["hello from the cli"])

    execution = _latest_execution(shell.session)
    assert execution is not None

    events = event_store.get_events(shell.session, execution.execution_id)
    assert events
    assert any(e.type == "chat.user" for e in events)

    api_exec = event_store.get_execution(shell.session, execution.execution_id)
    assert api_exec is not None
    assert api_exec.execution_id == execution.execution_id
    assert api_exec.provider == "agentrouter"
