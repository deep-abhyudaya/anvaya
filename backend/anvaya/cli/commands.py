"""Slash command registry for the ANVAYA interactive CLI."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SlashCommand:
    """Definition of a single slash command."""

    name: str
    description: str
    handler: str
    aliases: list[str] = field(default_factory=list)
    args: str = ""
    examples: list[str] = field(default_factory=list)


class CommandRegistry:
    """Reusable slash command registry."""

    def __init__(self) -> None:
        self._commands: dict[str, SlashCommand] = {}
        self._aliases: dict[str, str] = {}
        for command in _COMMANDS:
            self.register(command)

    def register(self, command: SlashCommand) -> None:
        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name

    def get(self, name: str) -> SlashCommand | None:
        name = name.lstrip("/")
        if name in self._commands:
            return self._commands[name]
        if name in self._aliases:
            return self._commands[self._aliases[name]]
        return None

    def list_all(self) -> list[SlashCommand]:
        return list(self._commands.values())

    def names(self) -> list[str]:
        return [f"/{c.name}" for c in self._commands.values()]

    def complete(self, prefix: str) -> list[str]:
        """Return command names/aliases matching ``prefix`` (without leading slash)."""
        prefix = prefix.lstrip("/")
        hits: list[str] = []
        for name, cmd in self._commands.items():
            if name.startswith(prefix):
                hits.append(f"/{name}")
            for alias in cmd.aliases:
                if alias.startswith(prefix):
                    hits.append(f"/{alias}")
        return sorted(set(hits))


def parse_input(text: str) -> tuple[str, list[str]]:
    """Parse a slash command into name and arguments.

    Natural-language input is returned as ("", [text]).
    """
    text = text.strip()
    if not text.startswith("/"):
        return "", [text]
    parts = text[1:].split()
    if not parts:
        return "", []
    return parts[0], parts[1:]


def parse_artifact_args(args: list[str], default_type: str = "") -> tuple[str, str, str]:
    """Parse artifact subcommand syntax: ``[action] [artifact_id/dataset_id]``.

    Returns (artifact_type, action, artifact_id_or_dataset).
    """
    actions = {"generate", "regenerate", "delete", "list", "inspect", "regen"}
    action = "list"
    target = ""
    artifact_type = default_type

    for arg in args:
        if arg in actions or arg == "regen":
            action = "regenerate" if arg == "regen" else arg
        elif arg.startswith("GEN-") or arg.startswith("ORB-") or arg.startswith("ART-"):
            target = arg
        elif arg in {
            "all",
            "incidents",
            "arbor",
            "impacts",
            "reach",
            "replay",
            "ecosystem",
            "arena",
            "orbits",
            "segments",
            "trophy_wall",
            "ledger",
        }:
            artifact_type = arg
        else:
            target = arg

    return artifact_type, action, target


_COMMANDS: list[SlashCommand] = [
    SlashCommand("help", "Show available slash commands", "_do_help", ["h"], "[command]"),
    SlashCommand("model", "Select or filter the active model", "_do_model", ["m"], "[filter]"),
    SlashCommand("models", "List available models", "_do_models"),
    SlashCommand("provider", "Show provider status", "_do_provider"),
    SlashCommand("project", "Select an active project", "_do_project", ["p"]),
    SlashCommand("profile", "Select an agent profile", "_do_profile"),
    SlashCommand("context", "Show or clear context", "_do_context", ["ctx"], "[clear]"),
    SlashCommand("read", "Read a file into context", "_do_read", ["r"], "<path> [start] [end]"),
    SlashCommand("tree", "Show a directory tree", "_do_tree", ["t"], "[path]"),
    SlashCommand(
        "search",
        "Search code/text in the workspace",
        "_do_search",
        ["s"],
        '"query" [scope]',
    ),
    SlashCommand(
        "investigate",
        "Run an agentic investigation",
        "_do_investigate",
        ["i"],
        "<objective>",
    ),
    SlashCommand("mission", "Show current mission", "_do_mission"),
    SlashCommand("incident", "Select an incident context", "_do_incident"),
    SlashCommand("artifact", "Artifact command center", "_do_artifact", ["art"], "[type] [action]"),
    SlashCommand(
        "orbit",
        "Orbit artifact operations",
        "_do_orbit",
        [],
        "[generate|inspect|regenerate|delete] [id]",
    ),
    SlashCommand(
        "ecosystem",
        "Threat ecosystem operations",
        "_do_ecosystem",
        [],
        "[generate|inspect|regenerate|delete] [id]",
    ),
    SlashCommand(
        "replay",
        "Replay artifact operations",
        "_do_replay",
        [],
        "[generate|inspect|regenerate|delete] [id]",
    ),
    SlashCommand(
        "reach",
        "Reach artifact operations",
        "_do_reach",
        [],
        "[generate|inspect|regenerate|delete] [id]",
    ),
    SlashCommand(
        "segments",
        "Segment artifact operations",
        "_do_segments",
        [],
        "[generate|inspect|regenerate|delete] [id]",
    ),
    SlashCommand(
        "arena",
        "Arena artifact operations",
        "_do_arena",
        [],
        "[generate|inspect|regenerate|delete] [id]",
    ),
    SlashCommand(
        "arbor",
        "Arbor artifact operations",
        "_do_arbor",
        [],
        "[generate|inspect|regenerate|delete] [id]",
    ),
    SlashCommand(
        "impact",
        "Impact artifact operations",
        "_do_impact",
        [],
        "[generate|inspect|regenerate|delete] [id]",
    ),
    SlashCommand(
        "trophy",
        "Trophy wall operations",
        "_do_trophy",
        [],
        "[generate|inspect|regenerate|delete] [id]",
    ),
    SlashCommand(
        "ledger",
        "Ledger artifact operations",
        "_do_ledger",
        [],
        "[generate|inspect|regenerate|delete] [id]",
    ),
    SlashCommand("inspect", "Inspect an artifact or directory", "_do_inspect"),
    SlashCommand("regenerate", "Regenerate an artifact", "_do_regenerate", ["regen"]),
    SlashCommand("delete", "Delete an artifact", "_do_delete"),
    SlashCommand("history", "List agent executions", "_do_history", ["hist"], "[limit]"),
    SlashCommand("open", "Load an existing execution", "_do_open"),
    SlashCommand("resume", "Resume an execution", "_do_resume"),
    SlashCommand("new", "Start a new conversation", "_do_new"),
    SlashCommand("tools", "List registered agent tools", "_do_tools"),
    SlashCommand("blackboard", "Show active blackboard", "_do_blackboard", ["bb"]),
    SlashCommand("hypotheses", "Show active hypotheses", "_do_hypotheses", ["hyps"]),
    SlashCommand("hypothesis", "Show one hypothesis", "_do_hypothesis", ["hyp"]),
    SlashCommand("memory", "Show working memory", "_do_memory", ["mem"]),
    SlashCommand("chat", "Switch to chat mode", "_do_chat"),
    SlashCommand("ask", "Ask the model without tools", "_do_ask"),
    SlashCommand("clear", "Clear the terminal", "_do_clear"),
    SlashCommand("debug", "Toggle debug mode", "_do_debug", args="[on|off]"),
    SlashCommand("status", "Show CLI status", "_do_status"),
    SlashCommand("shell", "Run a local shell command", "_do_shell", args="<command>"),
    SlashCommand(
        "train",
        "Agent-orchestrated training: generate/load dataset, train models, Sentinel cycle",
        "_do_train",
        args="[mode] [seed|file.csv]",
    ),
    SlashCommand("quit", "Exit the interactive shell", "_do_quit", ["q", "exit"]),
]
