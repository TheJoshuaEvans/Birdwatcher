"""
Contract tests for birdwatcher.checks.images.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.checks.images import CHECK, check_images
from birdwatcher.core.findings import Severity


def write_page(root, text):
    page = root / "docs" / "Notes.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("line", "source"),
    [
        ("![](Images/chart.png)", "Images/chart.png"),
        ("See ![ ](a.png) here", "a.png"),
        (
            '<img src="Images/Activation-Functions.png" style="zoom:50%;" />',
            "Images/Activation-Functions.png",
        ),
        ("<IMG SRC='b.png'>", "b.png"),
    ],
    ids=["markdown-empty", "markdown-blank", "html-no-alt", "html-upper-case"],
)
def test_images_without_alt_text_are_reported(tmp_path, line, source):
    write_page(tmp_path, f"Intro\n{line}\n")
    [finding] = check_images(tmp_path)
    assert (finding.check, finding.severity, finding.line) == (
        CHECK,
        Severity.WARNING,
        2,
    )
    assert source in finding.message
    assert finding.fix is None


@pytest.mark.parametrize(
    "text",
    [
        "![A sigmoid curve](s.png)\n",
        '<img src="s.png" alt="A sigmoid curve">\n',
        '<img src="divider.png" alt="">\n',
        "```\n![](in-code.png)\n```\n",
        "[a link](page.md) and ![alt](x.png)\n",
    ],
    ids=["markdown-alt", "html-alt", "html-decorative", "in-code", "link-not-image"],
)
def test_images_with_alt_text_are_fine(tmp_path, text):
    write_page(tmp_path, text)
    assert check_images(tmp_path) == []


def test_several_images_on_a_page_each_count(tmp_path):
    write_page(tmp_path, "![](a.png) ![](b.png)\n<img src='c.png'>\n")
    assert [f.line for f in check_images(tmp_path)] == [1, 1, 2]


def test_no_docs_folder_means_no_findings(tmp_path):
    assert check_images(tmp_path) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
