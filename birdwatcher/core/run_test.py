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
from birdwatcher.core.run import CheckFinished, CheckStarted, RunResult, run_checks

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
