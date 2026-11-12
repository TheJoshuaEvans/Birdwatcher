"""
Renumbering leftovers: lab files in the wrong lab's or group's folder, and lab
folders that share a number.

Labs live in folders named "Lab<number>-<topic>" (e.g. Lab03-TextClassification),
sometimes with one folder per group ("GroupA"). When labs are renumbered or
copied, files named for one lab or group can be left behind in another's
folder, and students may open the wrong one.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import re
from collections import defaultdict
from pathlib import Path

from birdwatcher.core.course import site_folder
from birdwatcher.core.findings import Finding, Severity

CHECK = "renumbering-leftover"

LAB_FOLDER = re.compile(r"^Lab(\d+)(?:-|$)")
GROUP_FOLDER = re.compile(r"^Group([A-Z])(?![a-z])")
# Not after another letter, so "collab2" and "Labels" are not lab names
LAB_IN_NAME = re.compile(r"(?<![A-Za-z])Lab[_\- ]?(\d+)")
GROUP_IN_NAME = re.compile(r"(?<![A-Za-z])Group([A-Z])(?![a-z])")
LEFTOVER = "Probably left over from renumbering or copying."


def check_numbering(repo_root):
    """
    Find lab files named for a different lab or group than the folder they are
    in, and lab folders that share a number.

    Looks at every file and folder under the repository's docs/ folder. A lab
    folder's name starts with "Lab" and its number ("Lab03-TextClassification"
    is lab 3); a group folder's name starts with "Group" and its letter
    ("GroupA", "GroupA-V2-Data" are group A). A file is named for a lab when
    its name contains "Lab" directly followed by a number, optionally after
    "_", "-" or a space ("CS212_Lab04_...", "Rubric_Lab7"), and for a group
    when it contains "Group" and a capital letter that ends the word
    ("..._GroupB.md", "...GroupC-V2.md"). Numbers are compared as numbers, so
    Lab7 matches Lab07.

    Args:
        repo_root (Path): Root folder of the course repository.

    Returns:
        list[Finding]: In path order, with no line (they concern whole files
            or folders):
            - a warning for each file named for another lab than its nearest
              lab folder,
            - a warning for each file named for another group than its
              nearest group folder,
            - info for each lab folder that shares its number with another
              lab folder in the same parent folder (the finding's path is the
              folder; the message names the others).
            Empty when the repository has no docs/ folder.
    """
    repo_root = Path(repo_root).resolve()
    docs = site_folder(repo_root)
    if not docs.is_dir():
        return []

    findings = []
    for item in sorted(docs.rglob("*")):
        path = item.relative_to(repo_root).as_posix()
        if item.is_file():
            findings.extend(_misplaced(item, docs, path))
    findings.extend(_shared_numbers(docs, repo_root))
    return sorted(findings, key=lambda finding: finding.path)


def _misplaced(file, docs, path):
    """Warnings for a file named for another lab or group than its folders."""
    folders = file.relative_to(docs).parts[:-1]
    found = []
    named_lab = LAB_IN_NAME.search(file.name)
    lab_folder = _nearest(folders, LAB_FOLDER)
    if named_lab and lab_folder:
        named, folder_name, folder_number = int(named_lab[1]), *lab_folder
        if named != int(folder_number):
            found.append(
                _warning(
                    path,
                    f"Named for Lab {named}, but it is in the Lab "
                    f"{int(folder_number)} folder ({folder_name}). {LEFTOVER}",
                )
            )
    named_group = GROUP_IN_NAME.search(file.name)
    group_folder = _nearest(folders, GROUP_FOLDER)
    if named_group and group_folder:
        folder_name, letter = group_folder
        if named_group[1] != letter:
            found.append(
                _warning(
                    path,
                    f"Named for Group {named_group[1]}, but it is in the Group "
                    f"{letter} folder ({folder_name}). {LEFTOVER}",
                )
            )
    return found


def _nearest(folders, pattern):
    """(folder name, captured number or letter) of the nearest matching folder."""
    for name in reversed(folders):
        match = pattern.match(name)
        if match:
            return name, match[1]
    return None


def _warning(path, message):
    return Finding(CHECK, Severity.WARNING, path, None, message)


def _shared_numbers(docs, repo_root):
    """Info for each lab folder sharing its number with a sibling lab folder."""
    found = []
    parents = [docs, *(item for item in sorted(docs.rglob("*")) if item.is_dir())]
    for parent in parents:
        by_number = defaultdict(list)
        for child in sorted(parent.iterdir()):
            match = LAB_FOLDER.match(child.name) if child.is_dir() else None
            if match:
                by_number[int(match[1])].append(child)
        for number, folders in by_number.items():
            if len(folders) == 1:
                continue
            for folder in folders:
                others = ", ".join(o.name for o in folders if o != folder)
                found.append(
                    Finding(
                        CHECK,
                        Severity.INFO,
                        folder.relative_to(repo_root).as_posix(),
                        None,
                        f"Shares lab number {number} with {others}. One of them "
                        "may be left over from renumbering.",
                    )
                )
    return found
