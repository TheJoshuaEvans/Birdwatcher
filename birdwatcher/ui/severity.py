"""
How severities look in every view: a word (never colour alone) and a style.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from birdwatcher.core.findings import Severity

SEVERITY_STYLES = {
    Severity.ERROR: ("ERROR", "bold red"),
    Severity.WARNING: ("WARNING", "bold yellow"),
    Severity.INFO: ("INFO", "bold cyan"),
}
"""Severity -> (label, Rich style) for console output and the app."""
