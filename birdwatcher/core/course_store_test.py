"""
Contract tests for birdwatcher.core.course_store.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.core.course_store import read_entries, write_entries


def test_written_entries_read_back(tmp_path):
    store = tmp_path / "settings" / "store.json"
    write_entries(store, tmp_path / "course", [{"a": 1}, "two", 3])
    assert read_entries(store, tmp_path / "course") == [{"a": 1}, "two", 3]


def test_each_folder_keeps_its_own_entries(tmp_path):
    store = tmp_path / "store.json"
    write_entries(store, tmp_path / "first", [1])
    write_entries(store, tmp_path / "second", [2])
    write_entries(store, tmp_path / "first", [])
    assert read_entries(store, tmp_path / "first") == []
    assert read_entries(store, tmp_path / "second") == [2]


def test_the_same_folder_spelled_differently_is_the_same(tmp_path, monkeypatch):
    store = tmp_path / "store.json"
    (tmp_path / "course").mkdir()
    monkeypatch.chdir(tmp_path)
    write_entries(store, tmp_path / "course", [1])
    assert read_entries(store, "course") == [1]


@pytest.mark.parametrize("content", [None, "", "not json", "[]", '{"x": 5}'])
def test_missing_or_unreadable_files_hold_nothing(tmp_path, content):
    store = tmp_path / "store.json"
    if content is not None:
        store.write_text(content, encoding="utf-8")
    assert read_entries(store, tmp_path) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
