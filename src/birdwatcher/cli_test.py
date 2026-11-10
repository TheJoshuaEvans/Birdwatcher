"""
Contract tests for birdwatcher.cli. GitHub is replaced by an in-memory fake.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import asyncio
import io
import sys
import zipfile

import pytest
from rich.console import Console
from textual.widgets import DataTable

from birdwatcher.checks import ALL_CHECKS
from birdwatcher.cli import EXIT_FAILED, EXIT_OK, main
from birdwatcher.tui import BirdwatcherApp

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
    """Run main with a fake GitHub, a captured console and a recorded app launch."""
    buffer = io.StringIO()
    apps = []
    status = main(
        ["--cache-dir", str(tmp_path / "cache"), *args],
        fetch=fake_fetch(online),
        console=Console(file=buffer, width=160, color_system=None),
        run_app=apps.append,
    )
    return status, buffer.getvalue(), apps


def test_no_command_opens_the_app_on_the_course(tmp_path):
    status, _, apps = run(tmp_path)
    assert status == EXIT_OK
    [app] = apps
    assert isinstance(app, BirdwatcherApp)

    async def drive():
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.query_one(DataTable)
            assert table.row_count == 1
            assert "docs/Page.md" in [str(cell) for cell in table.get_row_at(0)]

    asyncio.run(drive())


def test_check_prints_a_summary_without_opening_the_app(tmp_path):
    status, text, apps = run(tmp_path, "check")
    assert status == EXIT_OK
    assert apps == []
    assert "lcc-cit/CS212-CourseMaterials" in text
    assert "1 finding" in text
    assert "#nowhere" not in text  # findings only with --verbose


def test_check_verbose_prints_progress_and_findings(tmp_path):
    _, text, _ = run(tmp_path, "check", "--verbose")
    assert "#nowhere" in text
    assert ALL_CHECKS[0].title in text


def test_list_checks_prints_them_without_fetching(tmp_path):
    status, text, _ = run(tmp_path, "check", "--list-checks", online=False)
    assert status == EXIT_OK
    for check in ALL_CHECKS:
        assert check.id in text
    assert "offline" not in text


def test_unknown_check_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as stopped:
        run(tmp_path, "check", "--check", "no-such-check")
    assert stopped.value.code == EXIT_FAILED


def test_selected_checks_only(tmp_path):
    status, text, _ = run(tmp_path, "check", "--check", ALL_CHECKS[0].id)
    assert status == EXIT_OK
    assert ALL_CHECKS[0].id in text


def test_check_fails_with_a_message_when_the_course_is_unreachable(tmp_path):
    status, text, _ = run(tmp_path, "check", online=False)
    assert status == EXIT_FAILED
    assert "offline" in text


def test_shared_options_also_work_after_the_command(tmp_path):
    cache = tmp_path / "after"
    status = main(
        ["check", "--cache-dir", str(cache)],
        fetch=fake_fetch(),
        console=Console(file=io.StringIO(), color_system=None),
        run_app=lambda app: None,
    )
    assert status == EXIT_OK
    assert cache.is_dir()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
