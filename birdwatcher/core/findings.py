"""
Findings: the problems that checks report, as plain data.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import hashlib
from dataclasses import dataclass
from enum import StrEnum

ID_LENGTH = 12


class Severity(StrEnum):
    """How much a finding matters."""

    ERROR = "error"  # something is broken for readers
    WARNING = "warning"  # likely a mistake, or a problem for some readers
    INFO = "info"  # worth a look; may be intentional


@dataclass(frozen=True)
class Destination:
    """Where a fixed link leads, so the fix can be checked by eye.

    Attributes:
        path: The file the link now leads to, relative to the repository root,
            with forward slashes.
        line: 1-based line of the section it leads to, or None if unknown.
        url: The section's address on the published site, or None when the
            site is not known.
    """

    path: str
    line: int | None
    url: str | None


@dataclass(frozen=True)
class Fix:
    """A one-line text replacement that resolves a finding.

    Attributes:
        line: 1-based line in the finding's file.
        before: The exact text on that line to replace (its first occurrence).
        after: The text to put in its place.
        destination: Where the fixed link leads, for fixes to links; else None.
    """

    line: int
    before: str
    after: str
    destination: Destination | None = None


@dataclass(frozen=True)
class Finding:
    """One problem found in the course materials.

    Attributes:
        check: Identifier of the check that found it, e.g. "broken-section-link".
        severity: How much it matters.
        path: File it is in, relative to the repository root, with forward slashes.
        line: 1-based line number in that file, or None if it concerns the whole file.
        message: What is wrong, for a human reader.
        fix: A replacement that resolves it, when the check knows one; else None.
    """

    check: str
    severity: Severity
    path: str
    line: int | None
    message: str
    fix: Fix | None = None

    @property
    def id(self):
        """
        A short identifier that is the same for the same finding on every run.

        Returns:
            str: 12 lowercase hex characters, derived from the check, severity,
                path, line and message (not the fix); findings that differ in
                any of those get different ids.
        """
        line = "" if self.line is None else str(self.line)
        fields = (self.check, self.severity.value, self.path, line, self.message)
        # NUL can't appear in the fields, so different splits can't collide
        digest = hashlib.sha256("\0".join(fields).encode("utf-8")).hexdigest()
        return digest[:ID_LENGTH]
