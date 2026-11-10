"""
Contract tests for birdwatcher.config.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys
from pathlib import Path

import pytest

from birdwatcher.config import Config, default_config_path, load_config, save_config


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


def test_default_path_is_a_json_file_named_for_birdwatcher():
    path = default_config_path()
    assert path.name == "config.json"
    assert "birdwatcher" in str(path).lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
