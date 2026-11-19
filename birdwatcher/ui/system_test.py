"""
Contract tests for birdwatcher.ui.system. Opening VS Code and the folder picker
are desktop side effects, checked by hand; the app's tests use fakes for them.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys
from pathlib import PurePosixPath, PureWindowsPath

import keyring
import keyring.backend
import keyring.errors
import pytest

from birdwatcher.ui.system import (
    DEFAULT_APP,
    KEYRING_SERVICE,
    TYPORA,
    VSCODE,
    desktop_editors,
    editor_url,
    system_key_store,
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


class MemoryKeyring(keyring.backend.KeyringBackend):
    """A keyring held in memory; `broken` makes every call fail as a keyring
    without a usable backend does."""

    priority = 1

    def __init__(self, broken=False):
        super().__init__()
        self.entries = {}
        self.broken = broken

    def _check(self):
        if self.broken:
            raise keyring.errors.KeyringError("no keyring here")

    def get_password(self, service, username):
        self._check()
        return self.entries.get((service, username))

    def set_password(self, service, username, password):
        self._check()
        self.entries[(service, username)] = password

    def delete_password(self, service, username):
        self._check()
        if (service, username) not in self.entries:
            raise keyring.errors.PasswordDeleteError("not found")
        del self.entries[(service, username)]


@pytest.fixture
def memory_keyring():
    """Swaps the system keyring for one in memory, so tests never touch the
    real one."""
    real = keyring.get_keyring()
    memory = MemoryKeyring()
    keyring.set_keyring(memory)
    yield memory
    keyring.set_keyring(real)


def test_keys_are_saved_read_and_forgotten_per_provider(memory_keyring):
    store = system_key_store()
    assert store.get("openrouter") is None
    store.set("openrouter", "sk-or-1")
    store.set("gemini", "AIza-2")
    assert store.get("openrouter") == "sk-or-1"
    assert memory_keyring.entries[(KEYRING_SERVICE, "openrouter")] == "sk-or-1"
    store.delete("openrouter")
    assert store.get("openrouter") is None
    assert store.get("gemini") == "AIza-2"


def test_forgetting_a_key_that_is_not_there_is_fine(memory_keyring):
    system_key_store().delete("openrouter")


def test_a_broken_keyring_reads_as_empty_and_refuses_to_save(memory_keyring):
    memory_keyring.broken = True
    store = system_key_store()
    assert store.get("openrouter") is None
    store.delete("openrouter")
    with pytest.raises(OSError, match="no keyring here"):
        store.set("openrouter", "sk-or-1")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
