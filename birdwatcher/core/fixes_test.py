"""
Contract tests for birdwatcher.core.fixes.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.core.findings import Edit, Fix
from birdwatcher.core.fixes import FixError, apply_fix, undo_fix

ORIGINAL = "# Café\r\n[a](#bad) and [b](#bad)\r\n[c](#bad)\r\nlast line, no newline"
FIX = Fix(line=2, before="#bad", after="#good")


def write(tmp_path, text=ORIGINAL):
    file = tmp_path / "Page.md"
    file.write_bytes(text.encode("utf-8"))
    return file


def test_apply_replaces_the_first_occurrence_on_that_line_only(tmp_path):
    file = write(tmp_path)
    apply_fix(file, FIX)
    expected = ORIGINAL.replace("[a](#bad)", "[a](#good)")
    assert file.read_bytes() == expected.encode("utf-8")


def test_lines_are_counted_by_newlines_only(tmp_path):
    # A Unicode line separator inside a line must not shift the line count.
    file = write(tmp_path, "intro still line one\n[a](#bad)\n")
    apply_fix(file, Fix(line=2, before="#bad", after="#good"))
    assert file.read_text(encoding="utf-8") == "intro still line one\n[a](#good)\n"


def test_undo_restores_the_file_exactly(tmp_path):
    file = write(tmp_path)
    apply_fix(file, FIX)
    undo_fix(file, FIX)
    assert file.read_bytes() == ORIGINAL.encode("utf-8")


@pytest.mark.parametrize(
    ("fix", "where"),
    [
        (Fix(line=9, before="#bad", after="#good"), "9"),
        (Fix(line=1, before="#bad", after="#good"), "#bad"),
    ],
    ids=["no-such-line", "text-not-on-line"],
)
def test_apply_refuses_when_the_file_has_changed(tmp_path, fix, where):
    file = write(tmp_path)
    with pytest.raises(FixError, match=where):
        apply_fix(file, fix)
    assert file.read_bytes() == ORIGINAL.encode("utf-8")


def test_undo_refuses_when_the_line_changed_since_the_fix(tmp_path):
    file = write(tmp_path)
    with pytest.raises(FixError, match="#good"):
        undo_fix(file, FIX)
    assert file.read_bytes() == ORIGINAL.encode("utf-8")


TWO_LINES = Fix(1, "Python", "", also=(Edit(3, "```", "```python"),))


def test_a_fix_with_further_edits_changes_every_line(tmp_path):
    file = tmp_path / "Page.md"
    file.write_bytes(b"Python\r\n\r\n```\r\nx = 1\r\n```\r\n")
    apply_fix(file, TWO_LINES)
    assert file.read_bytes() == b"\r\n\r\n```python\r\nx = 1\r\n```\r\n"
    undo_fix(file, TWO_LINES)
    assert file.read_bytes() == b"Python\r\n\r\n```\r\nx = 1\r\n```\r\n"


def test_a_fix_with_further_edits_is_all_or_nothing(tmp_path):
    file = tmp_path / "Page.md"
    original = b"Python\n\n~~~\nx = 1\n~~~\n"  # line 3 no longer holds ```
    file.write_bytes(original)
    with pytest.raises(FixError):
        apply_fix(file, TWO_LINES)
    assert file.read_bytes() == original


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
