"""
Contract tests for birdwatcher.ui.system. Opening VS Code and the folder picker
are desktop side effects, checked by hand; the app's tests use fakes for them.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from birdwatcher.ui.system import (
    DEFAULT_APP,
    TYPORA,
    VSCODE,
    desktop_editors,
    editor_url,
    system_prefers_dark,
)

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


def test_the_editors_on_offer_in_order():
    editors = desktop_editors()
    assert list(editors) == [VSCODE, TYPORA, DEFAULT_APP]
    assert all(editor.id == key for key, editor in editors.items())


def test_only_vscode_opens_at_the_line():
    editors = desktop_editors()
    assert [e.id for e in editors.values() if e.opens_at_line] == [VSCODE]


def test_the_default_app_is_always_available():
    assert desktop_editors()[DEFAULT_APP].available


def test_the_system_mode_is_an_answer_or_unknown():
    assert system_prefers_dark() in (True, False, None)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
