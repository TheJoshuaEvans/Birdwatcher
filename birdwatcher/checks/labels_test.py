"""
Contract tests for birdwatcher.checks.labels. Pages are shaped like the real
CS 212 lab pages.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.checks.labels import CHECK, check_labels
from birdwatcher.core.findings import Edit, Fix, Severity
from birdwatcher.core.fixes import apply_fix


def write_page(root, text, name="Lab05.md"):
    page = root / "docs" / name
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(text, encoding="utf-8")
    return page


def test_a_label_right_above_a_code_block_is_reported_with_a_fix(tmp_path):
    write_page(tmp_path, "Run this:\n\nPython\n```python\nprint(1)\n```\n")
    [finding] = check_labels(tmp_path)
    assert (finding.check, finding.severity, finding.path, finding.line) == (
        CHECK,
        Severity.WARNING,
        "docs/Lab05.md",
        3,
    )
    assert "Python" in finding.message
    assert finding.fix == Fix(line=3, before="Python", after="")


@pytest.mark.parametrize(
    ("text", "fence_line", "fence", "tagged"),
    [
        ("Python\n```\nx = 1\n```\n", 2, "```", "```python"),
        ("Bash\n\n\n````\nls\n````\n", 4, "````", "````bash"),
        ("PowerShell\n  ~~~\ndir\n  ~~~\n", 2, "~~~", "~~~powershell"),
        ("C#\n```\nx;\n```\n", 2, "```", "```csharp"),
        ("Terminal\n```\n$ ls\n```\n", 2, "```", "```console"),
        ("Output\n```\n42\n```\n", 2, "```", "```text"),
    ],
    ids=["python", "longer-fence", "tilde-indented", "c-sharp", "terminal", "output"],
)
def test_a_label_above_a_bare_fence_moves_onto_the_fence(
    tmp_path, text, fence_line, fence, tagged
):
    write_page(tmp_path, text)
    [finding] = check_labels(tmp_path)
    label = text.split("\n")[0].strip()
    assert finding.fix == Fix(
        line=1, before=label, after="", also=(Edit(fence_line, fence, tagged),)
    )
    assert "highlight" in finding.message


def test_moving_the_label_gives_the_block_its_language(tmp_path):
    page = write_page(tmp_path, "")
    page.write_bytes(b"Intro\r\nPython\r\n```\r\nx = 1\r\n```\r\n")
    [finding] = check_labels(tmp_path)
    apply_fix(page, finding.fix)
    assert page.read_bytes() == b"Intro\r\n\r\n```python\r\nx = 1\r\n```\r\n"


def test_blank_lines_between_label_and_code_block_still_count(tmp_path):
    write_page(tmp_path, "Python\n\n\n```\nx = 1\n```\n")
    assert [f.line for f in check_labels(tmp_path)] == [1]


@pytest.mark.parametrize(
    "label", ["python", "  Python  ", "Bash", "C#", "PowerShell", "Output"]
)
def test_other_spellings_and_languages_count(tmp_path, label):
    write_page(tmp_path, f"{label}\n```\nx\n```\n")
    assert len(check_labels(tmp_path)) == 1


@pytest.mark.parametrize(
    "text",
    [
        "Python\n\nPython is a language.\n```\nx\n```\n",
        "Python is great\n```\nx\n```\n",
        "```\nPython\n```\n",
        "---\ntitle: Python\n---\n```\nx\n```\n",
        "Python\n",
    ],
    ids=["prose-between", "sentence", "inside-code", "front-matter", "no-code-block"],
)
def test_other_lines_are_not_labels(tmp_path, text):
    write_page(tmp_path, text)
    assert check_labels(tmp_path) == []


def test_the_fix_empties_the_line_and_keeps_the_rest(tmp_path):
    page = write_page(tmp_path, "")
    # Bytes, so Windows' text mode doesn't add a second \r to each line ending.
    page.write_bytes(b"Intro\r\nPython\r\n```python\r\nx = 1\r\n```\r\n")
    [finding] = check_labels(tmp_path)
    apply_fix(page, finding.fix)
    assert page.read_bytes() == b"Intro\r\n\r\n```python\r\nx = 1\r\n```\r\n"


def test_no_docs_folder_means_no_findings(tmp_path):
    assert check_labels(tmp_path) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
