"""
Contract tests for birdwatcher.checks.links.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.checks.links import CHECK, check_links
from birdwatcher.core.findings import Severity

SITE = "https://lcc-cit.github.io/CS212-CourseMaterials/"


def make_site(root):
    """A docs/ folder with a page, an image, a lab folder with an index, a
    folder with a README, and a page whose name has a space."""
    docs = root / "docs"
    for path in [
        "Notes/Page.md",
        "Notes/Images/chart.png",
        "Labs/index.md",
        "Labs/Lab05/README.md",
        "Labs/Lab05/Lab05_Instructions.md",
        "Notes/My Page.md",
    ]:
        (docs / path).parent.mkdir(parents=True, exist_ok=True)
        (docs / path).write_text("# Title\n", encoding="utf-8")
    return docs


def link_from_notes(root, target, site_url=SITE):
    """Findings for a page in docs/Notes/ whose second line links to target."""
    page = root / "docs" / "Notes" / "Links.md"
    page.write_text(f"Intro\nSee [this]({target}).\n", encoding="utf-8")
    return check_links(root, site_url)


@pytest.mark.parametrize(
    "target",
    [
        "Page.md",
        "Images/chart.png",
        "../Labs/",
        "../Labs",
        "../Labs/Lab05/",
        "Page.html",
        "Page",
        "Page.md#section",
        "Page.md?plain=1",
        "My%20Page.md",
        "<My Page.md>",
        "./Page.md",
        f"{SITE}Notes/Page.html",
        f"{SITE}Labs/",
        "/CS212-CourseMaterials/Notes/Images/chart.png",
        "Images\\chart.png",  # browsers read a backslash as a slash
    ],
)
def test_links_to_what_exists_are_fine(tmp_path, target):
    make_site(tmp_path)
    assert link_from_notes(tmp_path, target) == []


@pytest.mark.parametrize(
    "target",
    [
        "https://example.com/Nope.md",
        "#no-such-section",
        "mailto:someone@example.com",
        "/elsewhere/Nope.md",
        "data:image/png;base64,AAAA",
    ],
)
def test_links_this_check_does_not_own_are_ignored(tmp_path, target):
    make_site(tmp_path)
    assert link_from_notes(tmp_path, target) == []


def test_full_site_addresses_are_ignored_without_a_site_url(tmp_path):
    make_site(tmp_path)
    assert link_from_notes(tmp_path, f"{SITE}Nope.html", site_url=None) == []


@pytest.mark.parametrize(
    "target",
    [
        "Nope.md",
        "Images/missing.png",
        "../Labs/Lab09/",
        "Images/",  # a folder without an index page
        f"{SITE}Labs/Nope.html",
        "/CS212-CourseMaterials/Nope.html",
    ],
)
def test_links_to_nothing_are_errors(tmp_path, target):
    make_site(tmp_path)
    [finding] = link_from_notes(tmp_path, target)
    assert (finding.check, finding.severity, finding.path, finding.line) == (
        CHECK,
        Severity.ERROR,
        "docs/Notes/Links.md",
        2,
    )
    assert target in finding.message
    assert finding.fix is None


@pytest.mark.parametrize(
    ("target", "suggestion"),
    [
        ("../Labs/Lab05/Lab05_Instructons.md", "Lab05_Instructions.md"),
        ("../Labs/Lab05/Lab05_Instructons.html", "Lab05_Instructions.html"),
    ],
    ids=["source", "published"],
)
def test_a_missing_file_with_a_close_name_is_suggested(tmp_path, target, suggestion):
    make_site(tmp_path)
    [finding] = link_from_notes(tmp_path, target)
    assert f"Did you mean '{suggestion}'?" in finding.message


def test_a_missing_file_with_no_close_name_suggests_nothing(tmp_path):
    make_site(tmp_path)
    [finding] = link_from_notes(tmp_path, "Zebra.md")
    assert "Did you mean" not in finding.message


@pytest.mark.parametrize(
    ("target", "spelled", "destination"),
    [
        ("images/Chart.PNG", "Images/chart.png", "docs/Notes/Images/chart.png"),
        ("page.md#section", "Page.md#section", "docs/Notes/Page.md"),
        ("../labs/lab05/", "../Labs/Lab05/", "docs/Labs/Lab05/README.md"),
        ("my%20page.md", "My%20Page.md", "docs/Notes/My Page.md"),
    ],
)
def test_a_link_in_the_wrong_letter_case_is_a_fixable_error(
    tmp_path, target, spelled, destination
):
    make_site(tmp_path)
    [finding] = link_from_notes(tmp_path, target)
    assert (finding.severity, finding.line) == (Severity.ERROR, 2)
    assert "letter case" in finding.message
    assert (finding.fix.line, finding.fix.before, finding.fix.after) == (
        2,
        target,
        spelled,
    )
    assert finding.fix.destination.path == destination


def test_links_outside_the_published_site_are_errors(tmp_path):
    make_site(tmp_path)
    (tmp_path / "GradingAssistant").mkdir()
    (tmp_path / "GradingAssistant" / "grade.py").write_text("", encoding="utf-8")
    [finding] = link_from_notes(tmp_path, "../../GradingAssistant/grade.py")
    assert finding.severity == Severity.ERROR
    assert "outside the published site" in finding.message


def test_html_pages_are_checked_too(tmp_path):
    docs = make_site(tmp_path)
    (docs / "index.html").write_text(
        "<ul>\n"
        f'<li><a href="{SITE}Notes/Page.html">Fine</a></li>\n'
        f'<li><a href="{SITE}Notes/Page_Draft.html">Renamed</a></li>\n'
        "</ul>\n",
        encoding="utf-8",
    )
    [finding] = check_links(tmp_path, SITE)
    assert (finding.path, finding.line) == ("docs/index.html", 3)
    assert "Page_Draft.html" in finding.message


def test_findings_are_in_file_and_line_order(tmp_path):
    docs = make_site(tmp_path)
    (docs / "B.md").write_text("[x](Gone1.md)\n\n[y](Gone2.md)\n", encoding="utf-8")
    (docs / "A.md").write_text("![z](Gone3.png)\n", encoding="utf-8")
    found = [(f.path, f.line) for f in check_links(tmp_path, SITE)]
    assert found == [("docs/A.md", 1), ("docs/B.md", 1), ("docs/B.md", 3)]


def test_no_docs_folder_means_no_findings(tmp_path):
    assert check_links(tmp_path, SITE) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
