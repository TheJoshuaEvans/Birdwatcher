"""
The interface every check implements.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CheckContext:
    """What a check gets to look at.

    Attributes:
        root: Root folder of the course repository's files.
        site_url: Address of the repository's published site, ending in "/",
            or None when it is not known.
    """

    root: Path
    site_url: str | None


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
