"""
Contract tests for birdwatcher.ui.tui.app, driven headless through Textual's test pilot.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import asyncio
import io
import sys
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from rich.console import Console
from rich.style import Style
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    OptionList,
    RadioButton,
    Select,
    Static,
)

from birdwatcher.core.check import Check
from birdwatcher.core.config import Config, load_config, save_config
from birdwatcher.core.findings import Destination, Finding, Fix, Severity
from birdwatcher.core.fix_log import FIX_LOG_FILE, load_fixed
from birdwatcher.core.ignores import IGNORE_FILE, load_ignores
from birdwatcher.core.run import CheckResult, RunResult
from birdwatcher.ui.system import Editor
from birdwatcher.ui.tui.app import BirdwatcherApp
from birdwatcher.ui.tui.divider import Divider
from birdwatcher.ui.tui.fix_all import FixAllDialog
from birdwatcher.ui.tui.tree import FindingsTree

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
    repeats) and records which folders were checked, and whether each run
    asked for fresh answers from the web. An exception is raised."""

    def __init__(self, *outcomes):
        self.outcomes = outcomes or ([],)
        self.folders = []
        self.fresh = []

    def __call__(self, course_dir, on_event=None, should_stop=None, fresh=False):
        self.folders.append(course_dir)
        self.fresh.append(fresh)
        outcome = self.outcomes[min(len(self.folders), len(self.outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        results = (CheckResult(CHECK, tuple(outcome), 0.1),)
        return RunResult(course_dir, datetime(2026, 11, 10, tzinfo=UTC), results)


class FakeChooser:
    """Stands in for the folder picker: records where it started and returns
    `outcome` (a folder, or None for cancel); an exception is raised."""

    def __init__(self, outcome=None):
        self.outcome = outcome
        self.starts = []

    def __call__(self, start):
        self.starts.append(start)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def fake_editors(opened, in_typora=None, typora_found=True):
    """Editors that record what they open: VS Code into `opened`, Typora into
    `in_typora`, the default app into neither."""
    in_typora = [] if in_typora is None else in_typora
    return {
        "vscode": Editor(
            "vscode", "VS Code", True, True, lambda p, n: opened.append((p, n))
        ),
        "typora": Editor(
            "typora",
            "Typora",
            False,
            typora_found,
            lambda p, n: in_typora.append((p, n)),
        ),
        "default": Editor(
            "default", "The file's default app", False, True, lambda p, n: None
        ),
    }


def make_app(
    tmp_path,
    checker,
    course=None,
    opened=None,
    chooser=None,
    urls=None,
    shown=None,
    editors=None,
    dark=True,
    severities=frozenset(Severity),
):
    """An app whose config names `course` (no config when course is None);
    `dark` is what the system's light or dark mode reports; `severities` are
    the ones the list shows (all, unless a test is about filtering)."""
    config_path = tmp_path / "settings" / "config.json"
    if course is not None:
        # As the app saves it: the course is also its only recent course.
        save_config(
            config_path,
            Config(course_dir=course, recent=(course,), shown_severities=severities),
        )
    opened = [] if opened is None else opened
    urls = [] if urls is None else urls
    shown = [] if shown is None else shown
    app = BirdwatcherApp(
        config_path,
        check=checker,
        editors=editors or fake_editors(opened),
        choose_folder=chooser or FakeChooser(),
        open_url=urls.append,
        show_folder=shown.append,
        prefers_dark=lambda: dark,
    )
    return app, config_path


def drive(app, steps, size=None):
    """Run the app headless (at `size`, default SCREEN), wait for loading, then
    run `steps(app, pilot)`."""

    async def main():
        async with app.run_test(size=size or SCREEN) as pilot:
            await settle(app, pilot)
            await steps(app, pilot)

    asyncio.run(main())


async def settle(app, pilot):
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


def render_text(renderable, width=120):
    buffer = io.StringIO()
    Console(file=buffer, width=width, color_system=None).print(renderable)
    return buffer.getvalue()


def panel_text(app):
    """The detail panel's visible content (message, source excerpt, fix, a
    branch's list of findings) as plain text."""
    parts = [app.screen.query_one("#detail", Static).content]
    for selector in ("#excerpt", "#fix-summary", "#branch-list"):
        widget = app.screen.query_one(selector, Static)
        if widget.display:
            parts.append(widget.content)
    return "".join(render_text(part) for part in parts)


def setup_error(app):
    return render_text(app.screen.query_one("#setup-error", Static).content)


def on_setup(app):
    return bool(app.screen.query("#course-dir"))


def leaves(app):
    """The tree's finding rows (leaf nodes) that are showing (not inside a
    folded branch), in display order."""
    found = []

    def walk(node):
        for child in node.children:
            if child.children or child.allow_expand:
                if child.is_expanded:
                    walk(child)
            else:
                found.append(child)

    walk(app.screen.query_one(FindingsTree).root)
    return found


def finding_rows(app):
    """Each finding row as 'branch › branch › row' text, in display order."""

    def path_text(node):
        parts = []
        while node is not None and not node.is_root:
            parts.append(str(node.label))
            node = node.parent
        return " › ".join(reversed(parts))

    return [path_text(leaf) for leaf in leaves(app)]


def branches(app):
    """The tree's top-level branch labels."""
    return [
        str(node.label) for node in app.screen.query_one(FindingsTree).root.children
    ]


async def enter_folder(app, pilot, folder, submit="enter"):
    app.screen.query_one("#course-dir", Input).value = str(folder)
    if submit == "enter":
        app.screen.query_one("#course-dir", Input).focus()
        await pilot.press("enter")
    else:
        await pilot.click("#save")
    await settle(app, pilot)


def typed_path(app):
    return app.screen.query_one("#course-dir", Input).value


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
        assert load_config(config_path).course_dir == course
        assert checker.folders == [course]
        assert len(finding_rows(app)) == 1

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


@pytest.mark.parametrize("how", ["click", "ctrl+o"])
def test_browsing_to_a_course_folder_saves_and_checks_it(tmp_path, how):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIRST])
    app, config_path = make_app(tmp_path, checker, chooser=FakeChooser(course))

    async def steps(app, pilot):
        if how == "click":
            await pilot.click("#browse")
        else:
            await pilot.press("ctrl+o")
        await settle(app, pilot)
        assert not on_setup(app)
        assert load_config(config_path).course_dir == course
        assert checker.folders == [course]

    drive(app, steps)


def test_browsing_starts_at_the_typed_folder(tmp_path):
    typed = tmp_path / "somewhere"
    chooser = FakeChooser(None)
    app, _ = make_app(tmp_path, FakeChecker(), chooser=chooser)

    async def steps(app, pilot):
        app.screen.query_one("#course-dir", Input).value = str(typed)
        await pilot.click("#browse")
        await pilot.pause()
        assert chooser.starts == [typed]

    drive(app, steps)


def test_browsing_with_nothing_typed_starts_anywhere(tmp_path):
    chooser = FakeChooser(None)
    app, _ = make_app(tmp_path, FakeChecker(), chooser=chooser)

    async def steps(app, pilot):
        await pilot.click("#browse")
        await pilot.pause()
        assert chooser.starts == [None]

    drive(app, steps)


def test_a_cancelled_browse_changes_nothing(tmp_path):
    checker = FakeChecker()
    app, config_path = make_app(tmp_path, checker, chooser=FakeChooser(None))

    async def steps(app, pilot):
        app.screen.query_one("#course-dir", Input).value = "half typed"
        await pilot.click("#browse")
        await settle(app, pilot)
        assert on_setup(app)
        assert typed_path(app) == "half typed"
        assert setup_error(app).strip() == ""
        assert load_config(config_path) is None
        assert checker.folders == []

    drive(app, steps)


def test_browsing_to_an_unusable_folder_fills_it_in_and_explains(tmp_path):
    checker = FakeChecker()
    app, config_path = make_app(tmp_path, checker, chooser=FakeChooser(tmp_path))

    async def steps(app, pilot):
        await pilot.click("#browse")
        await settle(app, pilot)
        assert on_setup(app)
        assert typed_path(app) == str(tmp_path)
        assert "docs" in setup_error(app)
        assert load_config(config_path) is None

    drive(app, steps)


def test_no_folder_picker_is_explained_on_the_page(tmp_path):
    chooser = FakeChooser(OSError("no desktop session"))
    app, _ = make_app(tmp_path, FakeChecker(), chooser=chooser)

    async def steps(app, pilot):
        await pilot.click("#browse")
        await pilot.pause()
        assert on_setup(app)
        assert "no desktop session" in setup_error(app)

    drive(app, steps)


def test_first_run_has_no_recent_courses_to_offer(tmp_path):
    app, _ = make_app(tmp_path, FakeChecker())

    async def steps(app, pilot):
        assert not is_visible(app, "#recent")

    drive(app, steps)


def test_picking_a_recent_course_switches_to_it(tmp_path):
    first = make_course(tmp_path / "first")
    second = make_course(tmp_path / "second")
    checker = FakeChecker([FIRST], [SECOND])
    app, config_path = make_app(tmp_path, checker)
    save_config(config_path, Config(course_dir=first, recent=(first, second)))

    async def steps(app, pilot):
        await press(app, pilot, "s")
        recent = app.screen.query_one("#recent", OptionList)
        assert recent.option_count == 2
        recent.focus()
        recent.highlighted = 1
        await press(app, pilot, "enter")
        assert checker.folders == [first, second]
        config = load_config(config_path)
        assert config.course_dir == second
        assert config.recent == (second, first)

    drive(app, steps)


def test_a_recent_course_that_is_gone_is_explained(tmp_path):
    first = make_course(tmp_path / "first")
    gone = tmp_path / "gone"
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]))
    save_config(config_path, Config(course_dir=first, recent=(first, gone)))

    async def steps(app, pilot):
        await press(app, pilot, "s")
        recent = app.screen.query_one("#recent", OptionList)
        recent.focus()
        recent.highlighted = 1
        await press(app, pilot, "enter")
        assert on_setup(app)
        assert "gone" in setup_error(app)

    drive(app, steps)


def test_saving_a_new_folder_adds_it_to_the_recent_courses(tmp_path):
    first = make_course(tmp_path / "first")
    second = make_course(tmp_path / "second")
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]), first)

    async def steps(app, pilot):
        await press(app, pilot, "s")
        await enter_folder(app, pilot, second)
        assert load_config(config_path).recent == (second, first)

    drive(app, steps)


def test_choosing_typora_opens_files_in_typora(tmp_path):
    course = make_course(tmp_path / "course")
    opened, in_typora = [], []
    editors = fake_editors(opened, in_typora)
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]), course, editors=editors)

    async def steps(app, pilot):
        await press(app, pilot, "s")
        await pilot.click("#editor-typora")
        await pilot.click("#save")
        await settle(app, pilot)
        assert load_config(config_path).editor == "typora"
        await press(app, pilot, "o")
        assert in_typora == [(course / "docs/A.md", 3)]
        assert opened == []

    drive(app, steps)


def test_the_saved_editor_is_selected_on_the_setup_page(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]))
    save_config(config_path, Config(course_dir=course, editor="typora"))

    async def steps(app, pilot):
        await press(app, pilot, "s")
        assert app.screen.query_one("#editor-typora", RadioButton).value
        assert not app.screen.query_one("#editor-vscode", RadioButton).value

    drive(app, steps)


def test_editors_that_were_not_found_cannot_be_chosen(tmp_path):
    course = make_course(tmp_path / "course")
    editors = fake_editors([], typora_found=False)
    app, _ = make_app(tmp_path, FakeChecker([FIRST]), course, editors=editors)

    async def steps(app, pilot):
        await press(app, pilot, "s")
        assert app.screen.query_one("#editor-typora", RadioButton).disabled
        assert not app.screen.query_one("#editor-vscode", RadioButton).disabled

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
        assert load_config(config_path).course_dir == course
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
        assert load_config(config_path).course_dir == second
        assert str(second) in app.sub_title
        assert "docs/B.md" in finding_rows(app)[0]

    drive(app, steps)


# Findings


def test_lists_every_finding_with_severity_file_and_line(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        rows = finding_rows(app)
        assert len(rows) == 2
        assert "error" in rows[0].lower() and "docs/A.md" in rows[0] and "3" in rows[0]
        assert "warning" in rows[1].lower() and "docs/B.md" in rows[1]

    drive(app, steps)


def test_a_row_shows_severity_then_line_then_message(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, WHOLE_FILE]), course)

    async def steps(app, pilot):
        labels = [str(leaf.label).split() for leaf in leaves(app)]
        assert labels == [
            ["ERROR", "3", "First", "problem."],
            ["INFO", "Whole-file", "problem."],
        ]

    drive(app, steps)


def test_findings_are_grouped_by_check_then_file_with_counts(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        assert [b.split() for b in branches(app)] == [
            ["Broken", "section", "links", "2"]
        ]
        words = " ".join(finding_rows(app)[0].split())
        assert words.startswith("Broken section links 2 › docs/A.md 1 ›")

    drive(app, steps)


@pytest.mark.parametrize("how", ["tab", "g"])
def test_the_grouping_tabs_and_g_switch_the_grouping(tmp_path, how):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        if how == "tab":
            await pilot.click("#by-folder")
        else:
            await press(app, pilot, "g")
        await settle(app, pilot)
        assert [b.split()[0] for b in branches(app)] == ["docs"]
        assert "A.md" in finding_rows(app)[0]
        if how == "g":
            await press(app, pilot, "g")
            assert branches(app)[0].startswith("Broken section links")

    drive(app, steps)


def test_there_is_no_severity_grouping_any_more(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        assert not app.screen.query("#by-severity")

    drive(app, steps)


def chip(app, severity):
    return app.screen.query_one(f"#show-{severity}", Checkbox)


def test_severity_chips_count_open_findings_and_filter_the_list(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND, WHOLE_FILE]), course)

    async def steps(app, pilot):
        labels = [str(chip(app, s).label) for s in ("error", "warning", "info")]
        assert labels == ["ERROR 1", "WARNING 1", "INFO 1"]
        assert len(finding_rows(app)) == 3
        await pilot.click("#show-info")
        await settle(app, pilot)
        assert len(finding_rows(app)) == 2
        assert not any("C.md" in row for row in finding_rows(app))
        assert str(chip(app, "info").label) == "INFO 1"
        assert "2 of 3 findings" in app.sub_title

    drive(app, steps)


@pytest.mark.parametrize(
    ("key", "hidden"), [("1", "A.md"), ("2", "B.md"), ("3", "C.md")]
)
def test_keys_1_2_3_toggle_the_severity_chips(tmp_path, key, hidden):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND, WHOLE_FILE]), course)

    async def steps(app, pilot):
        await press(app, pilot, key)
        assert not any(hidden in row for row in finding_rows(app))
        assert len(finding_rows(app)) == 2
        await press(app, pilot, key)
        assert len(finding_rows(app)) == 3

    drive(app, steps)


def test_the_shown_severities_are_remembered(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(
        tmp_path, FakeChecker([FIRST, SECOND, WHOLE_FILE]), course
    )

    async def steps(app, pilot):
        await press(app, pilot, "2")
        await press(app, pilot, "3")

    drive(app, steps)
    assert load_config(config_path).shown_severities == {Severity.ERROR}


def test_the_list_opens_with_the_saved_severities(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(
        tmp_path,
        FakeChecker([FIRST, SECOND, WHOLE_FILE]),
        course,
        severities=frozenset({Severity.WARNING}),
    )

    async def steps(app, pilot):
        assert [chip(app, s).value for s in ("error", "warning", "info")] == [
            False,
            True,
            False,
        ]
        [row] = finding_rows(app)
        assert "B.md" in row
        assert "1 of 3 findings" in app.sub_title

    drive(app, steps)


def search_box(app):
    return app.screen.query_one("#find", Input)


def test_the_find_row_is_always_there_and_says_how_to_use_it(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        assert search_box(app).display
        assert "/" in str(search_box(app).placeholder)

    drive(app, steps)


def test_slash_searches_as_you_type_without_triggering_keys(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIRST, SECOND])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await press(app, pilot, "slash")
        assert app.focused is search_box(app)
        await press(app, pilot, *"second pro")  # holds r and p, which are keys
        assert [row.split()[-2:] for row in finding_rows(app)] == [
            ["Second", "problem."]
        ]
        assert "1 of 2 findings" in app.sub_title
        assert app.focused is search_box(app)
        assert len(checker.folders) == 1  # r did not re-run the checks

    drive(app, steps)


@pytest.mark.parametrize(
    ("text", "files"),
    [
        ("b.md", ["B.md"]),
        ("FIRST", ["A.md"]),
        ("broken SECTION", ["A.md", "B.md"]),  # the check's title
        ("links", ["A.md", "B.md"]),  # the check's id
        ("nothing like it", []),
    ],
    ids=["path", "message", "check-title", "check-id", "no-match"],
)
def test_search_matches_path_message_and_check_ignoring_case(tmp_path, text, files):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        search_box(app).value = text
        await settle(app, pilot)
        shown = [f for f in ("A.md", "B.md") if any(f in r for r in finding_rows(app))]
        assert shown == files

    drive(app, steps)


def test_enter_keeps_the_search_and_escape_clears_it(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        await press(app, pilot, "slash", *"b.md", "enter")
        assert isinstance(app.focused, FindingsTree)
        assert len(finding_rows(app)) == 1
        await press(app, pilot, "slash", "escape")
        assert search_box(app).value == ""
        assert isinstance(app.focused, FindingsTree)
        assert len(finding_rows(app)) == 2

    drive(app, steps)


def cursor_label(app):
    node = app.screen.query_one(FindingsTree).cursor_node
    return "" if node is None else str(node.label)


def visible_lines(app):
    return app.screen.query_one(FindingsTree).last_line + 1


@pytest.mark.parametrize("expand_key", ["plus", "equals_sign"])
def test_minus_and_plus_fold_and_unfold_one_level_at_a_time(tmp_path, expand_key):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        # Broken section links › docs/A.md, docs/B.md › one row each
        await press(app, pilot, "n")  # onto SECOND, in docs/B.md
        assert visible_lines(app) == 5
        await press(app, pilot, "minus")  # the files fold
        assert (visible_lines(app), leaves(app)) == (3, [])
        assert cursor_label(app).startswith("docs/B.md")
        await press(app, pilot, "minus")  # the check folds
        assert visible_lines(app) == 1
        assert cursor_label(app).startswith("Broken section links")
        await press(app, pilot, "minus")  # nothing left to fold
        assert visible_lines(app) == 1
        await press(app, pilot, expand_key)
        assert (visible_lines(app), leaves(app)) == (3, [])
        await press(app, pilot, expand_key)
        assert visible_lines(app) == 5
        await press(app, pilot, expand_key)  # nothing left to unfold
        assert visible_lines(app) == 5

    drive(app, steps)


def test_plus_unfolds_the_shallowest_folded_level_first(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        tree = app.screen.query_one(FindingsTree)
        [check_branch] = tree.root.children
        check_branch.children[0].collapse()  # docs/A.md, by hand
        await settle(app, pilot)
        assert visible_lines(app) == 4
        await press(app, pilot, "plus")
        assert visible_lines(app) == 5

    drive(app, steps)


def test_folded_branches_stay_folded_when_the_list_is_rebuilt(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        tree = app.screen.query_one(FindingsTree)
        [check_branch] = tree.root.children
        file_a = check_branch.children[0]
        file_a.collapse()
        await settle(app, pilot)
        assert len(leaves(app)) == 1
        await press(app, pilot, "r")
        assert len(leaves(app)) == 1
        assert SECOND.message in render_text(leaves(app)[0].label)

        await press(app, pilot, "minus")
        await press(app, pilot, "r")
        assert leaves(app) == []

    drive(app, steps)


def test_n_and_p_move_between_findings_skipping_branches(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        assert FIRST.message in panel_text(app)
        await press(app, pilot, "n")
        assert SECOND.message in panel_text(app)
        await press(app, pilot, "n")
        assert SECOND.message in panel_text(app)
        await press(app, pilot, "p")
        assert FIRST.message in panel_text(app)

    drive(app, steps)


def test_the_cursor_stays_on_its_finding_when_the_grouping_changes(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        await press(app, pilot, "n")
        assert SECOND.message in panel_text(app)
        await press(app, pilot, "g")
        assert SECOND.message in panel_text(app)

    drive(app, steps)


def test_the_fixed_chip_hides_and_shows_fixed_findings(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIXABLE], []), course)

    async def steps(app, pilot):
        await press(app, pilot, "f")
        chip = app.screen.query_one("#show-fixed", Checkbox)
        assert "FIXED 1" in str(chip.label) and chip.value
        await pilot.click("#show-fixed")
        await settle(app, pilot)
        assert finding_rows(app) == []
        await pilot.click("#show-fixed")
        await settle(app, pilot)
        assert len(finding_rows(app)) == 1

    drive(app, steps)


@pytest.mark.parametrize("how", ["chip", "h"])
def test_the_ignored_chip_and_h_show_ignored_findings(tmp_path, how):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([WARN]), course)

    async def steps(app, pilot):
        await ignore(app, pilot)
        chip = app.screen.query_one("#show-ignored", Checkbox)
        assert "IGNORED 1" in str(chip.label) and not chip.value
        if how == "chip":
            await pilot.click("#show-ignored")
        else:
            await press(app, pilot, "h")
        await settle(app, pilot)
        assert chip.value
        assert "IGNORED" in finding_rows(app)[0]

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
        await pilot.press("n")
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


def test_long_source_lines_scroll_sideways_instead_of_wrapping(tmp_path):
    course = make_course(tmp_path / "course")
    long_line = "x" * 300
    (course / "docs" / "A.md").write_text(
        f"one\ntwo\n{long_line}\nfour\n", encoding="utf-8"
    )
    app, _ = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        excerpt = app.screen.query_one("#excerpt", Static)
        view = app.screen.query_one("#excerpt-scroll")
        assert excerpt.size.width > view.size.width
        assert long_line in render_text(excerpt.content, width=400)

    drive(app, steps)


def test_the_message_still_wraps_to_the_panel(tmp_path):
    course = make_course(tmp_path / "course")
    wordy = Finding("links", Severity.ERROR, "docs/A.md", 3, "word " * 100)
    app, _ = make_app(tmp_path, FakeChecker([wordy]), course)

    async def steps(app, pilot):
        message = app.screen.query_one("#detail", Static)
        assert message.size.width <= app.screen.query_one("#detail-scroll").size.width

    drive(app, steps)


@pytest.mark.parametrize("key", ["enter", "o"])
def test_enter_or_o_opens_the_finding_in_the_editor(tmp_path, key):
    course = make_course(tmp_path / "course")
    opened = []
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course, opened)

    async def steps(app, pilot):
        await pilot.press("n", key)
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


@pytest.mark.parametrize("key", ["enter", "o"])
def test_a_finding_about_a_folder_opens_it_in_the_file_browser(tmp_path, key):
    course = make_course(tmp_path / "course")
    (course / "docs" / "Lab02-Old").mkdir()
    folder_finding = Finding("labs", Severity.INFO, "docs/Lab02-Old", None, "Shared.")
    opened, shown = [], []
    app, _ = make_app(
        tmp_path, FakeChecker([folder_finding]), course, opened, shown=shown
    )

    async def steps(app, pilot):
        assert folder_finding.message in panel_text(app)
        await press(app, pilot, key)
        assert shown == [course / "docs/Lab02-Old"]
        assert opened == []

    drive(app, steps)


def test_first_click_shows_a_finding_and_second_click_opens_it(tmp_path):
    course = make_course(tmp_path / "course")
    opened = []
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course, opened)

    async def steps(app, pilot):
        second = (20, leaves(app)[1].line)  # on the second finding's label
        await pilot.click(FindingsTree, offset=second)
        await pilot.pause()
        assert opened == []
        assert SECOND.message in panel_text(app)
        await pilot.click(FindingsTree, offset=second)
        await pilot.pause()
        assert opened == [(course / "docs/B.md", 2)]

    drive(app, steps)


def test_clicking_a_branch_folds_and_unfolds_it(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        await pilot.click(FindingsTree, offset=(4, 0))
        await pilot.pause()
        assert leaves(app) == []
        await pilot.click(FindingsTree, offset=(4, 0))
        await pilot.pause()
        assert len(leaves(app)) == 2

    drive(app, steps)


def test_dragging_the_divider_resizes_the_findings_list(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        pane = app.screen.query_one("#findings-pane")
        before = pane.size.width
        destination = (app.screen.query_one(Divider).region.x - 12, 5)
        await pilot.mouse_down(Divider)
        await pilot.hover(None, offset=destination)
        await pilot.mouse_up(None, offset=destination)
        await pilot.pause()
        assert pane.size.width == before - 12

    drive(app, steps)


def test_r_runs_the_checks_again_and_shows_the_new_results(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIRST, SECOND], [SECOND])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await pilot.press("r")
        await settle(app, pilot)
        assert checker.folders == [course, course]
        rows = finding_rows(app)
        assert len(rows) == 1 and "docs/B.md" in rows[0]
        assert "1 finding" in app.sub_title
        assert SECOND.message in panel_text(app)

    drive(app, steps)


def test_ctrl_r_runs_the_checks_again_asking_the_web_afresh(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIRST, SECOND], [SECOND])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await pilot.press("ctrl+r")
        await settle(app, pilot)
        await pilot.press("r")
        await settle(app, pilot)
        assert checker.fresh == [False, True, False]
        assert len(finding_rows(app)) == 1

    drive(app, steps)


def test_no_findings_says_every_check_came_back_clean(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([]), course)

    async def steps(app, pilot):
        assert leaves(app) == []
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

    editors = {"vscode": Editor("vscode", "VS Code", True, True, broken_editor)}
    app = BirdwatcherApp(config_path, check=FakeChecker([FIRST]), editors=editors)

    async def steps(app, pilot):
        await pilot.press("enter")
        await pilot.pause()
        assert app.is_running
        assert FIRST.message in panel_text(app)

    drive(app, steps)


# Look


def test_bracketed_labels_and_frame_titles_show_as_written(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIXABLE]), course)

    async def steps(app, pilot):
        screen = app.screen
        assert str(screen.query_one("#fix", Button).label) == "[F] FIX"
        assert str(screen.query_one("#ignore", Button).label) == "[I] IGNORE"
        assert str(screen.query_one("#findings-pane").border_title) == "[ FINDINGS ]"
        assert str(screen.query_one("#detail-scroll").border_title) == "[ DETAIL ]"
        await press(app, pilot, "i")
        assert (
            str(app.screen.query_one("#cancel-ignore", Button).label) == "[ESC] CANCEL"
        )

    drive(app, steps)


# Layout

WIDE, NARROW = (140, 40), (100, 40)


def showing(app):
    """Which of the findings pane and the detail panel are on screen."""
    screen = app.screen
    return {
        name
        for name, selector in (
            ("findings", "#findings-pane"),
            ("detail", "#detail-scroll"),
        )
        if screen.query_one(selector).display
    }


def test_a_wide_window_shows_both_panes_half_and_half(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        assert showing(app) == {"findings", "detail"}
        assert app.screen.query_one("#findings-pane").outer_size.width == WIDE[0] // 2

    drive(app, steps, WIDE)


def test_a_narrow_window_shows_only_the_findings(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        assert showing(app) == {"findings"}

    drive(app, steps, NARROW)


@pytest.mark.parametrize("back", ["z", "escape"])
def test_z_in_a_narrow_window_opens_the_detail_page(tmp_path, back):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        await press(app, pilot, "z")
        assert showing(app) == {"detail"}
        assert FIRST.message in panel_text(app)
        await press(app, pilot, back)
        assert showing(app) == {"findings"}

    drive(app, steps, NARROW)


@pytest.mark.parametrize("back", ["z", "escape"])
def test_z_in_a_wide_window_zooms_the_detail(tmp_path, back):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        await press(app, pilot, "z")
        assert showing(app) == {"detail"}
        await press(app, pilot, back)
        assert showing(app) == {"findings", "detail"}

    drive(app, steps, WIDE)


def test_n_and_p_page_through_the_details_while_zoomed(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        await press(app, pilot, "z", "n")
        assert showing(app) == {"detail"}
        assert SECOND.message in panel_text(app)
        await press(app, pilot, "p")
        assert FIRST.message in panel_text(app)

    drive(app, steps, NARROW)


def test_resizing_the_window_switches_the_layout(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        await pilot.resize_terminal(*NARROW)
        await pilot.pause()
        assert showing(app) == {"findings"}
        await pilot.resize_terminal(*WIDE)
        await pilot.pause()
        assert showing(app) == {"findings", "detail"}

    drive(app, steps, WIDE)


def test_the_dragged_split_is_remembered(tmp_path):
    course = make_course(tmp_path / "course")
    first, config_path = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def drag(app, pilot):
        destination = (app.screen.query_one(Divider).region.x - 14, 5)
        await pilot.mouse_down(Divider)
        await pilot.hover(None, offset=destination)
        await pilot.mouse_up(None, offset=destination)
        await pilot.pause()

    drive(first, drag, WIDE)
    assert load_config(config_path).split == 40  # 56 of 140 columns
    second, _ = make_app(tmp_path, FakeChecker([FIRST]))

    async def check(app, pilot):
        assert app.screen.query_one("#findings-pane").outer_size.width == 56

    drive(second, check, WIDE)


# Themes


@pytest.mark.parametrize(
    ("dark", "expected"),
    [(True, "textual-dark"), (False, "textual-light"), (None, "textual-dark")],
    ids=["dark-mode", "light-mode", "unknown"],
)
def test_by_default_the_theme_follows_the_system(tmp_path, dark, expected):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]), course, dark=dark)

    async def steps(app, pilot):
        assert app.theme == expected
        assert load_config(config_path).theme == "auto"

    drive(app, steps)


def test_a_chosen_theme_is_used(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]))
    save_config(config_path, Config(course_dir=course, recent=(course,), theme="nord"))

    async def steps(app, pilot):
        assert app.theme == "nord"

    drive(app, steps)


def test_picking_a_theme_on_setup_previews_it_and_save_keeps_it(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        await press(app, pilot, "s")
        app.screen.query_one("#theme", Select).value = "gruvbox"
        await pilot.pause()
        assert app.theme == "gruvbox"
        await pilot.click("#save")
        await settle(app, pilot)
        assert load_config(config_path).theme == "gruvbox"
        assert app.theme == "gruvbox"

    drive(app, steps)


def test_escape_on_setup_puts_the_previous_theme_back(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        await press(app, pilot, "s")
        app.screen.query_one("#theme", Select).value = "gruvbox"
        await pilot.pause()
        await press(app, pilot, "escape")
        assert app.theme == "textual-dark"
        assert load_config(config_path).theme == "auto"

    drive(app, steps)


def test_choosing_match_the_system_again_follows_the_system(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]), dark=False)
    save_config(config_path, Config(course_dir=course, recent=(course,), theme="nord"))

    async def steps(app, pilot):
        await press(app, pilot, "s")
        assert app.screen.query_one("#theme", Select).value == "nord"
        app.screen.query_one("#theme", Select).value = "auto"
        await pilot.click("#save")
        await settle(app, pilot)
        assert load_config(config_path).theme == "auto"
        assert app.theme == "textual-light"

    drive(app, steps)


def test_a_theme_changed_from_the_command_palette_is_saved(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        app.theme = "tokyo-night"  # what the palette's "Change theme" does
        await settle(app, pilot)
        assert load_config(config_path).theme == "tokyo-night"

    drive(app, steps)


# Fixing

SITE_URL = "https://example.github.io/Course/B.html#beta-line"
FIXABLE = Finding(
    "links",
    Severity.ERROR,
    "docs/A.md",
    3,
    "Broken link.",
    Fix(3, "broken", "fixed", Destination("docs/B.md", 2, SITE_URL)),
)
NO_SITE = replace(FIXABLE, fix=replace(FIXABLE.fix, destination=None))


def drawn_row(app, index):
    """(indent, label) for a showing row, as the tree draws it."""
    tree = app.screen.query_one(FindingsTree)
    node = leaves(app)[index]
    label = tree.render_label(node, Style(), Style())
    depth = 0
    parent = node.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    indent = max(0, depth - 1) * tree.guide_depth
    return indent, label


def test_a_fixable_row_ends_in_a_fix_marker_at_the_pane_edge(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIXABLE, SECOND]), course)

    async def steps(app, pilot):
        indent, label = drawn_row(app, 0)
        assert label.plain.endswith("[F] FIX")
        assert indent + label.cell_len == usable_width(app)
        _, plain = drawn_row(app, 1)
        assert "[F]" not in plain.plain

    drive(app, steps)


def usable_width(app):
    """The tree's width less its vertical scrollbar's (shown or not) and the
    one blank cell kept before it."""
    tree = app.screen.query_one(FindingsTree)
    return tree.size.width - tree.styles.scrollbar_size_vertical - 1


def drawn_node(app, node):
    """(indent, label) for any showing node, as the tree draws it."""
    tree = app.screen.query_one(FindingsTree)
    depth = 0
    parent = node.parent
    while parent is not None:
        depth += 1
        parent = parent.parent
    return max(0, depth - 1) * tree.guide_depth, tree.render_label(
        node, Style(), Style()
    )


def test_a_branch_with_fixable_findings_ends_in_a_fix_all_marker(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIXABLE, OTHER_FIXABLE, SECOND])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        tree = app.screen.query_one(FindingsTree)
        check_branch = tree.root.children[0]
        indent, label = drawn_node(app, check_branch)
        assert label.plain.endswith("[F] FIX 2")
        assert "Broken section links" in label.plain
        assert indent + label.cell_len == usable_width(app)
        # docs/B.md holds one fix, the same as its row's marker: none here
        b_file = check_branch.children[1]
        assert "[F]" not in drawn_node(app, b_file)[1].plain

    drive(app, steps)


def test_a_branch_with_nothing_fixable_has_no_marker(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        branch = app.screen.query_one(FindingsTree).root.children[0]
        assert "[F]" not in drawn_node(app, branch)[1].plain

    drive(app, steps)


def test_clicking_a_branch_marker_asks_to_fix_that_branch(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIXABLE, OTHER_FIXABLE, SECOND])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        tree = app.screen.query_one(FindingsTree)
        check_branch = tree.root.children[0]
        y = check_branch.line - tree.scroll_offset.y
        await pilot.click(FindingsTree, offset=(usable_width(app) - 2, y))
        await settle(app, pilot)
        assert isinstance(app.screen, FixAllDialog)
        text = render_text(app.screen.query_one("#fix-all-text", Static).content)
        assert "Broken section links" in text
        assert "2 fixes will change 2 lines in 2 files" in text
        await press(app, pilot, "escape")
        assert check_branch.is_expanded  # the click asked; it did not fold

    drive(app, steps)


def test_fix_markers_stay_clear_of_the_scrollbar_in_a_long_list(tmp_path):
    course = make_course(tmp_path / "course")
    many = [replace(FIXABLE, line=n, message=f"Problem {n}.") for n in range(1, 80)]
    app, _ = make_app(tmp_path, FakeChecker(many), course)

    async def steps(app, pilot):
        tree = app.screen.query_one(FindingsTree)
        assert tree.show_vertical_scrollbar
        indent, label = drawn_row(app, 0)
        assert indent + label.cell_len == usable_width(app)

    drive(app, steps)


def test_long_messages_are_cut_to_the_pane_and_nothing_scrolls_sideways(tmp_path):
    course = make_course(tmp_path / "course")
    long = replace(SECOND, message="word " * 100)
    app, _ = make_app(tmp_path, FakeChecker([long]), course)

    async def steps(app, pilot):
        tree = app.screen.query_one(FindingsTree)
        indent, label = drawn_row(app, 0)
        assert label.plain.endswith("…")
        assert indent + label.cell_len <= usable_width(app)
        assert tree.virtual_size.width <= tree.size.width

    drive(app, steps)


def test_clicking_a_fix_marker_fixes_that_finding(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([SECOND, FIXABLE], [SECOND])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        tree = app.screen.query_one(FindingsTree)
        await press(app, pilot, "n")  # onto the other finding
        node = next(n for n in leaves(app) if n.data.finding == FIXABLE)
        assert tree.cursor_node is not node
        y = node.line - tree.scroll_offset.y
        await pilot.click(FindingsTree, offset=(usable_width(app) - 2, y))
        await settle(app, pilot)
        assert line_3(course) == "the fixed line"
        assert len(checker.folders) == 2

    drive(app, steps)


OTHER_FIXABLE = replace(
    FIXABLE, path="docs/B.md", line=2, message="Other.", fix=Fix(2, "beta", "gamma")
)
STALE_FIXABLE = replace(FIXABLE, line=1, message="Stale.", fix=Fix(1, "gone", "x"))


async def on_check_branch(app, pilot):
    """Put the cursor on the (only) check branch."""
    tree = app.screen.query_one(FindingsTree)
    tree.move_cursor(tree.root.children[0])
    await settle(app, pilot)


def test_a_highlighted_branch_summarizes_its_findings(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIXABLE, OTHER_FIXABLE, SECOND])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await on_check_branch(app, pilot)
        text = panel_text(app)
        assert "Broken section links" in text
        assert "3 findings here" in text
        assert "2 can be fixed, in 2 files" in text
        assert is_visible(app, "#fix")
        assert "FIX ALL 2" in str(app.screen.query_one("#fix", Button).label)

    drive(app, steps)


def test_a_branch_lists_every_finding_under_its_file_with_its_fix(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIXABLE, OTHER_FIXABLE, SECOND])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await on_check_branch(app, pilot)
        listing = render_text(app.screen.query_one("#branch-list", Static).content)
        lines = [" ".join(line.split()) for line in listing.splitlines()]
        assert lines.index("docs/A.md") < lines.index("docs/B.md")
        for finding in (FIXABLE, OTHER_FIXABLE, SECOND):
            assert finding.message in listing
        assert "ERROR 3 Broken link." in lines
        assert "- broken" in lines and "+ fixed" in lines  # FIXABLE's fix
        assert "- beta" in lines and "+ gamma" in lines

    drive(app, steps)


def test_the_fix_all_button_sits_above_the_branch_list(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIXABLE, OTHER_FIXABLE]), course)

    async def steps(app, pilot):
        await on_check_branch(app, pilot)
        button = app.screen.query_one("#fix", Button)
        listing = app.screen.query_one("#branch-list", Static)
        assert button.region.y < listing.region.y

    drive(app, steps)


def test_a_branch_mixing_checks_names_each_findings_check(tmp_path):
    course = make_course(tmp_path / "course")
    note = Finding("labs", Severity.INFO, "docs/A.md", 1, "Shared number.")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, note]), course)

    async def steps(app, pilot):
        await press(app, pilot, "g")  # by folder: docs holds both checks
        tree = app.screen.query_one(FindingsTree)
        tree.move_cursor(tree.root.children[0])
        await settle(app, pilot)
        listing = render_text(app.screen.query_one("#branch-list", Static).content)
        assert "Broken section links · First problem." in " ".join(listing.split())
        assert "labs · Shared number." in " ".join(listing.split())

    drive(app, steps)


def test_a_finding_shows_no_branch_list(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        await on_check_branch(app, pilot)
        await press(app, pilot, "n")
        assert not is_visible(app, "#branch-list")

    drive(app, steps)


def test_a_branch_with_nothing_to_fix_offers_no_fix(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        await on_check_branch(app, pilot)
        assert "nothing here can be fixed" in panel_text(app).lower()
        assert not is_visible(app, "#fix")
        assert not app.screen.check_action("fix", ())

    drive(app, steps)


def test_fix_all_asks_first_and_cancel_changes_nothing(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIXABLE, OTHER_FIXABLE])
    app, _ = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await on_check_branch(app, pilot)
        await press(app, pilot, "f")
        text = render_text(app.screen.query_one("#fix-all-text", Static).content)
        assert "Broken section links" in text
        assert "2 fixes will change 2 lines in 2 files" in text
        await press(app, pilot, "escape")
        assert line_3(course) == "the broken line"
        assert len(checker.folders) == 1

    drive(app, steps)


@pytest.mark.parametrize("how", ["enter", "button"])
def test_fix_all_fixes_every_fixable_finding_then_checks_once(tmp_path, how):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIXABLE, OTHER_FIXABLE, SECOND], [SECOND])
    app, config_path = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await on_check_branch(app, pilot)
        await press(app, pilot, "f")
        if how == "enter":
            await press(app, pilot, "enter")
        else:
            await pilot.click("#confirm-fix-all")
            await settle(app, pilot)
        assert line_3(course) == "the fixed line"
        b_md = (course / "docs" / "B.md").read_text(encoding="utf-8")
        assert b_md.split("\n")[1] == "gamma line"
        assert len(checker.folders) == 2  # one re-check for the whole batch
        logged = {entry.finding for entry in fix_log(config_path, course)}
        assert logged == {FIXABLE, OTHER_FIXABLE}
        cursor = app.screen.query_one(FindingsTree).cursor_node
        assert str(cursor.label).startswith("Broken section links")

    drive(app, steps)


def test_fixes_that_fail_are_skipped_and_reported(tmp_path):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIXABLE, STALE_FIXABLE], [STALE_FIXABLE])
    app, config_path = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await on_check_branch(app, pilot)
        await press(app, pilot, "f", "enter")
        assert line_3(course) == "the fixed line"
        assert [e.finding for e in fix_log(config_path, course)] == [FIXABLE]
        text = panel_text(app)
        assert "Fixed 1 of 2" in text
        assert "docs/A.md" in text and "line 1" in text
        assert "gone" in text  # the reason: the line no longer holds it

    drive(app, steps)


def test_a_rebuild_keeps_the_cursor_on_its_branch(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIRST, SECOND]), course)

    async def steps(app, pilot):
        await on_check_branch(app, pilot)
        await press(app, pilot, "r")
        assert cursor_label(app).startswith("Broken section links")

    drive(app, steps)


def line_3(course):
    return (course / "docs" / "A.md").read_text(encoding="utf-8").split("\n")[2]


def fix_log(config_path, course):
    return load_fixed(config_path.with_name(FIX_LOG_FILE), course)


def is_visible(app, selector):
    return app.screen.query_one(selector).display


async def press(app, pilot, *keys):
    await pilot.press(*keys)
    await settle(app, pilot)


@pytest.mark.parametrize("how", ["key", "button"])
def test_fixing_edits_the_file_rechecks_and_keeps_the_row(tmp_path, how):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIXABLE], [])
    app, config_path = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        assert is_visible(app, "#fix")
        if how == "key":
            await press(app, pilot, "f")
        else:
            await pilot.click("#fix")
            await settle(app, pilot)
        assert line_3(course) == "the fixed line"
        assert len(checker.folders) == 2
        rows = finding_rows(app)
        assert len(rows) == 1 and "FIXED" in rows[0]
        text = panel_text(app)
        assert "broken" in text and "fixed" in text
        assert "passes" in text
        assert [entry.finding for entry in fix_log(config_path, course)] == [FIXABLE]

    drive(app, steps)


def test_a_fix_the_recheck_still_reports_says_so(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIXABLE]), course)

    async def steps(app, pilot):
        await press(app, pilot, "f")
        assert "still reported" in panel_text(app)

    drive(app, steps)


def test_findings_without_a_fix_offer_none(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        assert not is_visible(app, "#fix")
        await press(app, pilot, "f")
        assert line_3(course) == "the broken line"
        assert fix_log(config_path, course) == []

    drive(app, steps)


def test_a_fix_that_no_longer_applies_is_refused(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIXABLE]), course)

    async def steps(app, pilot):
        (course / "docs" / "A.md").write_text("edited meanwhile\n", encoding="utf-8")
        await press(app, pilot, "f")
        assert (course / "docs" / "A.md").read_text(encoding="utf-8") == (
            "edited meanwhile\n"
        )
        assert fix_log(config_path, course) == []
        assert "FIXED" not in finding_rows(app)[0]

    drive(app, steps)


def test_fixes_are_remembered_after_the_app_closes(tmp_path):
    course = make_course(tmp_path / "course")
    first, _ = make_app(tmp_path, FakeChecker([FIXABLE], []), course)

    async def fix(app, pilot):
        await press(app, pilot, "f")

    drive(first, fix)
    second, _ = make_app(tmp_path, FakeChecker([]), course)

    async def steps(app, pilot):
        rows = finding_rows(app)
        assert len(rows) == 1 and "FIXED" in rows[0]

    drive(second, steps)


@pytest.mark.parametrize("how", ["key", "button"])
def test_view_in_editor_opens_the_fixed_line(tmp_path, how):
    course = make_course(tmp_path / "course")
    opened = []
    app, _ = make_app(tmp_path, FakeChecker([FIXABLE], []), course, opened)

    async def steps(app, pilot):
        await press(app, pilot, "f")
        if how == "key":
            await press(app, pilot, "e")
        else:
            await pilot.click("#view-editor")
            await pilot.pause()
        assert opened == [(course / "docs/A.md", 3)]

    drive(app, steps)


@pytest.mark.parametrize("how", ["key", "button"])
def test_view_on_site_opens_the_published_section(tmp_path, how):
    course = make_course(tmp_path / "course")
    urls = []
    app, _ = make_app(tmp_path, FakeChecker([FIXABLE], []), course, urls=urls)

    async def steps(app, pilot):
        await press(app, pilot, "f")
        if how == "key":
            await press(app, pilot, "w")
        else:
            await pilot.click("#view-site")
            await pilot.pause()
        assert urls == [SITE_URL]

    drive(app, steps)


def test_without_a_published_address_there_is_no_view_on_site(tmp_path):
    course = make_course(tmp_path / "course")
    opened = []
    app, _ = make_app(tmp_path, FakeChecker([NO_SITE], []), course, opened)

    async def steps(app, pilot):
        await press(app, pilot, "f")
        assert not is_visible(app, "#view-site")
        await press(app, pilot, "e")
        assert opened == [(course / "docs/A.md", 3)]

    drive(app, steps)


@pytest.mark.parametrize("how", ["key", "button"])
def test_undo_restores_the_text_and_rechecks(tmp_path, how):
    course = make_course(tmp_path / "course")
    checker = FakeChecker([FIXABLE], [], [FIXABLE])
    app, config_path = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await press(app, pilot, "f")
        if how == "key":
            await press(app, pilot, "u")
        else:
            await pilot.click("#undo")
            await settle(app, pilot)
        assert line_3(course) == "the broken line"
        assert len(checker.folders) == 3
        assert fix_log(config_path, course) == []
        rows = finding_rows(app)
        assert len(rows) == 1 and "ERROR" in rows[0]

    drive(app, steps)


def test_undo_refuses_when_the_line_changed_since_the_fix(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIXABLE], []), course)

    async def steps(app, pilot):
        await press(app, pilot, "f")
        (course / "docs" / "A.md").write_text("one\ntwo\nrewritten\n", encoding="utf-8")
        await press(app, pilot, "u")
        assert line_3(course) == "rewritten"
        assert len(fix_log(config_path, course)) == 1

    drive(app, steps)


@pytest.mark.parametrize("how", ["key", "button"])
def test_clear_forgets_the_fix_but_keeps_the_file(tmp_path, how):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIXABLE], []), course)

    async def steps(app, pilot):
        await press(app, pilot, "f")
        if how == "key":
            await press(app, pilot, "c")
        else:
            await pilot.click("#clear")
            await settle(app, pilot)
        assert finding_rows(app) == []
        assert line_3(course) == "the fixed line"
        assert fix_log(config_path, course) == []

    drive(app, steps)


def test_shift_c_clears_every_fixed_finding(tmp_path):
    course = make_course(tmp_path / "course")
    other = replace(FIXABLE, path="docs/B.md", line=2, fix=Fix(2, "beta", "gamma"))
    checker = FakeChecker([FIXABLE, other], [other], [])
    app, config_path = make_app(tmp_path, checker, course)

    async def steps(app, pilot):
        await press(app, pilot, "f")
        await press(app, pilot, "n", "f")
        assert len(fix_log(config_path, course)) == 2
        await press(app, pilot, "C")
        assert finding_rows(app) == []
        assert fix_log(config_path, course) == []

    drive(app, steps)


# Ignoring

WARN = Finding("labs", Severity.WARNING, "docs/A.md", 3, "Misplaced file.")
NOTE = Finding("labs", Severity.INFO, "docs/B.md", 2, "Shared number.")


def ignore_list(config_path, course):
    return load_ignores(config_path.with_name(IGNORE_FILE), course)


def dialog_open(app):
    return bool(app.screen.query("#ignore-reason"))


async def ignore(app, pilot, reason=""):
    """Press i, type a reason and press Enter."""
    await press(app, pilot, "i")
    app.screen.query_one("#ignore-reason", Input).value = reason
    await press(app, pilot, "enter")


@pytest.mark.parametrize(
    "finding", [FIRST, WARN, NOTE], ids=["error", "warning", "info"]
)
def test_ignoring_takes_a_reason_and_hides_the_finding(tmp_path, finding):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([finding]), course)

    async def steps(app, pilot):
        await press(app, pilot, "i")
        assert dialog_open(app)
        app.screen.query_one("#ignore-reason", Input).value = "on purpose"
        await press(app, pilot, "enter")
        assert not dialog_open(app)
        assert finding_rows(app) == []
        assert "1 ignored" in app.sub_title
        assert [i.reason for i in ignore_list(config_path, course)] == ["on purpose"]

    drive(app, steps)


@pytest.mark.parametrize(
    ("finding", "warns"),
    [(FIRST, True), (WARN, False), (NOTE, False)],
    ids=["error", "warning", "info"],
)
def test_only_errors_get_a_warning_in_the_dialog(tmp_path, finding, warns):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([finding]), course)

    async def steps(app, pilot):
        await press(app, pilot, "i")
        assert app.screen.query_one("#ignore-warning").display == warns

    drive(app, steps)


@pytest.mark.parametrize("how", ["escape", "button"])
def test_cancelling_the_dialog_keeps_the_finding(tmp_path, how):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([FIRST]), course)

    async def steps(app, pilot):
        await press(app, pilot, "i")
        if how == "escape":
            await press(app, pilot, "escape")
        else:
            await pilot.click("#cancel-ignore")
            await settle(app, pilot)
        assert not dialog_open(app)
        assert len(finding_rows(app)) == 1
        assert ignore_list(config_path, course) == []

    drive(app, steps)


def test_the_ignore_buttons_work_like_the_keys(tmp_path):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([WARN]), course)

    async def steps(app, pilot):
        await pilot.click("#ignore")
        await settle(app, pilot)
        assert dialog_open(app)
        await pilot.click("#confirm-ignore")
        await settle(app, pilot)
        assert finding_rows(app) == []
        assert len(ignore_list(config_path, course)) == 1

    drive(app, steps)


@pytest.mark.parametrize("how", ["key", "button"])
def test_h_shows_ignored_findings_and_unignoring_brings_them_back(tmp_path, how):
    course = make_course(tmp_path / "course")
    app, config_path = make_app(tmp_path, FakeChecker([WARN]), course)

    async def steps(app, pilot):
        await ignore(app, pilot, "kept for last term")
        await press(app, pilot, "h")
        rows = finding_rows(app)
        assert len(rows) == 1 and "IGNORED" in rows[0]
        assert "kept for last term" in panel_text(app)
        if how == "key":
            await press(app, pilot, "i")
        else:
            await pilot.click("#unignore")
            await settle(app, pilot)
        assert not dialog_open(app)
        rows = finding_rows(app)
        assert len(rows) == 1 and "WARNING" in rows[0]
        assert ignore_list(config_path, course) == []

    drive(app, steps)


def test_h_again_hides_ignored_findings(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([WARN, NOTE]), course)

    async def steps(app, pilot):
        await ignore(app, pilot)
        await press(app, pilot, "h")
        assert len(finding_rows(app)) == 2
        await press(app, pilot, "h")
        rows = finding_rows(app)
        assert len(rows) == 1 and "INFO" in rows[0]

    drive(app, steps)


def test_ignores_are_remembered_after_the_app_closes(tmp_path):
    course = make_course(tmp_path / "course")
    first, _ = make_app(tmp_path, FakeChecker([WARN]), course)

    async def steps(app, pilot):
        await ignore(app, pilot)

    drive(first, steps)
    second, _ = make_app(tmp_path, FakeChecker([WARN]), course)

    async def check(app, pilot):
        assert finding_rows(app) == []
        assert "1 ignored" in app.sub_title

    drive(second, check)


def test_an_ignore_survives_the_finding_moving_to_another_line(tmp_path):
    course = make_course(tmp_path / "course")
    moved = replace(WARN, line=7)
    app, _ = make_app(tmp_path, FakeChecker([WARN], [moved]), course)

    async def steps(app, pilot):
        await ignore(app, pilot)
        await press(app, pilot, "r")
        assert finding_rows(app) == []

    drive(app, steps)


def test_fixed_findings_cannot_be_ignored(tmp_path):
    course = make_course(tmp_path / "course")
    app, _ = make_app(tmp_path, FakeChecker([FIXABLE], []), course)

    async def steps(app, pilot):
        await press(app, pilot, "f")
        await press(app, pilot, "i")
        assert not dialog_open(app)
        assert not is_visible(app, "#ignore")

    drive(app, steps)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
