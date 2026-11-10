"""
Birdwatcher's saved settings: a small JSON file in the user's config folder.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
from dataclasses import dataclass, replace
from pathlib import Path

from platformdirs import user_config_dir

CONFIG_FILE = "config.json"
COURSE_DIR_KEY = "course_dir"
EDITOR_KEY = "editor"
RECENT_KEY = "recent"
DEFAULT_EDITOR = "vscode"
THEME_KEY = "theme"
THEME_AUTO = "auto"  # follow the system's light or dark mode
RECENT_LIMIT = 5  # course folders remembered for quick switching


@dataclass(frozen=True)
class Config:
    """
    Birdwatcher's settings.

    Attributes:
        course_dir (Path): The local clone of the course repository to check.
        editor (str): Which editor opens files (an id the user interface
            understands, such as "vscode").
        recent (tuple[Path, ...]): Course folders used lately, most recent
            first.
        theme (str): The color theme's name, or THEME_AUTO to follow the
            system's light or dark mode.
    """

    course_dir: Path
    editor: str = DEFAULT_EDITOR
    recent: tuple[Path, ...] = ()
    theme: str = THEME_AUTO


def with_course(config, course_dir):
    """
    The settings with another course folder chosen.

    Args:
        config (Config): The current settings.
        course_dir (Path): The chosen course folder.

    Returns:
        Config: The same settings with course_dir set and the folder first in
            the recent list; the list holds no folder twice (the same folder
            spelled differently counts once) and at most RECENT_LIMIT.
    """
    chosen = Path(course_dir).resolve()
    others = [path for path in config.recent if Path(path).resolve() != chosen]
    recent = (Path(course_dir), *others)[:RECENT_LIMIT]
    return replace(config, course_dir=Path(course_dir), recent=recent)


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
            has no readable course folder (it is then treated as not set up).
            A missing or unreadable editor is DEFAULT_EDITOR, and a missing
            or unreadable theme is THEME_AUTO; unreadable
            recent entries are left out, and a file from before the recent
            list existed (no "recent" key) gets one holding just the course
            folder.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    course_dir = data.get(COURSE_DIR_KEY) if isinstance(data, dict) else None
    if not isinstance(course_dir, str):
        return None
    editor = data.get(EDITOR_KEY)
    listed = data.get(RECENT_KEY, [course_dir])
    recent = tuple(
        Path(entry)
        for entry in (listed if isinstance(listed, list) else [])
        if isinstance(entry, str)
    )
    theme = data.get(THEME_KEY)
    return Config(
        course_dir=Path(course_dir),
        editor=editor if isinstance(editor, str) else DEFAULT_EDITOR,
        recent=recent,
        theme=theme if isinstance(theme, str) else THEME_AUTO,
    )


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
    data = {
        COURSE_DIR_KEY: str(config.course_dir),
        EDITOR_KEY: config.editor,
        RECENT_KEY: [str(folder) for folder in config.recent],
        THEME_KEY: config.theme,
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
