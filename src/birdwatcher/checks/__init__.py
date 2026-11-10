"""
Checks: each inspects a course repository and returns findings.

ALL_CHECKS lists every check Birdwatcher runs, in report order.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from birdwatcher.checks import anchors


@dataclass(frozen=True)
class CheckContext:
    """What a check gets to look at.

    Attributes:
        root: Root folder of the course repository's files.
        repo: GitHub repository as "owner/name".
        commit: Full SHA of the commit being checked.
        site_url: Address of the repository's published site, ending in "/".
    """

    root: Path
    repo: str
    commit: str
    site_url: str


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


ALL_CHECKS = (
    Check(
        id=anchors.CHECK,
        title="Broken section links",
        description=(
            "Links to a #section that does not exist on the target page. Readers who "
            "click them land at the top of the page instead of the section. The "
            "site's link checker does not look at the part after '#'."
        ),
        run=lambda context: anchors.check_anchors(context.root, context.site_url),
    ),
)
