"""
Contract tests for birdwatcher.core.run.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from birdwatcher.core.check import Check
from birdwatcher.core.findings import Finding, Severity
from birdwatcher.core.run import (
    CheckFinished,
    CheckProgress,
    CheckStarted,
    RunResult,
    run_checks,
)

COURSE = Path("course")
SITE = "https://lcc-cit.github.io/CS212-CourseMaterials/"


def finding(check, path, line, severity=Severity.ERROR):
    return Finding(check=check, severity=severity, path=path, line=line, message="m")


def fake_check(check_id, findings=(), error=None, seen=None):
    def run(context):
        if seen is not None:
            seen.append(context)
        if error is not None:
            raise error
        return list(findings)

    return Check(id=check_id, title=check_id.title(), description="d", run=run)


def test_runs_each_check_with_the_course_context():
    seen = []
    run_checks(COURSE, [fake_check("one", seen=seen)], site_url=SITE)
    [context] = seen
    assert (context.root, context.site_url) == (COURSE, SITE)


def test_site_url_is_optional():
    seen = []
    run_checks(COURSE, [fake_check("one", seen=seen)])
    assert seen[0].site_url is None


def test_result_describes_the_run():
    before = datetime.now(UTC)
    result = run_checks(COURSE, [fake_check("one")])
    assert result.course_dir == COURSE
    assert result.started_at.tzinfo is not None
    assert before <= result.started_at <= datetime.now(UTC)


def test_results_keep_check_order_and_their_findings():
    first = finding("one", "docs/B.md", 2)
    second = finding("two", "docs/A.md", 1)
    result = run_checks(
        COURSE, [fake_check("one", [first]), fake_check("two", [second])]
    )
    assert [r.check.id for r in result.results] == ["one", "two"]
    assert result.results[0].findings == (first,)
    assert result.results[1].findings == (second,)
    assert all(r.seconds >= 0 and r.error is None for r in result.results)


def test_a_failing_check_does_not_stop_the_run():
    survivor = finding("two", "docs/A.md", 1)
    result = run_checks(
        COURSE,
        [fake_check("one", error=ValueError("boom")), fake_check("two", [survivor])],
    )
    failed, worked = result.results
    assert failed.findings == ()
    assert "boom" in failed.error
    assert worked.findings == (survivor,)


def test_events_arrive_in_order_as_checks_run():
    events = []
    run_checks(
        COURSE,
        [fake_check("one"), fake_check("two", error=RuntimeError("x"))],
        on_event=events.append,
    )
    kinds = [
        (
            type(e).__name__,
            e.check.id if isinstance(e, CheckStarted) else e.result.check.id,
        )
        for e in events
    ]
    assert kinds == [
        ("CheckStarted", "one"),
        ("CheckFinished", "one"),
        ("CheckStarted", "two"),
        ("CheckFinished", "two"),
    ]
    assert isinstance(events[-1], CheckFinished)
    assert events[-1].result.error is not None


def reporting_check(check_id, steps, after=None):
    """A check that reports steps of progress, calling after(step) after each
    report, and finds nothing."""

    def run(context):
        for step in range(1, steps + 1):
            context.report_progress(step, steps, f"step {step}")
            if after is not None:
                after(step)
        return []

    return Check(id=check_id, title=check_id.title(), description="d", run=run)


def test_progress_reports_arrive_as_events_between_start_and_finish():
    events = []
    run_checks(COURSE, [reporting_check("slow", 2)], on_event=events.append)
    assert [type(e).__name__ for e in events] == [
        "CheckStarted",
        "CheckProgress",
        "CheckProgress",
        "CheckFinished",
    ]
    assert [(e.check.id, e.done, e.total, e.detail) for e in events[1:3]] == [
        ("slow", 1, 2, "step 1"),
        ("slow", 2, 2, "step 2"),
    ]


def test_a_run_that_is_not_stopped_says_so():
    result = run_checks(COURSE, [reporting_check("slow", 3)], should_stop=lambda: False)
    assert result.stopped is False
    assert [r.check.id for r in result.results] == ["slow"]


def test_stopping_before_a_check_skips_it_and_the_rest():
    events = []
    stop = []
    first = fake_check("first", [finding("first", "docs/A.md", 1)])
    second = fake_check("second")
    result = run_checks(
        COURSE,
        [first, reporting_check("trigger", 1, after=stop.append), second],
        on_event=events.append,
        should_stop=lambda: bool(stop),
    )
    assert result.stopped is True
    assert [r.check.id for r in result.results] == ["first", "trigger"]
    assert "second" not in {e.check.id for e in events if isinstance(e, CheckStarted)}


def test_a_check_reporting_progress_after_a_stop_is_cut_off():
    events = []
    stop = []
    result = run_checks(
        COURSE,
        [reporting_check("slow", 5, after=stop.append), fake_check("next")],
        on_event=events.append,
        should_stop=lambda: bool(stop),
    )
    assert result.stopped is True
    assert result.results == ()
    progress = [e.done for e in events if isinstance(e, CheckProgress)]
    assert progress == [1]  # the second report raised instead of being sent
    assert not any(isinstance(e, CheckFinished) for e in events)


def test_a_check_that_never_reports_progress_finishes_despite_a_stop():
    stop = []

    def run(context):
        stop.append(True)
        return [finding("quiet", "docs/A.md", 1)]

    quiet = Check(id="quiet", title="Quiet", description="d", run=run)
    result = run_checks(COURSE, [quiet], should_stop=lambda: bool(stop))
    assert [r.check.id for r in result.results] == ["quiet"]
    assert result.results[0].error is None


def test_progress_without_a_watcher_does_nothing():
    result = run_checks(COURSE, [reporting_check("slow", 3)])
    assert result.stopped is False
    assert result.results[0].error is None


def make_run(*per_check):
    return run_checks(
        COURSE, [fake_check(f"c{n}", findings) for n, findings in enumerate(per_check)]
    )


def test_findings_are_merged_in_path_line_check_order():
    a1 = finding("c1", "docs/A.md", 1)
    a_file = finding("c0", "docs/A.md", None)
    a1_other = finding("c0", "docs/A.md", 1)
    b3 = finding("c0", "docs/B.md", 3)
    result = make_run([b3, a1_other, a_file], [a1])
    assert result.findings == [a_file, a1_other, a1, b3]


def test_count_by_severity():
    result = make_run(
        [finding("c0", "a", 1), finding("c0", "a", 2, Severity.WARNING)],
        [finding("c1", "b", 1, Severity.WARNING)],
    )
    assert result.count(Severity.ERROR) == 1
    assert result.count(Severity.WARNING) == 2
    assert result.count(Severity.INFO) == 0


def test_file_of_a_finding_is_inside_the_course_folder():
    result = RunResult(COURSE, datetime.now(UTC), ())
    found = finding("c", "docs/Lesson Plans/Week 1.md", 3)
    assert result.file_of(found) == COURSE / "docs" / "Lesson Plans" / "Week 1.md"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
