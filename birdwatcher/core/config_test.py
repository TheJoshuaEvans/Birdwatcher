"""
Contract tests for birdwatcher.core.config.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys
from pathlib import Path

import pytest

from birdwatcher.core.config import (
    DEFAULT_EDITOR,
    DEFAULT_SPLIT,
    RECENT_LIMIT,
    THEME_AUTO,
    Config,
    default_config_path,
    load_config,
    save_config,
    with_course,
)


def test_saved_settings_load_back(tmp_path):
    path = tmp_path / "config.json"
    save_config(path, Config(course_dir=Path(r"C:\courses\CS212 Materials")))
    assert load_config(path) == Config(course_dir=Path(r"C:\courses\CS212 Materials"))


def test_saving_creates_the_folder_and_replaces_earlier_settings(tmp_path):
    path = tmp_path / "new" / "folder" / "config.json"
    save_config(path, Config(course_dir=Path("first")))
    save_config(path, Config(course_dir=Path("second")))
    assert load_config(path) == Config(course_dir=Path("second"))


def test_missing_file_means_not_set_up(tmp_path):
    assert load_config(tmp_path / "config.json") is None


@pytest.mark.parametrize(
    "content",
    ["", "not json", "[]", '{"other": 1}', '{"course_dir": 5}'],
    ids=["empty", "not-json", "not-an-object", "no-course-dir", "wrong-type"],
)
def test_unreadable_settings_mean_not_set_up(tmp_path, content):
    path = tmp_path / "config.json"
    path.write_text(content, encoding="utf-8")
    assert load_config(path) is None


def test_editor_and_recent_courses_load_back(tmp_path):
    path = tmp_path / "config.json"
    config = Config(
        course_dir=Path("a"), editor="typora", recent=(Path("a"), Path("b"))
    )
    save_config(path, config)
    assert load_config(path) == config


def test_older_settings_without_editor_or_recent_still_load(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"course_dir": "C:/courses/CS212"}', encoding="utf-8")
    config = load_config(path)
    assert config.course_dir == Path("C:/courses/CS212")
    assert config.editor == DEFAULT_EDITOR
    assert config.recent == (Path("C:/courses/CS212"),)


def test_unreadable_editor_or_recent_fall_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        '{"course_dir": "a", "editor": 5, "recent": ["b", 7, null]}', encoding="utf-8"
    )
    config = load_config(path)
    assert config.editor == DEFAULT_EDITOR
    assert config.recent == (Path("b"),)


def test_choosing_a_course_puts_it_first_in_the_recent_list(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    config = Config(course_dir=first, recent=(first,))
    config = with_course(config, second)
    assert config.course_dir == second
    assert config.recent == (second, first)
    config = with_course(config, first)
    assert config.recent == (first, second)


def test_the_same_folder_spelled_differently_is_listed_once(tmp_path, monkeypatch):
    (tmp_path / "course").mkdir()
    monkeypatch.chdir(tmp_path)
    config = Config(course_dir=tmp_path / "course", recent=(tmp_path / "course",))
    assert with_course(config, Path("course")).recent == (Path("course"),)


def test_the_recent_list_keeps_only_the_latest(tmp_path):
    config = Config(course_dir=tmp_path)
    for number in range(RECENT_LIMIT + 2):
        config = with_course(config, tmp_path / str(number))
    assert len(config.recent) == RECENT_LIMIT
    assert config.recent[0] == tmp_path / str(RECENT_LIMIT + 1)


def test_choosing_a_course_keeps_the_editor(tmp_path):
    config = Config(course_dir=tmp_path, editor="typora")
    assert with_course(config, tmp_path / "other").editor == "typora"


def test_the_theme_loads_back_and_defaults_to_auto(tmp_path):
    path = tmp_path / "config.json"
    assert Config(course_dir=Path("a")).theme == THEME_AUTO
    save_config(path, Config(course_dir=Path("a"), theme="nord"))
    assert load_config(path).theme == "nord"


def test_older_settings_without_a_theme_match_the_system(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"course_dir": "a", "theme": 3}', encoding="utf-8")
    assert load_config(path).theme == THEME_AUTO


def test_the_split_loads_back_and_defaults_to_half(tmp_path):
    path = tmp_path / "config.json"
    assert Config(course_dir=Path("a")).split == DEFAULT_SPLIT
    save_config(path, Config(course_dir=Path("a"), split=35))
    assert load_config(path).split == 35


@pytest.mark.parametrize("stored", ["3", "true", "5", "95", '"wide"'])
def test_a_split_that_is_not_a_sensible_percentage_is_the_default(tmp_path, stored):
    path = tmp_path / "config.json"
    path.write_text(f'{{"course_dir": "a", "split": {stored}}}', encoding="utf-8")
    assert load_config(path).split == DEFAULT_SPLIT


def test_default_path_is_a_json_file_named_for_birdwatcher():
    path = default_config_path()
    assert path.name == "config.json"
    assert "birdwatcher" in str(path).lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
