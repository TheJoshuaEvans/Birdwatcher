"""
Contract tests for birdwatcher.ui.tui.grouping. Paths are shaped like the real
CS 212 course repository.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys
from datetime import UTC, datetime

import pytest

from birdwatcher.core.findings import Finding, Fix, Severity
from birdwatcher.core.fix_log import FixedFinding
from birdwatcher.core.ignores import ignore_finding
from birdwatcher.ui.tui.grouping import Group, Grouping, group_rows
from birdwatcher.ui.tui.rows import Row, row_order

WHEN = datetime(2026, 11, 10, tzinfo=UTC)
TITLES = {"links": "Broken section links", "labs": "Renumbering leftovers"}
FOLDERS = {"docs/Labs/Lab02-X", "docs/Labs/Lab02-Y"}

LINK_A = Finding("links", Severity.ERROR, "docs/LectureNotes/Archive/A.md", 25, "a")
LINK_B = Finding("links", Severity.ERROR, "docs/LectureNotes/B.md", 3, "b")
SHARED_X = Finding("labs", Severity.INFO, "docs/Labs/Lab02-X", None, "shared")
SHARED_Y = Finding("labs", Severity.INFO, "docs/Labs/Lab02-Y", None, "shared")
MISPLACED = Finding(
    "labs", Severity.WARNING, "docs/Labs/Lab03/GroupA/x.html", None, "m"
)
FIXED = Row(
    Finding(
        "links", Severity.ERROR, "docs/LectureNotes/B.md", 9, "f", Fix(9, "a", "b")
    ),
    fixed=FixedFinding(
        Finding(
            "links", Severity.ERROR, "docs/LectureNotes/B.md", 9, "f", Fix(9, "a", "b")
        ),
        WHEN,
    ),
)
IGNORED = Row(MISPLACED, ignore=ignore_finding(MISPLACED, "", WHEN))


def rows(*items):
    made = [item if isinstance(item, Row) else Row(item) for item in items]
    return sorted(made, key=row_order)


def group(items, grouping):
    return group_rows(items, grouping, TITLES, lambda path: path in FOLDERS)


def shape(nodes):
    """The tree as nested (label, count, [children]) and finding messages."""
    return [
        (node.label, node.count, shape(node.children))
        if isinstance(node, Group)
        else node.finding.message
        for node in nodes
    ]


def test_by_check_groups_checks_in_order_then_paths():
    tree = group(rows(SHARED_X, LINK_B, LINK_A), Grouping.CHECK)
    assert shape(tree) == [
        (
            "Broken section links",
            2,
            [
                ("docs/LectureNotes/Archive/A.md", 1, ["a"]),
                ("docs/LectureNotes/B.md", 1, ["b"]),
            ],
        ),
        ("Renumbering leftovers", 1, [("docs/Labs/Lab02-X", 1, ["shared"])]),
    ]


def test_an_unknown_check_is_labelled_with_its_id_after_the_others():
    stray = Finding("zzz", Severity.INFO, "docs/A.md", 1, "z")
    tree = group(rows(stray, LINK_B), Grouping.CHECK)
    assert [node.label for node in tree] == ["Broken section links", "zzz"]


def test_by_folder_nests_folders_and_merges_single_folder_chains():
    tree = group(rows(LINK_A, LINK_B), Grouping.FOLDER)
    assert shape(tree) == [
        (
            "docs/LectureNotes",
            2,
            [
                ("Archive/A.md", 1, ["a"]),
                ("B.md", 1, ["b"]),
            ],
        )
    ]


def test_by_folder_puts_folder_findings_on_their_folders_branch():
    tree = group(rows(SHARED_X, SHARED_Y, MISPLACED), Grouping.FOLDER)
    assert shape(tree) == [
        (
            "docs/Labs",
            3,
            [
                ("Lab02-X", 1, ["shared"]),
                ("Lab02-Y", 1, ["shared"]),
                ("Lab03/GroupA/x.html", 1, ["m"]),
            ],
        )
    ]


def test_by_folder_keeps_a_folder_with_its_own_finding_and_children_separate():
    inside = Finding(
        "labs", Severity.WARNING, "docs/Labs/Lab02-X/GroupB/y.md", None, "y"
    )
    tree = group(rows(SHARED_X, inside), Grouping.FOLDER)
    assert shape(tree) == [
        (
            "docs/Labs/Lab02-X",
            2,
            ["shared", ("GroupB/y.md", 1, ["y"])],
        )
    ]


@pytest.mark.parametrize("grouping", list(Grouping))
def test_rows_keep_their_order_inside_a_branch(grouping):
    later = Finding("links", Severity.ERROR, "docs/LectureNotes/B.md", 30, "later")
    tree = group(rows(later, LINK_B), grouping)

    def messages(nodes):
        found = []
        for node in nodes:
            found.extend(
                messages(node.children)
                if isinstance(node, Group)
                else [node.finding.message]
            )
        return found

    assert messages(tree) == ["b", "later"]


def test_no_rows_means_no_branches():
    assert group([], Grouping.CHECK) == ()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
