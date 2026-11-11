"""
Contract tests for birdwatcher.checks.frontmatter.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.checks.frontmatter import CHECK, check_front_matter
from birdwatcher.core.findings import Severity

COMPLETE = '---\ntitle: "Lab 5"\ndescription: ANNs\nauthor: Brian Bird\n---\nBody\n'


def write_page(root, text, name="Lab.md"):
    page = root / "docs" / name
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(text, encoding="utf-8")


def test_a_complete_page_is_fine(tmp_path):
    write_page(tmp_path, COMPLETE)
    assert check_front_matter(tmp_path) == []


def test_a_page_without_front_matter_is_reported(tmp_path):
    write_page(tmp_path, "<h1>Lab</h1>\n")
    [finding] = check_front_matter(tmp_path)
    assert (finding.check, finding.severity, finding.path, finding.line) == (
        CHECK,
        Severity.INFO,
        "docs/Lab.md",
        None,
    )
    assert "no front matter" in finding.message
    assert finding.fix is None


@pytest.mark.parametrize(
    ("front", "missing"),
    [
        ("title: X\n", ["description", "author"]),
        ("title: X\ndescription:\nauthor: B\n", ["description"]),
        ('title: ""\ndescription: d\nauthor: B\nkeywords: k\n', ["title"]),
    ],
    ids=["two-missing", "empty-value", "empty-quotes"],
)
def test_missing_keys_are_named(tmp_path, front, missing):
    write_page(tmp_path, f"---\n{front}---\nBody\n")
    [finding] = check_front_matter(tmp_path)
    for key in missing:
        assert key in finding.message
    for key in {"title", "description", "author"} - set(missing):
        assert key not in finding.message.split(":", 1)[-1]


def test_keywords_are_optional(tmp_path):
    write_page(tmp_path, COMPLETE)
    assert "keywords" not in COMPLETE and check_front_matter(tmp_path) == []


def test_readme_files_are_skipped(tmp_path):
    write_page(tmp_path, "# Example project\n", name="Examples/Demo/README.md")
    assert check_front_matter(tmp_path) == []


def test_no_docs_folder_means_no_findings(tmp_path):
    assert check_front_matter(tmp_path) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
