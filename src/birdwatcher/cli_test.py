"""
Contract tests for birdwatcher.cli. GitHub is replaced by an in-memory fake.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import io
import sys
import zipfile

import pytest
from rich.console import Console

from birdwatcher.checks import ALL_CHECKS
from birdwatcher.cli import EXIT_FAILED, EXIT_OK, main

SHA = "c" * 40
BROKEN_PAGE = "[Jump](#nowhere)\n\n## Somewhere\n"


def course_archive():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"CS212-CourseMaterials-{SHA}/docs/Page.md", BROKEN_PAGE)
    return buffer.getvalue()


def fake_fetch(online=True):
    def fetch(url, headers):
        if not online:
            raise OSError("offline")
        return SHA.encode() if "api.github.com" in url else course_archive()

    return fetch


def run(tmp_path, *args, online=True):
    """Run main with a fake GitHub, a captured console and a recorded browser."""
    buffer = io.StringIO()
    opened = []
    status = main(
        [
            "--cache-dir",
            str(tmp_path / "cache"),
            "--out",
            str(tmp_path / "report"),
            *args,
        ],
        fetch=fake_fetch(online),
        console=Console(file=buffer, width=160, color_system=None),
        open_browser=opened.append,
    )
    return status, buffer.getvalue(), opened


def test_run_writes_the_report_and_prints_a_summary(tmp_path):
    status, text, opened = run(tmp_path)
    assert status == EXIT_OK
    index = tmp_path / "report" / "index.html"
    assert index.is_file()
    assert "#nowhere" in index.read_text(encoding="utf-8")
    assert "index.html" in text
    assert "#nowhere" not in text  # findings only with --verbose
    assert opened == []


def test_verbose_prints_progress_and_findings(tmp_path):
    _, text, _ = run(tmp_path, "--verbose")
    assert "#nowhere" in text
    assert ALL_CHECKS[0].title in text


def test_open_starts_at_the_first_finding(tmp_path):
    _, _, opened = run(tmp_path, "--open")
    [url] = opened
    assert url.startswith("file:")
    assert "/go/" in url and url.endswith(".html")


def test_list_checks_prints_them_without_fetching(tmp_path):
    status, text, _ = run(tmp_path, "--list-checks", online=False)
    assert status == EXIT_OK
    for check in ALL_CHECKS:
        assert check.id in text
    assert not (tmp_path / "report").exists()


def test_unknown_check_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as stopped:
        run(tmp_path, "--check", "no-such-check")
    assert stopped.value.code == EXIT_FAILED


def test_selected_checks_only(tmp_path):
    status, _, _ = run(tmp_path, "--check", ALL_CHECKS[0].id)
    assert status == EXIT_OK


def test_unreachable_course_fails_with_a_message(tmp_path):
    status, text, _ = run(tmp_path, online=False)
    assert status == EXIT_FAILED
    assert "offline" in text
    assert not (tmp_path / "report").exists()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
