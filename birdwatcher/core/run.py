"""
Running checks over a course folder, and the result the app and console show.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from birdwatcher.core.check import Check, CheckContext
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
        results: One CheckResult per check, in the order the checks were given.
    """

    course_dir: Path
    started_at: datetime
    results: tuple[CheckResult, ...]

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
class CheckFinished:
    """Event: a check finished (or failed; see result.error)."""

    result: CheckResult


def run_checks(course_dir, checks, *, site_url=None, on_event=None):
    """
    Run checks over a course folder and collect the results.

    A check that raises does not stop the run: its CheckResult records the error
    and the remaining checks still run.

    Args:
        course_dir (Path): The course folder.
        checks (Iterable[Check]): The checks to run, in order.
        site_url (str | None): Address of the course's published site, when
            known.
        on_event (Callable | None): Called with a CheckStarted before each check
            and a CheckFinished after it, as they happen.

    Returns:
        RunResult: The results, stamped with the time the run started.
    """
    started_at = datetime.now(UTC)
    context = CheckContext(root=course_dir, site_url=site_url)
    notify = on_event or (lambda event: None)
    results = []
    for check in checks:
        notify(CheckStarted(check))
        start = time.perf_counter()
        try:
            findings, error = tuple(check.run(context)), None
        except Exception as exception:  # noqa: BLE001 - one broken check must not stop the run
            findings, error = (), f"{type(exception).__name__}: {exception}"
        result = CheckResult(check, findings, time.perf_counter() - start, error)
        results.append(result)
        notify(CheckFinished(result))
    return RunResult(
        course_dir=course_dir, started_at=started_at, results=tuple(results)
    )


def _finding_order(finding):
    """Sort key: path, then line (whole-file findings first), then check id."""
    line = -1 if finding.line is None else finding.line
    return (finding.path, line, finding.check)
