"""
The course's own words for the spelling check, kept in its cspell config (the
format VS Code's Code Spell Checker reads), so words added in either tool
count in both.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
import os
from pathlib import Path

# cspell's own config file names at a project's root, in the order it looks
CONFIG_NAMES = ("cspell.json", ".cspell.json", "cSpell.json", "cspell.config.json")
NEW_CONFIG = {"version": "0.2", "language": "en"}  # a new file's other settings


class DictionaryError(Exception):
    """The course's cspell config exists but cannot be read as a JSON object
    (for example, it has comments), so Birdwatcher will not rewrite it."""


def config_path(repo_root):
    """
    The course's cspell config.

    Args:
        repo_root (Path): The course repository's root folder.

    Returns:
        Path: The first of CONFIG_NAMES that exists there, or cspell.json
            when none does.
    """
    root = Path(repo_root)
    return next(
        (root / name for name in CONFIG_NAMES if (root / name).is_file()),
        root / CONFIG_NAMES[0],
    )


def _read(path):
    """The config as a dict ({} when the file is missing)."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise DictionaryError(f"{path.name} cannot be read: {error}") from error
    if not isinstance(data, dict):
        raise DictionaryError(f"{path.name} is not a JSON object.")
    return data


def _listed(data, key):
    entries = data.get(key, [])
    return (
        [entry for entry in entries if isinstance(entry, str)]
        if isinstance(entries, list)
        else []
    )


def course_words(repo_root):
    """
    The course's own words: the config's "words" and "ignoreWords".

    Args:
        repo_root (Path): The course repository's root folder.

    Returns:
        frozenset[str]: The words, lowercased; empty when there is no config
            or it cannot be read.
    """
    try:
        data = _read(config_path(repo_root))
    except DictionaryError:
        return frozenset()
    return frozenset(
        word.lower() for key in ("words", "ignoreWords") for word in _listed(data, key)
    )


def add_words(repo_root, words):
    """
    Add words to the course's "words" list.

    The config keeps its other settings. The list stays sorted (ignoring
    case) and holds each word once: a word already there in any letter case
    is not added again. With no config, cspell.json is created with
    NEW_CONFIG's settings. The file is written as JSON indented by two spaces
    with a final newline, through a temporary file.

    Args:
        repo_root (Path): The course repository's root folder.
        words (Iterable[str]): The words to add.

    Returns:
        Path: The config file written.

    Raises:
        DictionaryError: The config exists but cannot be read; it is left
            unchanged.
    """
    path = config_path(repo_root)
    data = _read(path) if path.is_file() else dict(NEW_CONFIG)
    listed = _listed(data, "words")
    known = {word.lower() for word in listed}
    for word in words:
        if word.lower() not in known:
            listed.append(word)
            known.add(word.lower())
    data["words"] = sorted(listed, key=lambda word: (word.lower(), word))
    temporary = path.with_name(path.name + ".birdwatcher-tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return path
