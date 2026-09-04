"""Tests for the ANVAYA interactive CLI."""

import os
import tempfile
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console
from sqlmodel import Session, SQLModel, create_engine

os.environ["DATABASE_URL"] = "sqlite://"

from anvaya.cli.artifacts import list_artifact_counts
from anvaya.cli.commands import CommandRegistry, parse_artifact_args, parse_input
from anvaya.cli.files import (
    build_tree,
    extract_at_refs,
    parse_line_range,
    read_file,
    resolve_workspace_path,
    search_text,
)
from anvaya.cli.render import AnvayaRenderer
from anvaya.cli.shell import InteractiveShell
from anvaya.cli.state import CLIState
from anvaya.models.project import Project, ProjectArtifact


@pytest.fixture(scope="module")
def db_engine():
    """Create an in-memory database engine for CLI tests."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Provide a fresh session per test."""
    with Session(db_engine) as session:
        yield session


@pytest.fixture
def workspace():
    """Provide a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def _shell(session, workspace, state=None):
    """Create a testable shell with a captured, uncolored console."""
    console = Console(file=StringIO(), color_system=None)
    state = state or CLIState()
    return InteractiveShell(session=session, console=console, workspace=workspace, state=state)


def test_parse_input_command():
    assert parse_input("/help") == ("help", [])
    assert parse_input("/read foo.py 1 20") == ("read", ["foo.py", "1", "20"])
    assert parse_input("  /search query  ") == ("search", ["query"])


def test_parse_input_natural():
    assert parse_input("find the top issue") == ("", ["find the top issue"])
    assert parse_input("/") == ("", [])


def test_command_registry_lookup():
    registry = CommandRegistry()
    assert registry.get("help").handler == "_do_help"
    assert registry.get("h").handler == "_do_help"
    assert registry.get("unknown") is None


def test_parse_artifact_args():
    assert parse_artifact_args(["generate"]) == ("", "generate", "")
    assert parse_artifact_args(["orbits", "generate"]) == ("orbits", "generate", "")
    assert parse_artifact_args(["regen", "reach"]) == ("reach", "regenerate", "")
    assert parse_artifact_args(["all"]) == ("all", "list", "")


def test_state_persists_without_secrets():
    state = CLIState(
        project_id="PRJ-1",
        model_id="anvaya-local",
        profile_id="sentinel",
    )
    d = state.to_dict()
    assert d["project_id"] == "PRJ-1"
    assert "api_key" not in d
    assert "secret" not in str(d).lower()
    state.add_command("/set-key sk-123")
    assert "/set-key" not in state.recent_commands


def test_resolve_workspace_path(workspace):
    (workspace / "foo.py").write_text("print(1)")
    assert resolve_workspace_path("foo.py", workspace).name == "foo.py"
    assert resolve_workspace_path(str(workspace / "foo.py"), workspace).name == "foo.py"
    with pytest.raises(ValueError):
        resolve_workspace_path("../etc/passwd", workspace)
    with pytest.raises(ValueError):
        resolve_workspace_path("/etc/passwd", workspace)


def test_read_file_with_line_range(workspace):
    (workspace / "sample.py").write_text("\n".join(f"line {i}" for i in range(1, 21)))
    path, start, end = parse_line_range("sample.py:5-8")
    data = read_file(path, workspace, line_start=start, line_end=end)
    assert data["start"] == 5
    assert data["end"] == 8
    assert data["lines"] == ["line 5", "line 6", "line 7", "line 8"]
    assert data["total"] == 20


def test_parse_line_range():
    assert parse_line_range("file.py:1-120") == ("file.py", 1, 120)
    assert parse_line_range("file.py 1 120") == ("file.py", 1, 120)
    assert parse_line_range("file.py:5") == ("file.py", 5, 0)
    assert parse_line_range("file.py") == ("file.py", 1, 0)


def test_build_tree(workspace):
    (workspace / "src").mkdir()
    (workspace / "src" / "main.py").write_text("x = 1")
    (workspace / "src" / ".git").mkdir()
    (workspace / "src" / ".venv").mkdir()
    (workspace / "README.md").write_text("# hi")
    data = build_tree(".", workspace)
    text = "\n".join(data["lines"])
    assert "README.md" in text
    assert "main.py" in text
    assert ".git" not in text
    assert ".venv" not in text


def test_search_text(workspace):
    (workspace / "a.py").write_text("hello world\nfoo bar\nhello again")
    (workspace / "b.py").write_text("goodbye")
    results = search_text("hello", workspace)
    assert len(results) == 2
    assert all(r["file"] == "a.py" for r in results)


def test_extract_at_refs():
    text = "Look at @src/main.py and @README.md for context"
    assert extract_at_refs(text) == ["src/main.py", "README.md"]


def test_renderer_events():
    out = StringIO()
    console = Console(file=out, color_system=None)
    renderer = AnvayaRenderer(console)

    renderer.event({"type": "agent.started", "label": "Start", "payload": {"objective": "test"}})
    renderer.event({"type": "tool.completed", "label": "done", "payload": {"output_summary": "ok"}})
    text = out.getvalue()
    assert "test" in text
    assert "ok" in text


def test_shell_status(db_session, workspace):
    shell = _shell(db_session, workspace)
    assert shell._do_status([]) is True
    output = shell.console.file.getvalue()
    assert "ANVAYA STATUS" in output
    assert "Tools" in output


def test_shell_tools(db_session, workspace):
    shell = _shell(db_session, workspace)
    assert shell._do_tools([]) is True
    assert "search_events" in shell.console.file.getvalue()


def test_shell_help(db_session, workspace):
    shell = _shell(db_session, workspace)
    assert shell._do_help([]) is True
    assert "/read" in shell.console.file.getvalue()


def test_shell_read(db_session, workspace):
    (workspace / "test.py").write_text("print(1)\nprint(2)\nprint(3)")
    shell = _shell(db_session, workspace)
    assert shell._do_read(["test.py"]) is True
    output = shell.console.file.getvalue()
    assert "test.py" in output
    assert "print(1)" in output
    assert shell.state.file_contexts


def test_shell_tree(db_session, workspace):
    (workspace / "dir").mkdir()
    (workspace / "dir" / "a.py").write_text("x=1")
    shell = _shell(db_session, workspace)
    assert shell._do_tree(["dir"]) is True
    assert "a.py" in shell.console.file.getvalue()


def test_shell_search(db_session, workspace):
    (workspace / "code.py").write_text("hello\nworld")
    shell = _shell(db_session, workspace)
    assert shell._do_search(["hello"]) is True
    assert "code.py" in shell.console.file.getvalue()


def test_shell_context(db_session, workspace):
    state = CLIState(project_id="PRJ-1", model_id="anvaya-local", profile_id="sentinel")
    shell = _shell(db_session, workspace, state=state)
    assert shell._do_context([]) is True
    output = shell.console.file.getvalue()
    assert "PRJ-1" in output


def test_shell_refreshes_stale_model_display(db_session, workspace):
    """A stale model_display is re-derived from the catalog on startup."""
    state = CLIState(
        project_id="PRJ-1",
        model_id="nvidia/openai/gpt-oss-20b",
        model_display="GPT Oss 20B",
        model_provider="nvidia",
        profile_id="sentinel",
    )
    shell = _shell(db_session, workspace, state=state)
    assert shell.state.model_display == "GPT OSS 20B"
    toolbar = shell._bottom_toolbar()
    assert "GPT OSS 20B" in toolbar
    assert "GPT Oss 20B" not in toolbar


def test_shell_clear_context(db_session, workspace):
    (workspace / "x.py").write_text("x = 1")
    shell = _shell(db_session, workspace)
    shell._do_read(["x.py"])
    assert shell.state.file_contexts
    assert shell._do_context(["clear"]) is True
    assert not shell.state.file_contexts


def test_artifact_counts(db_session, workspace):
    """Artifact counting must return accurate per-type totals."""
    project = Project(
        project_id="PRJ-CLI-1", organization_id="ORG-1", name="cli test", created_by="test"
    )
    db_session.add(project)
    db_session.commit()

    for i in range(3):
        db_session.add(
            ProjectArtifact(
                project_id="PRJ-CLI-1",
                dataset_id="DS-1",
                generation_id="GEN-1",
                artifact_type="orbits",
                artifact_id=f"ORB-{i}",
            )
        )
    db_session.add(
        ProjectArtifact(
            project_id="PRJ-CLI-1",
            dataset_id="DS-1",
            generation_id="GEN-1",
            artifact_type="reach",
            artifact_id="REACH-1",
        )
    )
    db_session.commit()

    counts = list_artifact_counts(db_session, "PRJ-CLI-1")
    assert counts["orbits"] == 3
    assert counts["reach"] == 1


def test_shell_artifact_list(db_session, workspace):
    project = Project(
        project_id="PRJ-CLI-2", organization_id="ORG-1", name="cli test", created_by="test"
    )
    db_session.add(project)
    db_session.add(
        ProjectArtifact(
            project_id="PRJ-CLI-2",
            dataset_id="DS-1",
            generation_id="GEN-1",
            artifact_type="orbits",
            artifact_id="ORB-9",
        )
    )
    db_session.commit()

    state = CLIState(project_id="PRJ-CLI-2")
    shell = _shell(db_session, workspace, state=state)
    assert shell._run_artifact_command("orbits", "list", "") is True
    assert "ORB-9" in shell.console.file.getvalue()


def test_renderer_artifact_build_events():
    """New render branches must produce user-readable build narration in compact mode."""
    out = StringIO()
    console = Console(file=out, color_system=None)
    renderer = AnvayaRenderer(console)

    events = [
        {
            "type": "generation.started",
            "label": "Build started",
            "payload": {"target": "orbits", "manifest_length": 11},
        },
        {
            "type": "generation.analyzing",
            "label": "Understanding your request",
            "payload": {"target": "orbits"},
        },
        {
            "type": "artifact.world_build_started",
            "label": "Building canonical world model",
            "payload": {},
        },
        {
            "type": "artifact.world_build_completed",
            "label": "World model built",
            "payload": {"entities": 3, "events": 10, "incidents": 2},
        },
        {
            "type": "artifact.thinking",
            "label": "Planning Orbit Foundation",
            "payload": {
                "index": 0,
                "name": "Orbit Foundation",
                "purpose": "Provide the workspace foundation.",
                "building": "Resolving the dataset scope.",
                "live_reason": "Resolving the workspace: 2 incidents across 10 rows",
            },
        },
        {
            "type": "artifact.creating",
            "label": "Creating Orbit Foundation",
            "payload": {"index": 0, "name": "Orbit Foundation"},
        },
        {
            "type": "artifact.created",
            "label": "Orbit Foundation created",
            "payload": {"index": 0, "name": "Orbit Foundation"},
        },
        {
            "type": "element.thinking",
            "label": "Preparing node-1",
            "payload": {
                "display": "node-1",
                "reason": "Preparing node-1 — rank 1; risk 0.85",
            },
        },
        {
            "type": "generation.completed",
            "label": "Orbits is ready",
            "payload": {"target_artifact_type": "orbits", "total_artifacts": 11},
        },
    ]

    for ev in events:
        renderer.event(ev, compact=True)

    text = out.getvalue()
    assert "BUILD Build started" in text
    assert "Understanding your request" in text
    assert "Building canonical world model" in text
    assert "World model built" in text
    assert "01 Orbit Foundation" in text
    assert "Resolving the workspace: 2 incidents across 10 rows" in text
    assert "building..." in text
    assert "· node-1" in text
    assert "rank 1; risk 0.85" in text
    assert "Orbits is ready" in text
    assert "orbits · 11 steps" in text

    for etype in (
        "generation.started",
        "generation.analyzing",
        "artifact.thinking",
        "artifact.creating",
        "artifact.created",
        "element.thinking",
        "generation.completed",
    ):
        assert etype not in text, f"event type {etype} leaked into fallback output"

    assert text.count("node-1") == 1


def test_renderer_build_events_different_payload_shapes():
    """The same branches must work across multiple artifact type payload shapes."""
    out = StringIO()
    console = Console(file=out, color_system=None)
    renderer = AnvayaRenderer(console)

    renderer.event(
        {
            "type": "artifact.thinking",
            "label": "Planning Incident Foundation",
            "payload": {
                "index": 0,
                "name": "Incident Foundation",
                "purpose": "Provide the workspace foundation.",
                "building": "Resolving the dataset.",
                "live_reason": "Resolving the workspace: 5 incidents across 20 rows",
            },
        },
        compact=True,
    )
    renderer.event(
        {
            "type": "element.thinking",
            "label": "Preparing INC-1",
            "payload": {
                "element_id": "INC-1",
                "reason": "Preparing INC-1 — rank 1, risk 0.92",
            },
        },
        compact=True,
    )
    renderer.event(
        {
            "type": "artifact.created",
            "label": "Incident Foundation created",
            "payload": {"index": 0, "name": "Incident Foundation"},
        },
        compact=True,
    )
    renderer.event(
        {
            "type": "generation.completed",
            "label": "Incidents is ready",
            "payload": {"target_artifact_type": "incidents", "total_artifacts": 11},
        },
        compact=True,
    )

    text = out.getvalue()
    assert "01 Incident Foundation" in text
    assert "Resolving the workspace: 5 incidents across 20 rows" in text
    assert "· INC-1" in text
    assert "risk 0.92" in text
    assert "Incident Foundation" in text
    assert "incidents · 11 steps" in text


def test_renderer_non_compact_build_details():
    """Non-compact mode should expose the secondary/transitional events."""
    out = StringIO()
    console = Console(file=out, color_system=None)
    renderer = AnvayaRenderer(console)

    renderer.event(
        {"type": "navigation.started", "label": "Opening orbits workspace", "payload": {}},
        compact=False,
    )
    renderer.event(
        {"type": "element.mounted", "label": "node-1 added", "payload": {"display": "node-1"}},
        compact=False,
    )
    renderer.event(
        {"type": "artifact.completed", "label": "Orbit Foundation complete", "payload": {}},
        compact=False,
    )

    text = out.getvalue()
    assert "Opening orbits workspace" in text
    assert "node-1 mounted" in text
    assert "Orbit Foundation complete" in text
