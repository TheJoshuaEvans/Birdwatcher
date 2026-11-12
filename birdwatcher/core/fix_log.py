"""
The fix log: the findings Birdwatcher has fixed, remembered per course folder
in a small JSON file, until they are cleared.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from dataclasses import dataclass
from datetime import datetime

from birdwatcher.core.course_store import read_entries, write_entries
from birdwatcher.core.findings import Destination, Edit, Finding, Fix, Severity

FIX_LOG_FILE = "fixes.json"


@dataclass(frozen=True)
class FixedFinding:
    """
    A finding that was fixed.

    Attributes:
        finding (Finding): The finding as it was reported, with its fix.
        fixed_at (datetime): When the fix was applied, timezone-aware.
    """

    finding: Finding
    fixed_at: datetime


def load_fixed(path, course_dir):
    """
    Read the fixed findings remembered for one course folder.

    Args:
        path (Path): The fix log file.
        course_dir (Path): The course folder; the same folder spelled
            differently (relative, or in another letter case on Windows)
            counts as the same.

    Returns:
        list[FixedFinding]: In the order they were saved. Empty when the file
            is missing or unreadable, or remembers nothing for this folder;
            entries that cannot be read are left out.
    """
    fixed = []
    for entry in read_entries(path, course_dir):
        try:
            fixed.append(_from_json(entry))
        except (KeyError, TypeError, ValueError):
            continue
    return fixed


def save_fixed(path, course_dir, fixed):
    """
    Remember the fixed findings for one course folder, replacing what was
    remembered for it before. Other folders' entries are kept. Creates the
    file and its folder when needed.

    Args:
        path (Path): The fix log file.
        course_dir (Path): The course folder.
        fixed (Sequence[FixedFinding]): Everything to remember for it; empty
            forgets the folder.
    """
    write_entries(path, course_dir, [_to_json(entry) for entry in fixed])


def _to_json(entry):
    finding, fix = entry.finding, entry.finding.fix
    destination = fix.destination
    return {
        "check": finding.check,
        "severity": finding.severity.value,
        "path": finding.path,
        "line": finding.line,
        "message": finding.message,
        "fix": {
            "line": fix.line,
            "before": fix.before,
            "after": fix.after,
            "destination": None
            if destination is None
            else {
                "path": destination.path,
                "line": destination.line,
                "url": destination.url,
            },
            "also": [
                {"line": edit.line, "before": edit.before, "after": edit.after}
                for edit in fix.also
            ],
        },
        "fixed_at": entry.fixed_at.isoformat(),
    }


def _from_json(data):
    fix = data["fix"]
    destination = fix["destination"]
    fixed_at = datetime.fromisoformat(data["fixed_at"])
    if fixed_at.tzinfo is None:
        raise ValueError("fixed_at has no time zone")
    return FixedFinding(
        finding=Finding(
            check=data["check"],
            severity=Severity(data["severity"]),
            path=data["path"],
            line=data["line"],
            message=data["message"],
            fix=Fix(
                line=fix["line"],
                before=fix["before"],
                after=fix["after"],
                destination=None
                if destination is None
                else Destination(
                    destination["path"], destination["line"], destination["url"]
                ),
                # Logs from before multi-line fixes have no "also"
                also=tuple(
                    Edit(edit["line"], edit["before"], edit["after"])
                    for edit in fix.get("also", [])
                ),
            ),
        ),
        fixed_at=fixed_at,
    )
