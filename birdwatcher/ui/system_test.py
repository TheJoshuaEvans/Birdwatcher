"""
Contract tests for birdwatcher.ui.system. Opening VS Code and the folder picker
are desktop side effects, checked by hand; the app's tests use fakes for them.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from birdwatcher.ui.system import editor_url

COURSE = PureWindowsPath(r"C:\courses\CS212")  # behaves the same on every OS


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (3, "vscode://file/C:/courses/CS212/docs/A.md:3"),
        (None, "vscode://file/C:/courses/CS212/docs/A.md"),
    ],
    ids=["with-line", "whole-file"],
)
def test_editor_url_opens_vscode_at_the_line(line, expected):
    assert editor_url(COURSE / "docs" / "A.md", line) == expected


def test_editor_url_encodes_spaces_and_hashes():
    url = editor_url(PureWindowsPath(r"C:\Lesson Plans\Week #1.md"), 2)
    assert url == "vscode://file/C:/Lesson%20Plans/Week%20%231.md:2"


def test_editor_url_for_a_mac_path():
    url = editor_url(PurePosixPath("/Users/brian/CS212/docs/A.md"), 4)
    assert url == "vscode://file/Users/brian/CS212/docs/A.md:4"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
