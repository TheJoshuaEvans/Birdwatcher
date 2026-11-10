"""
Rows of the findings list: a finding, plus whether it was fixed or ignored.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from dataclasses import dataclass

from birdwatcher.core.findings import Finding
from birdwatcher.core.fix_log import FixedFinding
from birdwatcher.core.ignores import Ignore
from birdwatcher.ui.severity import SEVERITY_STYLES

FIXED_LABEL = ("FIXED", "bold green")
IGNORED_LABEL = ("IGNORED", "dim")


@dataclass(frozen=True)
class Row:
    """
    One row of the findings list.

    Attributes:
        finding (Finding): The finding.
        fixed (FixedFinding | None): Its fix log entry when it was fixed; None
            for a finding from the latest run.
        ignore (Ignore | None): The ignore that covers it, for an ignored
            finding that is shown; else None.
    """

    finding: Finding
    fixed: FixedFinding | None = None
    ignore: Ignore | None = None

    @property
    def label(self):
        """(label, Rich style): the severity, or FIXED or IGNORED."""
        if self.fixed:
            return FIXED_LABEL
        if self.ignore:
            return IGNORED_LABEL
        return SEVERITY_STYLES[self.finding.severity]

    @property
    def is_open(self):
        """Whether it is a finding to act on: neither fixed nor ignored."""
        return self.fixed is None and self.ignore is None

    @property
    def key(self):
        """Identifies the row across rebuilds of the list: the finding's id and
        whether it is open, fixed or ignored."""
        state = "fixed" if self.fixed else "ignored" if self.ignore else "open"
        return (self.finding.id, state)


def row_order(row):
    """
    Sort key for rows: path, then line (whole-file first), then check. A fixed
    row comes before an open one on the same line, so the cursor stays on a
    fix's outcome.
    """
    finding = row.finding
    line = -1 if finding.line is None else finding.line
    return (finding.path, line, row.fixed is None, finding.check)
