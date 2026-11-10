"""
Contract tests for birdwatcher.checks.numbering. The layouts mirror real ones
from the CS 212 course repository.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.checks.numbering import CHECK, check_numbering
from birdwatcher.core.findings import Severity


def make_files(root, *paths):
    """Create empty files (and their folders) under docs/; return the repo root."""
    for path in paths:
        file = root / "docs" / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("", encoding="utf-8")
    return root


def reported(root):
    """(path, severity) for each finding, checking what every finding shares."""
    findings = check_numbering(root)
    for finding in findings:
        assert finding.check == CHECK
        assert finding.line is None
        assert finding.fix is None
    return [(finding.path, finding.severity) for finding in findings]


def test_a_file_named_for_another_lab_is_reported(tmp_path):
    root = make_files(
        tmp_path, "Labs/Lab03-TextClassification/GroupA/CS212_Lab04_Part2_GroupA.html"
    )
    [finding] = check_numbering(root)
    assert finding.path == (
        "docs/Labs/Lab03-TextClassification/GroupA/CS212_Lab04_Part2_GroupA.html"
    )
    assert finding.severity == Severity.WARNING
    assert "Lab 4" in finding.message and "Lab 3" in finding.message


def test_a_file_named_for_another_group_is_reported(tmp_path):
    root = make_files(
        tmp_path,
        "Labs/Lab02-RuleBasedSystems/GroupB/CS212_Lab02_Instructions_GroupC.html",
    )
    [finding] = check_numbering(root)
    assert finding.severity == Severity.WARNING
    assert "Group C" in finding.message and "Group B" in finding.message


def test_a_file_wrong_on_both_counts_gets_both_findings(tmp_path):
    root = make_files(tmp_path, "Labs/Lab03-Text/GroupA/CS212_Lab04_Part2_GroupB.html")
    assert len(reported(root)) == 2


@pytest.mark.parametrize(
    "path",
    [
        "Labs/Lab07-ChatCompletion/Rubric_Lab7.md",
        "Labs/Lab01-Python/GroupA/CS212_Lab01_Instructions_GroupA_draft.md",
        "Labs/Lab02-ConstraintSolvers/CS212_Lab02_Instructions_GroupA-V2.md",
        "Labs/Lab02-ConstraintSolvers/GroupA-V2-Data/sections.csv",
        "Labs/Lab03-Text/GroupA/Labels.md",
        "Labs/Lab03-Text/CS212_CodeReviewForm-Lab03.docx",
        "Labs/CodeReviewProcedure.md",
        "Labs/CS212_Lab05_Overview.md",
        "Examples/Lab04-ClassifierMetrics/CS212_Lab04_Example.md",
    ],
    ids=[
        "unpadded-number",
        "matching-lab-and-group",
        "group-file-at-lab-level",
        "group-data-folder",
        "word-starting-with-lab",
        "code-review-form",
        "outside-lab-folders",
        "lab-file-outside-lab-folders",
        "examples-lab-folder",
    ],
)
def test_files_in_their_own_folders_are_fine(tmp_path, path):
    assert reported(make_files(tmp_path, path)) == []


def test_a_mismatch_inside_a_group_data_folder_is_reported(tmp_path):
    root = make_files(tmp_path, "Labs/Lab02-X/GroupA-V2-Data/roster_GroupB.csv")
    assert reported(root) == [
        ("docs/Labs/Lab02-X/GroupA-V2-Data/roster_GroupB.csv", Severity.WARNING)
    ]


def test_lab_folders_sharing_a_number_are_each_reported_as_info(tmp_path):
    root = make_files(
        tmp_path,
        "Labs/Lab02-ConstraintSolvers/a.md",
        "Labs/Lab02-RuleBasedSystems/b.md",
        "Labs/Lab03-TextClassification/c.md",
    )
    findings = check_numbering(root)
    assert [(f.path, f.severity) for f in findings] == [
        ("docs/Labs/Lab02-ConstraintSolvers", Severity.INFO),
        ("docs/Labs/Lab02-RuleBasedSystems", Severity.INFO),
    ]
    assert "Lab02-RuleBasedSystems" in findings[0].message
    assert "Lab02-ConstraintSolvers" in findings[1].message


def test_the_same_number_in_different_parent_folders_is_fine(tmp_path):
    root = make_files(
        tmp_path,
        "Labs/Lab02-ConstraintSolvers/a.md",
        "Examples/Lab02-Scheduling/b.md",
    )
    assert reported(root) == []


def test_findings_are_in_path_order(tmp_path):
    root = make_files(
        tmp_path,
        "Labs/Lab03-Text/GroupB/x_GroupA.md",
        "Labs/Lab03-Text/GroupA/x_Lab04.md",
    )
    paths = [path for path, _ in reported(root)]
    assert paths == sorted(paths)


def test_no_docs_folder_means_no_findings(tmp_path):
    assert check_numbering(tmp_path) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
