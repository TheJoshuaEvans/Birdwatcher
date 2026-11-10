"""
Contract tests for birdwatcher.ui.console.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import io
import sys
from datetime import UTC, datetime
from pathlib import PureWindowsPath

import pytest
from rich.console import Console

from birdwatcher.core.check import Check
from birdwatcher.core.findings import Finding, Severity
from birdwatcher.core.run import CheckFinished, CheckResult, CheckStarted, RunResult
from birdwatcher.ui.console import print_event, print_findings, print_summary
from birdwatcher.ui.system import editor_url

COURSE = PureWindowsPath(r"C:\courses\CS212")  # behaves the same on every OS
CHECK = Check(
    id="links", title="Broken section links", description="d", run=lambda c: []
)
FAILED = Check(id="broken", title="Broken check", description="d", run=lambda c: [])
FINDINGS = (
    Finding("links", Severity.ERROR, "docs/A.md", 3, "First problem."),
    Finding("links", Severity.WARNING, "docs/B.md", 7, "Second problem."),
)


def make_run():
    results = (
        CheckResult(CHECK, FINDINGS, 0.25),
        CheckResult(FAILED, (), 0.01, error="ValueError: boom"),
    )
    return RunResult(COURSE, datetime(2026, 11, 10, tzinfo=UTC), results)


def capture(terminal=False):
    """A console writing to a string; terminal=True keeps link escape codes.

    Rich writes OSC 8 links only when it has a colour system and is not in legacy
    Windows console mode (which it assumes on Windows when writing to a string),
    so terminal mode sets both; plain mode has no colour system, so plain text.
    """
    buffer = io.StringIO()
    color_system = "standard" if terminal else None
    console = Console(
        file=buffer,
        width=160,
        force_terminal=terminal,
        color_system=color_system,
        legacy_windows=False,
    )
    return console, buffer


def test_summary_names_the_course_checks_and_totals():
    console, buffer = capture()
    print_summary(console, make_run())
    text = buffer.getvalue()
    assert str(COURSE) in text
    assert "links" in text and "2" in text
    assert "ValueError: boom" in text
    assert "1 error" in text and "1 warning" in text


def test_findings_list_each_finding_linked_to_the_editor():
    console, buffer = capture(terminal=True)
    run = make_run()
    print_findings(console, run)
    text = buffer.getvalue()
    for finding in FINDINGS:
        assert finding.path in text
        assert finding.message in text
        assert editor_url(run.file_of(finding), finding.line) in text


def test_events_print_progress_and_errors():
    console, buffer = capture()
    print_event(console, CheckStarted(CHECK))
    print_event(console, CheckFinished(CheckResult(CHECK, FINDINGS, 0.25)))
    print_event(
        console, CheckFinished(CheckResult(FAILED, (), 0.01, error="ValueError: boom"))
    )
    text = buffer.getvalue()
    assert "Broken section links" in text
    assert "2 findings" in text
    assert "ValueError: boom" in text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
