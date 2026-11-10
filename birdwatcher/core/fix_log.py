"""
The fix log: the findings Birdwatcher has fixed, remembered per course folder
in a small JSON file, until they are cleared.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from birdwatcher.core.findings import Destination, Finding, Fix, Severity

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
    entries = _read_log(path).get(_course_key(course_dir), [])
    if not isinstance(entries, list):
        return []
    fixed = []
    for entry in entries:
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
    path = Path(path)
    log = _read_log(path)
    key = _course_key(course_dir)
    if fixed:
        log[key] = [_to_json(entry) for entry in fixed]
    else:
        log.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")


def _course_key(course_dir):
    # resolve() makes the path absolute and, on Windows, uses the real letter case.
    return str(Path(course_dir).resolve())


def _read_log(path):
    try:
        log = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return log if isinstance(log, dict) else {}


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
            ),
        ),
        fixed_at=fixed_at,
    )
