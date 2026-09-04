"""Entry points for the ANVAYA interactive CLI."""

from __future__ import annotations

import sys

from anvaya.config import settings
from anvaya.logging import configure_logging


def run_interactive_shell() -> int:
    """Run the ANVAYA interactive agent terminal."""
    from anvaya.cli.shell import InteractiveShell

    return InteractiveShell().run()


def main() -> None:
    """Dispatch between the interactive shell and existing Typer commands.

    Running ``anvaya`` with no arguments starts the shell. Any subcommand is
    forwarded to the existing Typer application. CLI logs are rendered in a
    human-readable format and default to error level to keep the output clean.
    """
    configure_logging(settings.cli_log_level, human=True)

    if len(sys.argv) == 1:
        run_interactive_shell()
        return

    from anvaya.cli import app

    app()
