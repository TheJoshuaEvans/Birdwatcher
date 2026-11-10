"""
Birdwatcher: watches course materials for consistency problems and blind spots.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys


def main() -> None:
    """Run Birdwatcher from the command line (`uv run birdwatcher`)."""
    from birdwatcher.cli import main as cli_main

    sys.exit(cli_main())
