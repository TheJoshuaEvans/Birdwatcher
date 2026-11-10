"""
Contract tests for birdwatcher.console.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import io
import sys
from datetime import UTC, datetime

import pytest
from rich.console import Console

from birdwatcher.checks import Check
from birdwatcher.console import print_event, print_findings, print_summary
from birdwatcher.findings import Finding, Severity
from birdwatcher.run import CheckFinished, CheckResult, CheckStarted, RunResult

REPO = "lcc-cit/CS212-CourseMaterials"
COMMIT = "abcdef1234" + "0" * 30
CHECK = Check(
    id="links", title="Broken section links", description="d", run=lambda c: []
)
FAILED = Check(id="broken", title="Broken check", description="d", run=lambda c: [])
FINDINGS = (
    Finding("links", Severity.ERROR, "docs/A.md", 3, "First problem."),
    Finding("links", Severity.WARNING, "docs/B.md", 7, "Second problem."),
)


def make_run(downloaded=False, stale=False):
    results = (
        CheckResult(CHECK, FINDINGS, 0.25),
        CheckResult(FAILED, (), 0.01, error="ValueError: boom"),
    )
    return RunResult(
        REPO, COMMIT, downloaded, stale, datetime(2026, 11, 10, tzinfo=UTC), results
    )


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


def test_summary_names_the_course_commit_checks_and_totals():
    console, buffer = capture()
    print_summary(console, make_run())
    text = buffer.getvalue()
    assert REPO in text
    assert COMMIT[:7] in text
    assert "links" in text and "2" in text
    assert "ValueError: boom" in text
    assert "1 error" in text and "1 warning" in text


@pytest.mark.parametrize(
    ("downloaded", "stale", "expected"),
    [
        (True, False, "downloaded"),
        (False, False, "cached"),
        (False, True, "out of date"),
    ],
    ids=["downloaded", "cached", "stale"],
)
def test_summary_says_where_the_files_came_from(downloaded, stale, expected):
    console, buffer = capture()
    print_summary(console, make_run(downloaded, stale))
    assert expected in buffer.getvalue()


def test_summary_links_the_commit_on_github():
    console, buffer = capture(terminal=True)
    print_summary(console, make_run())
    assert "\x1b]8;" in buffer.getvalue()
    assert f"https://github.com/{REPO}/commit/{COMMIT}" in buffer.getvalue()


def test_findings_list_each_finding_linked_to_its_source():
    console, buffer = capture(terminal=True)
    run = make_run()
    print_findings(console, run)
    text = buffer.getvalue()
    for finding in FINDINGS:
        assert finding.path in text
        assert finding.message in text
        assert run.source_url(finding) in text


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
