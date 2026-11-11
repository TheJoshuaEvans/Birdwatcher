"""
The interface every check implements.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


class CheckStopped(Exception):  # noqa: N818 - a signal, like StopIteration
    """Raised by CheckContext.report_progress when the run has been asked to
    stop. A check lets it propagate; the run then ends without that check's
    result."""


def ignore_progress(done, total, detail=None):
    """The report_progress of a context that nobody watches: does nothing."""


@dataclass(frozen=True)
class CheckContext:
    """What a check gets to look at.

    Attributes:
        root: Root folder of the course repository's files.
        site_url: Address of the repository's published site, ending in "/",
            or None when it is not known.
        report_progress: A long-running check calls report_progress(done,
            total, detail) as it goes: done of total units of work, and
            optionally what it is working on (a str, or None). It raises
            CheckStopped when the run has been asked to stop, so a check that
            reports progress can be stopped. Calling it is optional.
        look_up_links: Asks web servers about addresses, as
            core.web.look_up_links(addresses, report_progress) does; None
            when the network is not to be used.
    """

    root: Path
    site_url: str | None
    report_progress: Callable[..., None] = ignore_progress
    look_up_links: Callable[..., dict] | None = None


@dataclass(frozen=True)
class Check:
    """A registered check.

    Attributes:
        id: Short identifier, used in findings and on the command line.
        title: Human-readable name.
        description: One or two sentences on what it looks for and why it matters.
        run: Inspects a CheckContext and returns a list of findings.
    """

    id: str
    title: str
    description: str
    run: Callable[[CheckContext], list]
