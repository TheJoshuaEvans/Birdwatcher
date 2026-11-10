"""
The ignore list: findings the user chose to ignore, remembered per course
folder in a small JSON file.

An ignore is matched by the finding's check, file and message, not its line,
so it survives lines being added or removed above the finding. Identical
findings in one file are ignored together.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from dataclasses import dataclass
from datetime import datetime

from birdwatcher.core.course_store import read_entries, write_entries

IGNORE_FILE = "ignored.json"


@dataclass(frozen=True)
class Ignore:
    """
    One ignored finding.

    Attributes:
        check (str): The finding's check id.
        path (str): The finding's path.
        message (str): The finding's message.
        reason (str): Why it is ignored, as the user wrote it; "" for none.
        ignored_at (datetime): When it was ignored, timezone-aware.
    """

    check: str
    path: str
    message: str
    reason: str
    ignored_at: datetime

    def matches(self, finding):
        """
        Whether this ignore covers a finding.

        Args:
            finding (Finding): Any finding.

        Returns:
            bool: True when the check, path and message are the same (the
                line and severity do not matter).
        """
        return (self.check, self.path, self.message) == (
            finding.check,
            finding.path,
            finding.message,
        )


def ignore_finding(finding, reason, ignored_at):
    """
    Make the ignore for a finding.

    Args:
        finding (Finding): The finding to ignore.
        reason (str): Why; leading and trailing spaces are dropped.
        ignored_at (datetime): When, timezone-aware.

    Returns:
        Ignore: An ignore that matches the finding.
    """
    return Ignore(
        finding.check, finding.path, finding.message, reason.strip(), ignored_at
    )


def load_ignores(path, course_dir):
    """
    Read the ignores remembered for one course folder.

    Args:
        path (Path): The ignore file.
        course_dir (Path): The course folder (spelled any way, as for
            course_store.read_entries).

    Returns:
        list[Ignore]: In the order they were saved; entries that cannot be
            read are left out. Empty when there are none.
    """
    ignores = []
    for entry in read_entries(path, course_dir):
        try:
            ignored_at = datetime.fromisoformat(entry["ignored_at"])
            if ignored_at.tzinfo is None:
                continue
            ignores.append(
                Ignore(
                    check=entry["check"],
                    path=entry["path"],
                    message=entry["message"],
                    reason=entry["reason"],
                    ignored_at=ignored_at,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return ignores


def save_ignores(path, course_dir, ignores):
    """
    Remember the ignores for one course folder, replacing what was remembered
    for it before; other folders' ignores are kept.

    Args:
        path (Path): The ignore file.
        course_dir (Path): The course folder.
        ignores (Sequence[Ignore]): Everything to remember; empty forgets
            the folder.
    """
    entries = [
        {
            "check": ignore.check,
            "path": ignore.path,
            "message": ignore.message,
            "reason": ignore.reason,
            "ignored_at": ignore.ignored_at.isoformat(),
        }
        for ignore in ignores
    ]
    write_entries(path, course_dir, entries)
