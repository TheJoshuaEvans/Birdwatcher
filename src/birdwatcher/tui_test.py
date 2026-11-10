"""
Contract tests for birdwatcher.tui, driven headless through Textual's test pilot.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import asyncio
import io
import sys
from datetime import UTC, datetime

import pytest
from rich.console import Console
from textual.widgets import Button, DataTable, Input, Static

from birdwatcher.checks import Check
from birdwatcher.config import Config, load_config, save_config
from birdwatcher.findings import Finding, Severity
from birdwatcher.run import CheckResult, RunResult
from birdwatcher.tui import BirdwatcherApp

CHECK = Check(
    id="links", title="Broken section links", description="d", run=lambda c: []
)
FIRST = Finding("links", Severity.ERROR, "docs/A.md", 3, "First problem.")
SECOND = Finding("links", Severity.WARNING, "docs/B.md", 2, "Second problem.")
WHOLE_FILE = Finding("links", Severity.INFO, "docs/C.md", None, "Whole-file problem.")
SCREEN = (140, 40)


def make_course(folder):
    """A usable course folder with files matching FIRST and SECOND."""
    docs = folder / "docs"
    docs.mkdir(parents=True)
    (docs / "A.md").write_text("one\ntwo\nthe broken line\nfour\n", encoding="utf-8")
    (docs / "B.md").write_text("alpha\nbeta line\n", encoding="utf-8")
    return folder


class FakeChecker:
    """Stands in for check_course: returns each findings list in turn (the last
    repeats) and records which folders were checked. An exception is raised."""

    def __init__(self, *outcomes):
        self.outcomes = outcomes or ([],)
        self.folders = []

    def __call__(self, course_dir):
        self.folders.append(course_dir)
        outcome = self.outcomes[min(len(self.folders), len(self.outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        results = (CheckResult(CHECK, tuple(outcome), 0.1),)
        return RunResult(course_dir, datetime(2026, 11, 10, tzinfo=UTC), results)


def make_app(tmp_path, checker, course=None, opened=None):
    """An app whose config names `course` (no config when course is None)."""
    config_path = tmp_path / "settings" / "config.json"
    if course is not None:
        save_config(config_path, Config(course_dir=course))
    opened = [] if opened is None else opened
    app = BirdwatcherApp(
        config_path,
        check=checker,
        open_in_editor=lambda path, line: opened.append((path, line)),
    )
    return app, config_path


def drive(app, steps):
    """Run the app headless, wait for loading, then run `steps(app, pilot)`."""

    async def main():
        async with app.run_test(size=SCREEN) as pilot:
            await settle(app, pilot)
            await steps(app, pilot)

    asyncio.run(main())


async def settle(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


def render_text(renderable):
    buffer = io.StringIO()
    Console(file=buffer, width=120, color_system=None).print(renderable)
    return buffer.getvalue()


def panel_text(app):
    """The detail panel's content as plain text."""
    return render_text(app.screen.query_one("#detail", Static).content)


def setup_error(app):
    return render_text(app.screen.query_one("#setup-error", Static).content)


def on_setup(app):
    return bool(app.screen.query("#course-dir"))


def table_text(app):
    table = app.screen.query_one(DataTable)
    return [
        " ".join(str(cell) for cell in table.get_row_at(row))
        for row in range(table.row_count)
    ]


async def enter_folder(app, pilot, folder, submit="enter"):
    app.screen.query_one("#course-dir", Input).value = str(folder)
    if submit == "enter":
        app.screen.query_one("#course-dir", Input).focus()
        await pilot.press("enter")
    else:
        await pilot.click(Button)
    await settle(app, pilot)


# First run and setup


def test_first_run_opens_setup_without_checking(tmp_path):
    checker = FakeChecker()
    app, _ = make_app(tmp_path, checker)

    async def steps(app, pilot):
        assert on_setup(app)
        assert checker.folders == []

    drive(app, steps)


@pytest.mark.parametrize("submit", ["enter", "button"])
def test_saving_a_course_folder_remembers_it_and_checks_it(tmp_path, submit):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIRST])
    app, config_path = make_app(tmp_path, checker)

    async def steps(app, pilot):
        await enter_folder(app, pilot, course, submit)
        assert not on_setup(app)
        assert load_config(config_path) == Config(course_dir=course)
        assert checker.folders == [course]
        assert len(table_text(app)) == 1

    drive(app, steps)


def test_an_unusable_folder_is_explained_and_not_saved(tmp_path):
    checker = FakeChecker()
    app, config_path = make_app(tmp_path, checker)

    async def steps(app, pilot):
        await enter_folder(app, pilot, tmp_path / "nowhere")
        assert on_setup(app)
        assert "nowhere" in setup_error(app)
        assert load_config(config_path) is None
        assert checker.folders == []

    drive(app, steps)


def test_a_saved_course_opens_straight_to_the_findings(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIRST, SECOND])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        assert not on_setup(app)
        assert checker.folders == [course]

    drive(app, steps)


def test_a_saved_course_that_is_gone_reopens_setup_with_the_reason(tmp_path):
    missing = tmp_path / "moved-away"
    checker = FakeChecker()
    app, _ = make_app(tmp_path, checker, missing)

    async def steps(app, pilot):
        assert on_setup(app)
        assert app.screen.query_one("#course-dir", Input).value == str(missing)
        assert "moved-away" in setup_error(app)
        assert checker.folders == []

    drive(app, steps)


def test_s_opens_setup_filled_in_and_escape_returns_unchanged(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIRST])
    app, config_path = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await pilot.press("s")
        await pilot.pause()
        assert on_setup(app)
        assert app.screen.query_one("#course-dir", Input).value == str(course)
        await pilot.press("escape")
        await settle(app, pilot)
        assert not on_setup(app)
        assert load_config(config_path) == Config(course_dir=course)
        assert checker.folders == [course]

    drive(app, steps)


def test_choosing_another_course_checks_that_one(tmp_path):
    first = make_course(tmp_path / "first")
    second = make_course(tmp_path / "second")
    checker = FakeChecker([FIRST], [SECOND])
    app, config_path = make_app(tmp_path, checker, first)

    async def steps(app, pilot):
        await pilot.press("s")
        await pilot.pause()
        await enter_folder(app, pilot, second)
        assert checker.folders == [first, second]
        assert load_config(config_path) == Config(course_dir=second)
        assert str(second) in app.sub_title
        assert "docs/B.md" in table_text(app)[0]

    drive(app, steps)


# Findings


def test_lists_every_finding_with_severity_file_and_line(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        rows = table_text(app)
        assert len(rows) == 2
        assert "error" in rows[0].lower() and "docs/A.md" in rows[0] and "3" in rows[0]
        assert "warning" in rows[1].lower() and "docs/B.md" in rows[1]

    drive(app, steps)


def test_subtitle_names_the_course_folder_and_count(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        assert str(course) in app.sub_title
        assert "2 findings" in app.sub_title

    drive(app, steps)


def test_panel_follows_the_highlighted_finding(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        assert FIRST.message in panel_text(app)
        await pilot.press("down")
        text = panel_text(app)
        assert SECOND.message in text and FIRST.message not in text
        assert CHECK.title in text

    drive(app, steps)


def test_panel_shows_the_source_lines_around_the_finding(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        text = panel_text(app)
        assert "the broken line" in text
        assert "two" in text and "four" in text

    drive(app, steps)


@pytest.mark.parametrize("key", ["enter", "o"])
def test_enter_or_o_opens_the_finding_in_the_editor(tmp_path, key):
    course = make_course(tmp_path / "course")
    opened = []
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course, opened)

    async def steps(app, pilot):
        await pilot.press("down", key)
        await pilot.pause()
        assert opened == [(course / "docs/B.md", 2)]

    drive(app, steps)


def test_whole_file_findings_open_at_line_one(tmp_path):
    course = make_course(tmp_path / "course")
    opened = []
    app, _ = make_app(tmp_path, FakeChecker([WHOLE_FILE]), course, opened)

    async def steps(app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        assert opened == [(course / "docs/C.md", 1)]

    drive(app, steps)


def test_first_click_shows_a_finding_and_second_click_opens_it(tmp_path):
    course = make_course(tmp_path / "course")
    opened = []
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course, opened)
    second_row = (2, 2)  # below the header row and the first finding

    async def steps(app, pilot):
        await pilot.click(DataTable, offset=second_row)
        await pilot.pause()
        assert opened == []
        assert SECOND.message in panel_text(app)
        await pilot.click(DataTable, offset=second_row)
        await pilot.pause()
        assert opened == [(course / "docs/B.md", 2)]

    drive(app, steps)


def test_r_runs_the_checks_again_and_shows_the_new_results(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIRST, SECOND], [SECOND])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await pilot.press("r")
        await settle(app, pilot)
        assert checker.folders == [course, course]
        rows = table_text(app)
        assert len(rows) == 1 and "docs/B.md" in rows[0]
        assert "1 finding" in app.sub_title
        assert SECOND.message in panel_text(app)

    drive(app, steps)


def test_no_findings_says_every_check_came_back_clean(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([]), course)

    async def steps(app, pilot):
        assert app.screen.query_one(DataTable).row_count == 0
        assert "No findings" in panel_text(app)

    drive(app, steps)


def test_a_failed_check_run_is_shown_in_the_window(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker(OSError("disk on fire")), course)

    async def steps(app, pilot):
        assert "disk on fire" in panel_text(app)

    drive(app, steps)


def test_editor_failure_does_not_close_the_app(tmp_path):
    course = make_course(tmp_path / "course")
    config_path = tmp_path / "config.json"
    save_config(config_path, Config(course_dir=course))

    def broken_editor(path, line):
        raise FileNotFoundError("code")

    app = BirdwatcherApp(
        config_path, check=FakeChecker([FIRST]), open_in_editor=broken_editor
    )

    async def steps(app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        assert app.is_running
        assert FIRST.message in panel_text(app)

    drive(app, steps)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
