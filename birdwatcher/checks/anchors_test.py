"""
Contract tests for birdwatcher.checks.anchors.

Expected heading ids marked "live" were read from the published CS 212 site.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys
import textwrap

import pytest

from birdwatcher.checks.anchors import CHECK, check_anchors, heading_id
from birdwatcher.core.findings import Destination, Fix, Severity

SITE = "https://lcc-cit.github.io/CS212-CourseMaterials/"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Architect & Planner Mindset (Before Coding)",
            "architect--planner-mindset-before-coding",
        ),
        (
            "Process & Documentation Mindset (After Coding)",
            "process--documentation-mindset-after-coding",
        ),
        ("Graphic Processing Unit (GPU)", "graphic-processing-unit-gpu"),
        (
            "2. External Libraries for GPU Acceleration",
            "2-external-libraries-for-gpu-acceleration",
        ),
        ("GPU vs. CPU", "gpu-vs-cpu"),
        ("Objective:", "objective"),
        ("The *big* idea", "the-big-idea"),
        ("Using `model.fit()`", "using-modelfit"),
        ("See [the guide](Guide.md)", "see-the-guide"),
        ("my_variable rules", "my_variable-rules"),
        ("<em>Styled</em> heading", "styled-heading"),
        ("Café menu", "café-menu"),
    ],
    ids=[
        "live-ampersand",
        "live-ampersand-2",
        "live-parentheses",
        "live-numbered",
        "live-period",
        "colon",
        "emphasis",
        "code-span",
        "link-text",
        "underscore-in-word",
        "html-tag",
        "non-ascii-letter",
    ],
)
def test_heading_id_follows_kramdown(text, expected):
    assert heading_id(text) == expected


def write_docs(root, pages):
    """Create docs/<path> files from dedented text; return the repo root."""
    for path, text in pages.items():
        file = root / "docs" / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return root


def broken(root):
    """Run the check and return (path, line, message) for each finding."""
    findings = check_anchors(root, SITE)
    for finding in findings:
        assert finding.check == CHECK
        assert finding.severity == Severity.ERROR
    return [(f.path, f.line, f.message) for f in findings]


def test_link_to_an_existing_heading_is_fine(tmp_path):
    write_docs(
        tmp_path,
        {
            "Page.md": """
        - [Goals](#goals)

        ## Goals
    """
        },
    )
    assert broken(tmp_path) == []


def test_link_to_a_missing_section_is_reported_at_its_line(tmp_path):
    write_docs(
        tmp_path,
        {
            "Page.md": """
        # Title

        - [Goals](#goal)

        ## Goals
    """
        },
    )
    [(path, line, message)] = broken(tmp_path)
    assert path == "docs/Page.md"
    assert line == 3
    assert "#goal" in message


def test_message_suggests_the_closest_real_id(tmp_path):
    write_docs(
        tmp_path,
        {
            "Page.md": """
        - [Plan](#architect-planner-mindset)

        ## Architect & Planner Mindset
    """
        },
    )
    [(_, _, message)] = broken(tmp_path)
    assert "#architect--planner-mindset" in message


def test_line_numbers_count_front_matter(tmp_path):
    write_docs(
        tmp_path,
        {
            "Page.md": """
        ---
        title: Page
        ---
        [Nowhere](#nowhere)
    """
        },
    )
    [(_, line, _)] = broken(tmp_path)
    assert line == 4


@pytest.mark.parametrize(
    "target",
    [
        "Other.md#missing",
        "Other.html#missing",
        "Sub/../Other.md#missing",
        f"{SITE}Other.html#missing",
    ],
    ids=["md", "html", "relative-path", "site-url"],
)
def test_links_into_other_pages_are_checked(tmp_path, target):
    write_docs(
        tmp_path,
        {
            "Page.md": f"[Elsewhere]({target})\n",
            "Other.md": "## Present\n",
            "Sub/Placeholder.md": "\n",
        },
    )
    [(path, line, _)] = broken(tmp_path)
    assert (path, line) == ("docs/Page.md", 1)


def test_links_into_other_pages_that_exist_are_fine(tmp_path):
    write_docs(
        tmp_path,
        {
            "Labs/Lab01/Page.md": "[Up](../../Other.html#present) [Site]("
            + SITE
            + "Other.html#present)\n",
            "Other.md": "## Present\n",
        },
    )
    assert broken(tmp_path) == []


def test_section_link_into_an_html_page_uses_its_ids(tmp_path):
    write_docs(
        tmp_path,
        {
            "Page.md": "[Ok](index.html#intro) [Bad](index.html#outro)\n",
            "index.html": '<html><body><h1 id="intro">Hi</h1></body></html>\n',
        },
    )
    [(_, _, message)] = broken(tmp_path)
    assert "#outro" in message


def test_folder_link_uses_its_readme_when_there_is_no_index(tmp_path):
    # GitHub Pages publishes a folder's README.md as the folder's index page
    write_docs(
        tmp_path,
        {
            "Page.md": "[Ok](Example/#usage) [Bad](Example/#missing)\n",
            "Example/README.md": "## Usage\n",
        },
    )
    [(_, _, message)] = broken(tmp_path)
    assert "#missing" in message


def test_repeated_headings_are_numbered(tmp_path):
    write_docs(
        tmp_path,
        {
            "Page.md": """
        [First](#notes) [Second](#notes-1) [Third](#notes-2)

        ## Notes
        ## Notes
    """
        },
    )
    [(_, _, message)] = broken(tmp_path)
    assert "#notes-2" in message


def test_explicit_ids_count(tmp_path):
    write_docs(
        tmp_path,
        {
            "Page.md": """
        [A](#custom) [B](#named) [C](#boxed)

        ## Heading with its own id {#custom}

        <a name="named"></a>
        <div id="boxed">x</div>
    """
        },
    )
    assert broken(tmp_path) == []


def test_top_and_bare_hash_always_exist(tmp_path):
    write_docs(tmp_path, {"Page.md": "[Top](#top) [Hash](#)\n"})
    assert broken(tmp_path) == []


def test_code_is_ignored(tmp_path):
    write_docs(
        tmp_path,
        {
            "Page.md": """
        Use `[x](#not-a-link)` in your notes.

        ```markdown
        [Example](#also-not-a-link)
        ## Not a heading
        ```

        [Real](#not-a-heading)
    """
        },
    )
    [(_, line, message)] = broken(tmp_path)
    assert line == 8
    assert "#not-a-heading" in message


def test_html_links_are_checked(tmp_path):
    write_docs(
        tmp_path,
        {
            "Page.md": """
        <a href="#missing">Jump</a>
    """
        },
    )
    [(_, line, _)] = broken(tmp_path)
    assert line == 1


@pytest.mark.parametrize(
    "target",
    [
        "Missing.md#x",
        "https://example.com/page#x",
        "mailto:someone@example.com",
        "../Outside.md#x",
    ],
    ids=["missing-page", "external", "mailto", "outside-docs"],
)
def test_links_this_check_does_not_own_are_ignored(tmp_path, target):
    write_docs(tmp_path, {"Page.md": f"[Link]({target})\n"})
    (tmp_path / "Outside.md").write_text("## Other\n", encoding="utf-8")
    assert broken(tmp_path) == []


def test_findings_are_in_file_and_line_order(tmp_path):
    write_docs(
        tmp_path,
        {
            "B.md": "[x](#b2)\n[x](#b1)\n",
            "A.md": "Intro\n[x](#a)\n",
        },
    )
    assert [(p, n) for p, n, _ in broken(tmp_path)] == [
        ("docs/A.md", 2),
        ("docs/B.md", 1),
        ("docs/B.md", 2),
    ]


def only_fix(root, site_url=SITE):
    [finding] = check_anchors(root, site_url)
    return finding.fix


def test_a_suggestion_comes_with_a_fix_to_the_same_page(tmp_path):
    root = write_docs(
        tmp_path,
        {"Page.md": "Intro\n\nSee [rules](#goalmdashrules).\n\n## Goal Rules\n"},
    )
    assert only_fix(root) == Fix(
        line=3,
        before="#goalmdashrules",
        after="#goal-rules",
        destination=Destination("docs/Page.md", 5, f"{SITE}Page.html#goal-rules"),
    )


def test_a_fix_to_another_page_keeps_the_path(tmp_path):
    root = write_docs(
        tmp_path,
        {
            "Page.md": "[x](Lessons/Other.md#setupp)\n",
            "Lessons/Other.md": "# Title\n\n## Setup\n",
        },
    )
    assert only_fix(root) == Fix(
        line=1,
        before="Lessons/Other.md#setupp",
        after="Lessons/Other.md#setup",
        destination=Destination(
            "docs/Lessons/Other.md", 3, f"{SITE}Lessons/Other.html#setup"
        ),
    )


def test_a_fix_into_a_folder_points_at_the_folders_address(tmp_path):
    root = write_docs(
        tmp_path,
        {"Page.md": "[x](Unit/#setupp)\n", "Unit/README.md": "## Setup\n"},
    )
    fix = only_fix(root)
    assert fix.after == "Unit/#setup"
    assert fix.destination == Destination(
        "docs/Unit/README.md", 1, f"{SITE}Unit/#setup"
    )


def test_a_full_site_link_is_fixed_in_place(tmp_path):
    root = write_docs(
        tmp_path,
        {"Page.md": f"[x]({SITE}Other.html#setupp)\n", "Other.md": "## Setup\n"},
    )
    fix = only_fix(root)
    assert (fix.before, fix.after) == (
        f"{SITE}Other.html#setupp",
        f"{SITE}Other.html#setup",
    )


def test_without_a_site_url_the_fix_has_no_address(tmp_path):
    root = write_docs(tmp_path, {"Page.md": "[x](#setupp)\n\n## Setup\n"})
    assert only_fix(root, site_url=None).destination == Destination(
        "docs/Page.md", 3, None
    )


def test_no_close_section_means_no_fix(tmp_path):
    root = write_docs(tmp_path, {"Page.md": "[x](#zzzzzz)\n\n## Setup\n"})
    assert only_fix(root) is None


def test_without_a_site_url_only_full_site_links_are_skipped(tmp_path):
    root = write_docs(
        tmp_path,
        {"Page.md": f"[Full]({SITE}Page.html#nowhere)\n[Relative](#nowhere)\n"},
    )
    assert [finding.line for finding in check_anchors(root, None)] == [2]


def test_no_docs_folder_means_no_findings(tmp_path):
    assert check_anchors(tmp_path, SITE) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
