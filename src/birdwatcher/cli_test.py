"""
Contract tests for birdwatcher.cli.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import asyncio
import io
import sys

import pytest
from rich.console import Console
from textual.widgets import DataTable

from birdwatcher.checks import ALL_CHECKS
from birdwatcher.cli import EXIT_FAILED, EXIT_OK, main
from birdwatcher.config import Config, save_config
from birdwatcher.tui import BirdwatcherApp

BROKEN_PAGE = "[Jump](#nowhere)\n\n## Somewhere\n"


def make_course(folder):
    (folder / "docs").mkdir(parents=True)
    (folder / "docs" / "Page.md").write_text(BROKEN_PAGE, encoding="utf-8")
    return folder


def run(tmp_path, *args, course=None):
    """Run main with a config naming `course` (none when course is None), a
    captured console and a recorded app launch."""
    config_path = tmp_path / "settings" / "config.json"
    if course is not None:
        save_config(config_path, Config(course_dir=course))
    buffer = io.StringIO()
    apps = []
    status = main(
        list(args),
        config_path=config_path,
        console=Console(file=buffer, width=160, color_system=None),
        run_app=apps.append,
    )
    return status, buffer.getvalue(), apps


def test_no_command_opens_the_app_on_the_saved_course(tmp_path):
    course = make_course(tmp_path / "course")
    status, _, apps = run(tmp_path, course=course)
    assert status == EXIT_OK
    [app] = apps
    assert isinstance(app, BirdwatcherApp)

    async def drive():
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            table = app.screen.query_one(DataTable)
            assert table.row_count == 1
            assert "docs/Page.md" in [str(cell) for cell in table.get_row_at(0)]

    asyncio.run(drive())


def test_check_prints_a_summary_of_the_saved_course(tmp_path):
    course = make_course(tmp_path / "course")
    status, text, apps = run(tmp_path, "check", course=course)
    assert status == EXIT_OK
    assert apps == []
    assert str(course) in text
    assert "1 finding" in text
    assert "#nowhere" not in text  # findings only with --verbose


def test_course_dir_option_overrides_the_saved_course(tmp_path):
    saved = make_course(tmp_path / "saved")
    other = make_course(tmp_path / "other")
    _, text, _ = run(tmp_path, "check", "--course-dir", str(other), course=saved)
    assert str(other) in text


def test_check_without_any_course_explains_how_to_set_one(tmp_path):
    status, text, _ = run(tmp_path, "check")
    assert status == EXIT_FAILED
    assert "--course-dir" in text


def test_check_on_an_unusable_folder_says_why(tmp_path):
    status, text, _ = run(tmp_path, "check", "--course-dir", str(tmp_path / "nowhere"))
    assert status == EXIT_FAILED
    assert "nowhere" in text


def test_check_verbose_prints_progress_and_findings(tmp_path):
    course = make_course(tmp_path / "course")
    _, text, _ = run(tmp_path, "check", "--verbose", course=course)
    assert "#nowhere" in text
    assert ALL_CHECKS[0].title in text


def test_list_checks_needs_no_course(tmp_path):
    status, text, _ = run(tmp_path, "check", "--list-checks")
    assert status == EXIT_OK
    for check in ALL_CHECKS:
        assert check.id in text


def test_unknown_check_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as stopped:
        run(tmp_path, "check", "--check", "no-such-check")
    assert stopped.value.code == EXIT_FAILED


def test_selected_checks_only(tmp_path):
    course = make_course(tmp_path / "course")
    status, text, _ = run(tmp_path, "check", "--check", ALL_CHECKS[0].id, course=course)
    assert status == EXIT_OK
    assert ALL_CHECKS[0].id in text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
