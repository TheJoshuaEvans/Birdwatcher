"""
Contract tests for birdwatcher.ui.tui.watch: the watch strip, and the findings
view while checks are still running, driven headless through Textual's pilot.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import asyncio
import sys
import threading
import time

import pytest
from textual.widgets import Static

from birdwatcher.core.check import Check
from birdwatcher.core.findings import Finding, Severity
from birdwatcher.core.run import run_checks
from birdwatcher.ui.tui.app_test import (
    SCREEN,
    finding_rows,
    make_app,
    make_course,
    panel_text,
    render_text,
)
from birdwatcher.ui.tui.watch import BAR_DONE, BAR_LEFT, WatchStrip, progress_bar

QUICK = Finding("quick", Severity.ERROR, "docs/A.md", 3, "Quick problem.")
SLOW = Finding("slow", Severity.WARNING, "docs/B.md", 2, "Slow problem.")
WAIT_LIMIT = 5  # seconds a test waits for the app before failing


@pytest.mark.parametrize(
    ("done", "total", "width", "bar"),
    [
        (0, 10, 10, BAR_LEFT * 10),
        (5, 10, 10, BAR_DONE * 5 + BAR_LEFT * 5),
        (99, 100, 10, BAR_DONE * 9 + BAR_LEFT),  # not full until done
        (10, 10, 10, BAR_DONE * 10),
        (12, 10, 4, BAR_DONE * 4),  # clamped
        (-1, 10, 4, BAR_LEFT * 4),
        (0, 0, 4, BAR_DONE * 4),  # nothing to do is done
    ],
    ids=["none", "half", "almost", "all", "over", "under", "nothing-to-do"],
)
def test_progress_bar(done, total, width, bar):
    assert progress_bar(done, total, width) == bar


class SlowChecks:
    """Stands in for check_course with two real checks run by run_checks: a
    quick one, and a slow one that reports progress (3 of 10, at
    en.wikipedia.org) until `gate` is set. Each list of findings can be
    changed between runs. Records each run's should_stop."""

    def __init__(self, gate_open=False):
        self.gate = threading.Event()
        if gate_open:
            self.gate.set()
        self.quick_findings = [QUICK]
        self.slow_findings = [SLOW]
        self.stops = []

    def __call__(self, course_dir, on_event=None, should_stop=None, fresh=False):
        self.stops.append(should_stop)
        return run_checks(
            course_dir,
            [
                Check("quick", "Quick check", "d", lambda c: list(self.quick_findings)),
                Check("slow", "Slow links", "d", self._slow),
            ],
            on_event=on_event,
            should_stop=should_stop,
        )

    def _slow(self, context):
        context.report_progress(3, 10, "en.wikipedia.org")
        while not self.gate.wait(0.02):
            context.report_progress(3, 10, "en.wikipedia.org")
        return list(self.slow_findings)


def drive_live(app, checker, steps):
    """Run the app headless without waiting for its checks to finish. The
    checker's gate opens at the end, pass or fail, so no check runs on."""

    async def main():
        async with app.run_test(size=SCREEN) as pilot:
            try:
                await pilot.pause()
                await steps(app, pilot)
            finally:
                checker.gate.set()

    asyncio.run(main())


async def wait_until(pilot, condition):
    """Let the app run until condition() is true; fail after WAIT_LIMIT."""
    deadline = time.monotonic() + WAIT_LIMIT
    while not condition():
        assert time.monotonic() < deadline, "the app never got there"
        await pilot.pause(0.02)


def strip(app):
    return app.screen.query_one(WatchStrip)


def strip_text(app):
    return render_text(app.screen.query_one("#watch-status", Static).content)


def stop_shown(app):
    return app.screen.query_one("#stop").display


def rows_text(app):
    return " ".join(finding_rows(app))


def can_stop(app):
    return bool(app.screen.check_action("stop", ()))


def test_findings_show_while_a_slow_check_is_still_running(tmp_path):
    checker = SlowChecks()
    app, _ = make_app(tmp_path, checker, course=make_course(tmp_path / "course"))

    async def steps(app, pilot):
        await wait_until(pilot, lambda: "3/10" in strip_text(app))
        assert "Quick problem" in rows_text(app)
        assert "Slow problem" not in rows_text(app)
        text = strip_text(app)
        assert "WATCHING" in text
        assert "Slow links · en.wikipedia.org" in text
        assert strip(app).display
        assert stop_shown(app)
        assert can_stop(app)

        checker.gate.set()
        await wait_until(pilot, lambda: "Slow problem" in rows_text(app))
        await pilot.pause()
        assert not strip(app).display
        assert not can_stop(app)

    drive_live(app, checker, steps)


@pytest.mark.parametrize("how", ["key", "button"])
def test_stopping_keeps_the_finished_checks_and_says_what_was_not_checked(
    tmp_path, how
):
    checker = SlowChecks()
    app, _ = make_app(tmp_path, checker, course=make_course(tmp_path / "course"))

    async def steps(app, pilot):
        await wait_until(pilot, lambda: "3/10" in strip_text(app))
        if how == "key":
            await pilot.press("x")
        else:
            await pilot.click("#stop")
        await app.workers.wait_for_complete()
        await pilot.pause()
        text = strip_text(app)
        assert "STOPPED" in text
        assert "Slow links" in text
        assert strip(app).display
        assert not stop_shown(app)
        assert not can_stop(app)
        assert "Quick problem" in rows_text(app)

    drive_live(app, checker, steps)


def test_a_rerun_keeps_old_findings_until_their_check_finishes_again(tmp_path):
    checker = SlowChecks(gate_open=True)
    app, _ = make_app(tmp_path, checker, course=make_course(tmp_path / "course"))

    async def steps(app, pilot):
        await wait_until(pilot, lambda: "Slow problem" in rows_text(app))
        checker.gate.clear()
        checker.slow_findings = []
        await pilot.press("r")
        await wait_until(pilot, lambda: "3/10" in strip_text(app))
        assert "Slow problem" in rows_text(app)  # not re-checked yet

        checker.gate.set()
        await wait_until(pilot, lambda: "Slow problem" not in rows_text(app))
        await pilot.pause()
        assert not strip(app).display

    drive_live(app, checker, steps)


def test_findings_a_stopped_run_did_not_recheck_say_so(tmp_path):
    checker = SlowChecks(gate_open=True)
    app, _ = make_app(tmp_path, checker, course=make_course(tmp_path / "course"))

    async def steps(app, pilot):
        await wait_until(pilot, lambda: "Slow problem" in rows_text(app))
        checker.gate.clear()
        await pilot.press("r")
        await wait_until(pilot, lambda: "3/10" in strip_text(app))
        await pilot.press("x")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "Slow problem" in rows_text(app)
        while "Slow problem" not in panel_text(app):
            await pilot.press("n")
        assert "not re-checked" in panel_text(app)

        checker.gate.set()
        await pilot.press("r")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not strip(app).display
        assert "not re-checked" not in panel_text(app)

    drive_live(app, checker, steps)


def test_a_rerun_stops_the_run_it_replaces(tmp_path):
    checker = SlowChecks()
    app, _ = make_app(tmp_path, checker, course=make_course(tmp_path / "course"))

    async def steps(app, pilot):
        await wait_until(pilot, lambda: "3/10" in strip_text(app))
        await pilot.press("r")
        await wait_until(pilot, lambda: len(checker.stops) == 2)
        first, second = checker.stops
        assert first() is True
        assert second() is False

        checker.gate.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not strip(app).display
        assert rows_text(app).count("Slow problem") == 1

    drive_live(app, checker, steps)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
