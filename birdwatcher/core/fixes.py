"""
Applying and undoing fixes in course files.

A fix edits one line of one file and nothing else: the file keeps its
encoding (UTF-8), its line endings and every other character.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import os
from pathlib import Path


class FixError(Exception):
    """A fix (or its undo) cannot be applied because the file has changed: the
    line is gone or no longer holds the expected text. The message says which."""


def apply_fix(file, fix):
    """
    Apply a fix: replace the first occurrence of fix.before on fix.line with
    fix.after, and likewise for each edit in fix.also. Every line is checked
    before any is changed, so a fix applies wholly or not at all.

    Args:
        file (Path): The finding's file.
        fix (Fix): The fix.

    Raises:
        FixError: The file has no such line, or the line does not contain
            fix.before. The file is then left unchanged.
    """
    _replace_lines(Path(file), _edits(fix))


def undo_fix(file, fix):
    """
    Undo a fix: replace the first occurrence of fix.after on fix.line with
    fix.before, and likewise for each edit in fix.also, wholly or not at all.

    Args:
        file (Path): The finding's file.
        fix (Fix): The fix that was applied.

    Raises:
        FixError: The file has no such line, or the line does not contain
            fix.after (it changed since the fix). The file is then left
            unchanged.
    """
    _replace_lines(Path(file), _edits(fix, undo=True))


def _edits(fix, undo=False):
    """A fix's (line, old, new) replacements: its own line, then `also`;
    undoing swaps old and new."""
    edits = [(fix.line, fix.before, fix.after)]
    edits += [(edit.line, edit.before, edit.after) for edit in fix.also]
    return [(line, new, old) for line, old, new in edits] if undo else edits


def _replace_lines(file, edits):
    # Bytes in and out, so line endings and encoding come back exactly as found.
    # Lines are split on "\n" only (as the checks count them): splitlines()
    # would also split on form feeds and Unicode line separators.
    lines = file.read_bytes().decode("utf-8").split("\n")
    # Every line is checked before any is changed: all or nothing.
    for line, old, _ in edits:
        if not 1 <= line <= len(lines):
            raise FixError(f"{file.name} has no line {line} any more.")
        if old not in lines[line - 1]:
            raise FixError(f"Line {line} of {file.name} no longer contains '{old}'.")
    for line, old, new in edits:
        lines[line - 1] = lines[line - 1].replace(old, new, 1)
    # Write beside the file, then swap it in, so a failure never leaves half a file.
    temporary = file.with_name(f".{file.name}.birdwatcher-fix")
    temporary.write_bytes("\n".join(lines).encode("utf-8"))
    os.replace(temporary, file)
