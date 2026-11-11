"""
Contract tests for birdwatcher.checks.headings. Pages are shaped like the real
CS 212 lecture notes (an HTML <h1> title, then Markdown sections).

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.checks.headings import CHECK, check_headings
from birdwatcher.core.findings import Fix, Severity
from birdwatcher.core.fixes import apply_fix


def write_page(root, text):
    page = root / "docs" / "Notes.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(text, encoding="utf-8")
    return page


def test_a_skipped_level_is_reported_with_a_fix(tmp_path):
    write_page(tmp_path, "<h1>AI</h1>\n\n## Intro\n\n#### McCarthy's Definition\n")
    [finding] = check_headings(tmp_path)
    assert (finding.check, finding.severity, finding.line) == (
        CHECK,
        Severity.WARNING,
        5,
    )
    assert "2" in finding.message and "4" in finding.message
    assert finding.fix == Fix(line=5, before="#### ", after="### ")


def test_an_html_title_counts_as_level_one(tmp_path):
    write_page(tmp_path, "---\ntitle: X\n---\n<h1>Rules</h1>\n### The Problem\n")
    [finding] = check_headings(tmp_path)
    assert finding.line == 5
    assert finding.fix == Fix(line=5, before="### ", after="## ")


def test_a_skipping_html_heading_has_no_fix(tmp_path):
    write_page(tmp_path, "## Intro\n<h4>Deep</h4>\n")
    [finding] = check_headings(tmp_path)
    assert finding.line == 2 and finding.fix is None


@pytest.mark.parametrize(
    "text",
    [
        "## A\n### B\n#### C\n## D\n### E\n",
        "#### Starts deep\n##### Then one more\n",
        "## A\n```\n#### not a heading\n```\n### B\n",
        "## A\n####no space is not a heading\n",
        "## A\n\n# Back to the top\n## Then down one\n",
    ],
    ids=[
        "going-back-up-is-fine",
        "first-heading-free",
        "code-ignored",
        "no-space",
        "reset",
    ],
)
def test_these_are_not_reported(tmp_path, text):
    write_page(tmp_path, text)
    assert check_headings(tmp_path) == []


def test_the_fix_changes_only_the_heading_marker(tmp_path):
    page = write_page(tmp_path, "## Intro\n#### Analysis of #### things\n")
    [finding] = check_headings(tmp_path)
    apply_fix(page, finding.fix)
    assert page.read_text(encoding="utf-8") == "## Intro\n### Analysis of #### things\n"


def test_no_docs_folder_means_no_findings(tmp_path):
    assert check_headings(tmp_path) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
