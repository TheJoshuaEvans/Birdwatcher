"""
Per-course storage: a JSON file holding one list of entries per course folder.
The fix log and the ignore list are each one such file.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
from pathlib import Path


def read_entries(path, course_dir):
    """
    Read the entries stored for one course folder.

    Args:
        path (Path): The JSON file.
        course_dir (Path): The course folder; the same folder spelled
            differently (relative, or in another letter case on Windows)
            counts as the same.

    Returns:
        list: The stored entries (JSON values), in order. Empty when the file
            is missing or unreadable, or holds nothing for this folder.
    """
    entries = _read(path).get(_course_key(course_dir), [])
    return entries if isinstance(entries, list) else []


def write_entries(path, course_dir, entries):
    """
    Store the entries for one course folder, replacing what was stored for it.
    Other folders' entries are kept. Creates the file and its folder when
    needed.

    Args:
        path (Path): The JSON file.
        course_dir (Path): The course folder.
        entries (list): JSON-compatible entries; empty forgets the folder.
    """
    path = Path(path)
    store = _read(path)
    key = _course_key(course_dir)
    if entries:
        store[key] = list(entries)
    else:
        store.pop(key, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")


def _course_key(course_dir):
    # resolve() makes the path absolute and, on Windows, uses the real letter case.
    return str(Path(course_dir).resolve())


def _read(path):
    try:
        store = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return store if isinstance(store, dict) else {}
