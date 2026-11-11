"""
Contract tests for birdwatcher.checks.pages.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.checks.pages import (
    CODE,
    FENCE,
    FRONT,
    TEXT,
    front_matter,
    line_kinds,
    prose_lines,
    read_page,
    site_pages,
)

PAGE = """---
title: "Lab 5: ANNs"
author: Brian Bird
---
<h1>Lab 5</h1>
Python
```python
x = 1
```
Done.
"""


def test_site_pages_skip_jekyll_and_hidden_folders(tmp_path):
    for path in ("A.md", "Labs/B.md", "_includes/C.md", ".github/D.md", "Labs/x.txt"):
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("", encoding="utf-8")
    assert [p.relative_to(tmp_path).as_posix() for p in site_pages(tmp_path)] == [
        "A.md",
        "Labs/B.md",
    ]


def test_read_page_uses_newlines_only(tmp_path):
    page = tmp_path / "A.md"
    page.write_bytes(b"one\r\ntwo\r\n")
    assert read_page(page) == "one\ntwo\n"


def test_line_kinds_tell_front_matter_fences_code_and_text_apart():
    kinds = [kind for kind, _ in line_kinds(PAGE)]
    assert kinds == [FRONT] * 4 + [TEXT, TEXT, FENCE, CODE, FENCE, TEXT, TEXT]


def test_an_unclosed_fence_runs_to_the_end():
    kinds = [kind for kind, _ in line_kinds("text\n```\ncode\nmore")]
    assert kinds == [TEXT, FENCE, CODE, CODE]


def test_a_longer_fence_needs_a_matching_closer():
    kinds = [kind for kind, _ in line_kinds("````\n```\nstill code\n````\nprose")]
    assert kinds == [FENCE, CODE, CODE, FENCE, TEXT]


def test_prose_lines_keep_line_numbers():
    lines = prose_lines(PAGE)
    assert len(lines) == PAGE.count("\n") + 1
    assert lines[4] == "<h1>Lab 5</h1>" and lines[7] == "" and lines[9] == "Done."


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (PAGE, {"title": '"Lab 5: ANNs"', "author": "Brian Bird"}),
        ("---\n---\nbody", {}),
        ("no front matter\n---\n", None),
        ("---\ntitle: A\n  nested: x\n- item\n---\n", {"title": "A"}),
    ],
    ids=["keys", "empty-block", "none", "nested-ignored"],
)
def test_front_matter_reads_top_level_keys(text, expected):
    assert front_matter(text) == expected


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
