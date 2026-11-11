"""
Running checks over a course folder, and the result the app and console show.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path

from birdwatcher.core.check import Check, CheckContext, CheckStopped
from birdwatcher.core.findings import Finding


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one check.

    Attributes:
        check: The check that ran.
        findings: What it found, in its own order.
        seconds: How long it took.
        error: None if it completed; otherwise a description of the exception
            that stopped it (its findings are then empty).
    """

    check: Check
    findings: tuple[Finding, ...]
    seconds: float
    error: str | None = None


@dataclass(frozen=True)
class RunResult:
    """Everything the app and the console need about one run.

    Attributes:
        course_dir: The course folder that was checked.
        started_at: When the run started, timezone-aware (UTC).
        results: One CheckResult per check that completed, in the order the
            checks were given.
        stopped: True when the run was stopped before every check completed
            (see run_checks); the checks missing from results did not finish.
    """

    course_dir: Path
    started_at: datetime
    results: tuple[CheckResult, ...]
    stopped: bool = False

    @property
    def findings(self):
        """
        Every finding from every check.

        Returns:
            list[Finding]: Ordered by path, then line (findings without a line
                first), then check id.
        """
        everything = [finding for result in self.results for finding in result.findings]
        return sorted(everything, key=_finding_order)

    def count(self, severity):
        """
        Count findings of one severity across all checks.

        Args:
            severity (Severity): The severity to count.

        Returns:
            int: The number of findings with that severity.
        """
        return sum(
            1
            for result in self.results
            for finding in result.findings
            if finding.severity == severity
        )

    def file_of(self, finding):
        """
        The file a finding is about.

        Args:
            finding (Finding): A finding from this run.

        Returns:
            Path: The finding's path inside the course folder.
        """
        return self.course_dir / finding.path


@dataclass(frozen=True)
class CheckStarted:
    """Event: a check is about to run."""

    check: Check


@dataclass(frozen=True)
class CheckProgress:
    """Event: a running check reported how far it has got.

    Attributes:
        check: The check.
        done: Units of work done so far.
        total: Units of work in all.
        detail: What it is working on, or None.
    """

    check: Check
    done: int
    total: int
    detail: str | None = None


@dataclass(frozen=True)
class CheckFinished:
    """Event: a check finished (or failed; see result.error)."""

    result: CheckResult


def run_checks(course_dir, checks, *, site_url=None, on_event=None, should_stop=None):
    """
    Run checks over a course folder and collect the results.

    A check that raises does not stop the run: its CheckResult records the error
    and the remaining checks still run.

    The run stops early once should_stop() returns True: no further check
    starts, and a running check is stopped the next time it reports progress
    (CheckContext.report_progress raises CheckStopped). A stopped check has no
    CheckResult and no CheckFinished event, and the RunResult is marked stopped.

    Args:
        course_dir (Path): The course folder.
        checks (Iterable[Check]): The checks to run, in order.
        site_url (str | None): Address of the course's published site, when
            known.
        on_event (Callable | None): Called with a CheckStarted before each check,
            a CheckProgress each time the check reports progress, and a
            CheckFinished after it, as they happen, on the calling thread
            (unless the check reports progress from another thread).
        should_stop (Callable[[], bool] | None): Asked before each check and
            at each progress report whether to stop; None never stops.

    Returns:
        RunResult: The results, stamped with the time the run started.
    """
    started_at = datetime.now(UTC)
    notify = on_event or (lambda event: None)
    stopping = should_stop or (lambda: False)
    results = []
    stopped = False
    for check in checks:
        if stopping():
            stopped = True
            break
        context = CheckContext(
            root=course_dir,
            site_url=site_url,
            report_progress=partial(_report_progress, check, notify, stopping),
        )
        notify(CheckStarted(check))
        start = time.perf_counter()
        try:
            findings, error = tuple(check.run(context)), None
        except CheckStopped:
            stopped = True
            break
        except Exception as exception:  # noqa: BLE001 - one broken check must not stop the run
            findings, error = (), f"{type(exception).__name__}: {exception}"
        result = CheckResult(check, findings, time.perf_counter() - start, error)
        results.append(result)
        notify(CheckFinished(result))
    return RunResult(
        course_dir=course_dir,
        started_at=started_at,
        results=tuple(results),
        stopped=stopped,
    )


def _report_progress(check, notify, stopping, done, total, detail=None):
    """A check's report_progress: stop if asked to, otherwise pass it on."""
    if stopping():
        raise CheckStopped
    notify(CheckProgress(check, done, total, detail))


def _finding_order(finding):
    """Sort key: path, then line (whole-file findings first), then check id."""
    line = -1 if finding.line is None else finding.line
    return (finding.path, line, finding.check)
