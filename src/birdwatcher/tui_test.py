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
from textual.widgets import DataTable, Static

from birdwatcher.checks import Check
from birdwatcher.fetch import CourseFetchError
from birdwatcher.findings import Finding, Severity
from birdwatcher.run import CheckResult, RunResult
from birdwatcher.tui import BirdwatcherApp, Checked

REPO = "lcc-cit/CS212-CourseMaterials"
COMMIT = "abcdef1234" + "0" * 30
CHECK = Check(
    id="links", title="Broken section links", description="d", run=lambda c: []
)
FIRST = Finding("links", Severity.ERROR, "docs/A.md", 3, "First problem.")
SECOND = Finding("links", Severity.WARNING, "docs/B.md", 2, "Second problem.")
WHOLE_FILE = Finding("links", Severity.INFO, "docs/C.md", None, "Whole-file problem.")
SCREEN = (140, 40)


def make_run(findings, stale=False):
    results = (CheckResult(CHECK, tuple(findings), 0.1),)
    return RunResult(
        REPO, COMMIT, False, stale, datetime(2026, 11, 10, tzinfo=UTC), results
    )


def make_course(tmp_path):
    """Course files matching FIRST and SECOND, with recognisable lines."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "A.md").write_text("one\ntwo\nthe broken line\nfour\n", encoding="utf-8")
    (docs / "B.md").write_text("alpha\nbeta line\n", encoding="utf-8")
    return tmp_path


def loader(*results):
    """A load function returning each result in turn (the last one repeats)."""
    calls = []

    def load():
        calls.append(None)
        result = results[min(len(calls), len(results)) - 1]
        if isinstance(result, Exception):
            raise result
        return result

    load.calls = calls
    return load


def make_app(load, opened=None, urls=None):
    opened = [] if opened is None else opened
    urls = [] if urls is None else urls
    return BirdwatcherApp(
        load,
        open_in_editor=lambda path, line: opened.append((path, line)),
        open_url=urls.append,
    )


def drive(app, steps):
    """Run the app headless, wait for loading, then run `steps(app, pilot)`."""

    async def main():
        async with app.run_test(size=SCREEN) as pilot:
            await settle(app, pilot)
            await steps(app, pilot)

    asyncio.run(main())


async def settle(app, pilot):
    await app.workers.wait_for_complete()
    await pilot.pause()


def panel_text(app):
    """The detail panel's content as plain text."""
    buffer = io.StringIO()
    Console(file=buffer, width=120, color_system=None).print(
        app.query_one("#detail", Static).content
    )
    return buffer.getvalue()


def table_text(app):
    table = app.query_one(DataTable)
    return [
        " ".join(str(cell) for cell in table.get_row_at(row))
        for row in range(table.row_count)
    ]


def test_lists_every_finding_with_severity_file_and_line(tmp_path):
    app = make_app(loader(Checked(make_course(tmp_path), make_run([FIRST, SECOND]))))

    async def steps(app, pilot):
        rows = table_text(app)
        assert len(rows) == 2
        assert "error" in rows[0].lower() and "docs/A.md" in rows[0] and "3" in rows[0]
        assert "warning" in rows[1].lower() and "docs/B.md" in rows[1]

    drive(app, steps)


def test_subtitle_names_the_repository_commit_and_count(tmp_path):
    app = make_app(loader(Checked(tmp_path, make_run([FIRST, SECOND]))))

    async def steps(app, pilot):
        assert REPO in app.sub_title
        assert COMMIT[:7] in app.sub_title
        assert "2 findings" in app.sub_title

    drive(app, steps)


def test_subtitle_flags_a_copy_that_may_be_out_of_date(tmp_path):
    app = make_app(loader(Checked(tmp_path, make_run([FIRST], stale=True))))

    async def steps(app, pilot):
        assert "out of date" in app.sub_title

    drive(app, steps)


def test_panel_follows_the_highlighted_finding(tmp_path):
    app = make_app(loader(Checked(make_course(tmp_path), make_run([FIRST, SECOND]))))

    async def steps(app, pilot):
        assert FIRST.message in panel_text(app)
        await pilot.press("down")
        text = panel_text(app)
        assert SECOND.message in text and FIRST.message not in text
        assert CHECK.title in text

    drive(app, steps)


def test_panel_shows_the_source_lines_around_the_finding(tmp_path):
    app = make_app(loader(Checked(make_course(tmp_path), make_run([FIRST]))))

    async def steps(app, pilot):
        text = panel_text(app)
        assert "the broken line" in text
        assert "two" in text and "four" in text

    drive(app, steps)


def test_enter_opens_the_finding_in_the_editor(tmp_path):
    root = make_course(tmp_path)
    opened = []
    app = make_app(loader(Checked(root, make_run([FIRST, SECOND]))), opened)

    async def steps(app, pilot):
        await pilot.press("down", "enter")
        await pilot.pause()
        assert opened == [(root / "docs/B.md", 2)]

    drive(app, steps)


def test_o_also_opens_the_finding_in_the_editor(tmp_path):
    root = make_course(tmp_path)
    opened = []
    app = make_app(loader(Checked(root, make_run([FIRST]))), opened)

    async def steps(app, pilot):
        await pilot.press("o")
        await pilot.pause()
        assert opened == [(root / "docs/A.md", 3)]

    drive(app, steps)


def test_whole_file_findings_open_at_line_one(tmp_path):
    opened = []
    app = make_app(loader(Checked(tmp_path, make_run([WHOLE_FILE]))), opened)

    async def steps(app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        assert opened == [(tmp_path / "docs/C.md", 1)]

    drive(app, steps)


def test_first_click_shows_a_finding_and_second_click_opens_it(tmp_path):
    root = make_course(tmp_path)
    opened = []
    app = make_app(loader(Checked(root, make_run([FIRST, SECOND]))), opened)
    second_row = (2, 2)  # below the header row and the first finding

    async def steps(app, pilot):
        await pilot.click(DataTable, offset=second_row)
        await pilot.pause()
        assert opened == []
        assert SECOND.message in panel_text(app)
        await pilot.click(DataTable, offset=second_row)
        await pilot.pause()
        assert opened == [(root / "docs/B.md", 2)]

    drive(app, steps)


def test_g_opens_the_source_on_github(tmp_path):
    urls = []
    run = make_run([FIRST, SECOND])
    app = make_app(loader(Checked(tmp_path, run)), urls=urls)

    async def steps(app, pilot):
        await pilot.press("down", "g")
        await pilot.pause()
        assert urls == [run.source_url(SECOND)]

    drive(app, steps)


def test_r_runs_the_checks_again_and_shows_the_new_results(tmp_path):
    load = loader(
        Checked(tmp_path, make_run([FIRST, SECOND])),
        Checked(tmp_path, make_run([SECOND])),
    )
    app = make_app(load)

    async def steps(app, pilot):
        await pilot.press("r")
        await settle(app, pilot)
        assert len(load.calls) == 2
        rows = table_text(app)
        assert len(rows) == 1 and "docs/B.md" in rows[0]
        assert "1 finding" in app.sub_title
        assert SECOND.message in panel_text(app)

    drive(app, steps)


def test_no_findings_says_every_check_came_back_clean(tmp_path):
    app = make_app(loader(Checked(tmp_path, make_run([]))))

    async def steps(app, pilot):
        assert app.query_one(DataTable).row_count == 0
        assert "No findings" in panel_text(app)

    drive(app, steps)


def test_failed_load_is_shown_in_the_window(tmp_path):
    app = make_app(loader(CourseFetchError("GitHub is unreachable")))

    async def steps(app, pilot):
        assert "GitHub is unreachable" in panel_text(app)

    drive(app, steps)


def test_editor_failure_does_not_close_the_app(tmp_path):
    def broken_editor(path, line):
        raise FileNotFoundError("code")

    app = BirdwatcherApp(
        loader(Checked(tmp_path, make_run([FIRST]))),
        open_in_editor=broken_editor,
        open_url=lambda url: None,
    )

    async def steps(app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        assert app.is_running
        assert FIRST.message in panel_text(app)

    drive(app, steps)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
