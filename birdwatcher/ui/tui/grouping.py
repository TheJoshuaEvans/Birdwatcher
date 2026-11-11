"""
Grouping the findings list into a tree: by check or by folder.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from dataclasses import dataclass, field
from enum import StrEnum


class Grouping(StrEnum):
    """The ways the findings list can be grouped, in tab order."""

    CHECK = "check"
    FOLDER = "folder"


@dataclass(frozen=True)
class Group:
    """
    A branch of the findings tree.

    Attributes:
        label (str): What the branch shows (a check's title, or a folder or
            file path).
        children (tuple[Group | Row, ...]): Its sub-branches and rows, in
            display order.
    """

    label: str
    children: tuple

    @property
    def count(self):
        """The number of rows anywhere beneath this branch."""
        return sum(
            child.count if isinstance(child, Group) else 1 for child in self.children
        )


def group_rows(rows, grouping, check_titles, is_folder):
    """
    Arrange rows (already in row_order) into the tree for a grouping.

    - CHECK: one branch per check, in the order of `check_titles`, labelled
      with its title; inside, one branch per path, with its rows.
    - FOLDER: the folders of the paths as nested branches, each labelled with
      its own name; a file is a branch (labelled with its name) holding its
      rows; a row about a folder sits directly on that folder's branch, before
      its sub-branches. A folder branch with no rows of its own and exactly
      one sub-branch (folder or file) is merged with it, labelled
      "parent/child", so chains of single folders take one line.

    In every grouping, rows keep their given order inside a branch, and
    branches of paths and folders are in path order.

    Args:
        rows (Sequence[Row]): The rows, in row_order.
        grouping (Grouping): How to group them.
        check_titles (Mapping[str, str]): Check id -> title, in check order. A
            check missing from it is labelled with its id, after the others.
        is_folder (Callable[[str], bool]): Whether a finding's path names a
            folder.

    Returns:
        tuple[Group | Row, ...]: The top-level branches (and, for FOLDER, any
            rows about the top folder itself), in display order.
    """
    if grouping == Grouping.CHECK:
        by_check = _bucket(rows, lambda row: row.finding.check)
        order = [check for check in check_titles if check in by_check]
        order += [check for check in by_check if check not in check_titles]
        return tuple(
            Group(check_titles.get(check, check), _by_path(by_check[check]))
            for check in order
        )
    return _by_folder(rows, is_folder)


def _bucket(rows, key):
    """Rows by key, keys in order of first appearance, rows in their order."""
    buckets = {}
    for row in rows:
        buckets.setdefault(key(row), []).append(row)
    return buckets


def _by_path(rows):
    # Rows arrive in path order, so first appearance is path order.
    return tuple(
        Group(path, tuple(found))
        for path, found in _bucket(rows, lambda row: row.finding.path).items()
    )


@dataclass
class _Folder:
    rows: list = field(default_factory=list)  # findings about the folder itself
    folders: dict = field(default_factory=dict)  # name -> _Folder
    files: dict = field(default_factory=dict)  # name -> list of rows

    def descend(self, names):
        folder = self
        for name in names:
            folder = folder.folders.setdefault(name, _Folder())
        return folder


def _by_folder(rows, is_folder):
    root = _Folder()
    for row in rows:
        parts = row.finding.path.split("/")
        if is_folder(row.finding.path):
            root.descend(parts).rows.append(row)
        else:
            root.descend(parts[:-1]).files.setdefault(parts[-1], []).append(row)
    return tuple(root.rows) + _contents(root)


def _contents(folder):
    """A folder's sub-branches, folders and files together in name order."""
    names = sorted({*folder.folders, *folder.files})
    return tuple(
        _folder_branch(name, folder.folders[name])
        if name in folder.folders
        else Group(name, tuple(folder.files[name]))
        for name in names
    )


def _folder_branch(label, folder):
    while not folder.rows and len(folder.folders) + len(folder.files) == 1:
        if folder.files:
            [(name, found)] = folder.files.items()
            return Group(f"{label}/{name}", tuple(found))
        [(name, folder)] = folder.folders.items()
        label = f"{label}/{name}"
    return Group(label, tuple(folder.rows) + _contents(folder))
