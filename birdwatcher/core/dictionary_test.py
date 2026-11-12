"""
Contract tests for birdwatcher.core.dictionary.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
import sys

import pytest

from birdwatcher.core.dictionary import (
    DictionaryError,
    add_words,
    config_path,
    course_words,
    ignore_paths,
    is_ignored,
)


def test_without_a_config_there_are_no_words(tmp_path):
    assert course_words(tmp_path) == frozenset()
    assert config_path(tmp_path) == tmp_path / "cspell.json"


def test_adding_words_creates_a_cspell_config(tmp_path):
    written = add_words(tmp_path, ["Keras", "jupyter"])
    assert written == tmp_path / "cspell.json"
    text = written.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == {
        "version": "0.2",
        "language": "en",
        "words": ["jupyter", "Keras"],
    }
    assert course_words(tmp_path) == {"keras", "jupyter"}


def test_adding_keeps_other_settings_and_one_sorted_copy_of_each_word(tmp_path):
    config = tmp_path / "cspell.json"
    config.write_text(
        json.dumps(
            {"language": "en", "ignorePaths": ["build"], "words": ["zeta", "Alpha"]}
        ),
        encoding="utf-8",
    )
    add_words(tmp_path, ["alpha", "beta", "Beta", "colab"])
    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["ignorePaths"] == ["build"]
    assert data["words"] == ["Alpha", "beta", "colab", "zeta"]


def test_ignore_paths_are_read_from_the_config(tmp_path):
    assert ignore_paths(tmp_path) == ()
    (tmp_path / "cspell.json").write_text(
        json.dumps({"ignorePaths": ["**/ace-builds/**", 7, "Drafts"]}), encoding="utf-8"
    )
    assert ignore_paths(tmp_path) == ("**/ace-builds/**", "Drafts")


@pytest.mark.parametrize(
    ("pattern", "path", "ignored"),
    [
        ("**/ace-builds/**", "docs/Lessons/ace-builds/src/a.js", True),
        ("**/ace-builds/**", "docs/Lessons/ace-builder.js", False),
        ("Drafts", "docs/Drafts/Old.md", True),  # a bare name: any folder or file
        ("Drafts", "docs/MyDrafts/Old.md", False),
        ("docs/*.css", "docs/site.css", True),
        ("*.map", "docs/js/app.js.map", True),
    ],
)
def test_ignored_matches_paths_like_cspell(pattern, path, ignored):
    assert is_ignored(path, (pattern,)) is ignored


def test_ignore_words_count_as_course_words(tmp_path):
    (tmp_path / "cspell.json").write_text(
        json.dumps({"words": ["Colab"], "ignoreWords": ["Hte"]}), encoding="utf-8"
    )
    assert course_words(tmp_path) == {"colab", "hte"}


def test_another_cspell_file_name_is_found_and_written(tmp_path):
    hidden = tmp_path / ".cspell.json"
    hidden.write_text(json.dumps({"words": ["numpy"]}), encoding="utf-8")
    assert config_path(tmp_path) == hidden
    add_words(tmp_path, ["pandas"])
    assert course_words(tmp_path) == {"numpy", "pandas"}
    assert not (tmp_path / "cspell.json").exists()


@pytest.mark.parametrize(
    "text", ['{"words": ["a"], // a comment\n}', "[1, 2]", "not json"]
)
def test_an_unreadable_config_is_never_rewritten(tmp_path, text):
    config = tmp_path / "cspell.json"
    config.write_text(text, encoding="utf-8")
    assert course_words(tmp_path) == frozenset()
    with pytest.raises(DictionaryError):
        add_words(tmp_path, ["word"])
    assert config.read_text(encoding="utf-8") == text


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
