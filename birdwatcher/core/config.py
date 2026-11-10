"""
Birdwatcher's saved settings: a small JSON file in the user's config folder.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_dir

CONFIG_FILE = "config.json"
COURSE_DIR_KEY = "course_dir"


@dataclass(frozen=True)
class Config:
    """
    Birdwatcher's settings.

    Attributes:
        course_dir (Path): The local clone of the course repository to check.
    """

    course_dir: Path


def default_config_path():
    """
    Where the settings are kept for the current user.

    Returns:
        Path: config.json in the user's config folder for Birdwatcher (on
            Windows, under %LOCALAPPDATA%).
    """
    return Path(user_config_dir("birdwatcher", appauthor=False)) / CONFIG_FILE


def load_config(path):
    """
    Read saved settings.

    Args:
        path (Path): The settings file.

    Returns:
        Config | None: The settings, or None when the file does not exist or
            cannot be read as settings (it is then treated as not set up).
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    course_dir = data.get(COURSE_DIR_KEY) if isinstance(data, dict) else None
    if not isinstance(course_dir, str):
        return None
    return Config(course_dir=Path(course_dir))


def save_config(path, config):
    """
    Save settings, creating the file's folder if needed and replacing any
    earlier settings.

    Args:
        path (Path): The settings file.
        config (Config): The settings to save.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {COURSE_DIR_KEY: str(config.course_dir)}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
