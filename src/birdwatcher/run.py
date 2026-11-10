"""
Running checks over a course snapshot, and the result that reports are built from.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import time
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime

from birdwatcher.checks import Check, CheckContext
from birdwatcher.findings import Finding


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
    """Everything a report needs about one run.

    Attributes:
        repo: GitHub repository as "owner/name".
        commit: Full SHA of the commit that was checked.
        downloaded: True if the course files were downloaded for this run.
        stale: True if the cached files may be older than the repository.
        started_at: When the run started, timezone-aware (UTC).
        results: One CheckResult per check, in the order the checks were given.
    """

    repo: str
    commit: str
    downloaded: bool
    stale: bool
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

    def source_url(self, finding):
        """
        Link to a finding's file (and line) on GitHub, at the checked commit.

        Args:
            finding (Finding): A finding from this run.

        Returns:
            str: "https://github.com/<repo>/blob/<commit>/<path>", with "#L<line>"
                when the finding has a line; the path is URL-encoded.
        """
        path = urllib.parse.quote(finding.path, safe="/")
        url = f"https://github.com/{self.repo}/blob/{self.commit}/{path}"
        return url if finding.line is None else f"{url}#L{finding.line}"


@dataclass(frozen=True)
class CheckStarted:
    """Event: a check is about to run."""

    check: Check


@dataclass(frozen=True)
class CheckFinished:
    """Event: a check finished (or failed; see result.error)."""

    result: CheckResult


def run_checks(snapshot, repo, checks, *, site_url, on_event=None):
    """
    Run checks over a course snapshot and collect the results.

    A check that raises does not stop the run: its CheckResult records the error
    and the remaining checks still run.

    Args:
        snapshot (Snapshot): The course files, from fetch.ensure_materials.
        repo (str): GitHub repository as "owner/name".
        checks (Iterable[Check]): The checks to run, in order.
        site_url (str): Address of the repository's published site.
        on_event (Callable | None): Called with a CheckStarted before each check
            and a CheckFinished after it, as they happen.

    Returns:
        RunResult: The results, stamped with the time the run started.
    """
    started_at = datetime.now(UTC)
    context = CheckContext(
        root=snapshot.root, repo=repo, commit=snapshot.commit, site_url=site_url
    )
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
        repo=repo,
        commit=snapshot.commit,
        downloaded=snapshot.downloaded,
        stale=snapshot.stale,
        started_at=started_at,
        results=tuple(results),
    )


def _finding_order(finding):
    """Sort key: path, then line (whole-file findings first), then check id."""
    line = -1 if finding.line is None else finding.line
    return (finding.path, line, finding.check)
