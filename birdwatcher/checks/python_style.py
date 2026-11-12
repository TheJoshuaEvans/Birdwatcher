"""
Python style: Ruff over the course's Python files and notebooks, with the
course's own rules.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
import subprocess
from pathlib import Path

from ruff.__main__ import find_ruff_bin

from birdwatcher.core.course import site_folder
from birdwatcher.core.findings import Finding, Fix, Severity

CHECK = "python-style"
# The course's Ruff settings, the first that exists, relative to the repository
CONFIG_FILES = ("GradingAssistant/ruff.toml", "ruff.toml", ".ruff.toml")
RUFF_TIMEOUT = 120  # seconds
SYNTAX_ERROR = "invalid-syntax"  # Ruff's code for a syntax error (older versions: none)


class RuffError(RuntimeError):
    """Ruff could not check the files (for example, its settings are broken)."""


def check_python_style(repo_root):
    """
    Run Ruff over the .py files and Jupyter notebooks under docs/.

    Ruff uses the course's settings: the first of CONFIG_FILES that exists,
    for every file; without one, the settings Ruff finds itself (its
    defaults, or a pyproject.toml or ruff.toml near the files). Ruff keeps no
    cache in the course folder.

    Args:
        repo_root (Path): Root folder of the course repository.

    Returns:
        list[Finding]: One per problem Ruff reports, in file and line order.
            Correctness problems (pyflakes rules, codes starting "F") and
            syntax errors are warnings; everything else is info. The message
            starts with the rule's code ("F401: ...") or "Syntax error: ".
            In a .py file the finding has Ruff's line; when Ruff's fix is safe
            and changes only that line, it carries a Fix whose before is the
            whole line and whose after is the line as fixed. In a notebook the
            line is None and the message starts with "Cell <n>, line <m>: ",
            counting every cell from 1; notebook findings have no Fix.
            Empty when the repository has no docs/ folder.

    Raises:
        RuffError: Ruff failed to run, with what it said.
    """
    repo_root = Path(repo_root).resolve()
    docs = site_folder(repo_root)
    if not docs.is_dir():
        return []
    command = [find_ruff_bin(), "check", "--output-format", "json", "--no-cache"]
    config = next(
        (repo_root / name for name in CONFIG_FILES if (repo_root / name).is_file()),
        None,
    )
    if config is not None:
        command += ["--config", str(config)]
    # --exit-zero: problems found still exit 0, so any other exit is a failure
    command += ["--exit-zero", str(docs)]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUFF_TIMEOUT,
            check=False,
            cwd=repo_root,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuffError(f"Ruff could not run: {error}") from error
    if result.returncode != 0:
        raise RuffError(f"Ruff failed: {result.stderr.strip()}")
    findings = [
        _finding(problem, repo_root) for problem in json.loads(result.stdout or "[]")
    ]
    return sorted(
        findings,
        key=lambda f: (f.path, -1 if f.line is None else f.line),
    )


def _finding(problem, repo_root):
    """A finding for one entry of Ruff's JSON output."""
    file = Path(problem["filename"]).resolve()
    path = file.relative_to(repo_root).as_posix()
    code = problem.get("code")
    if code == SYNTAX_ERROR:
        code = None
    row = problem["location"]["row"]
    label = f"{code}: " if code else "Syntax error: "
    severity = (
        Severity.WARNING if code is None or code.startswith("F") else Severity.INFO
    )
    cell = problem.get("cell")
    if cell is not None:
        message = f"Cell {cell}, line {row}: {label}{problem['message']}"
        return Finding(CHECK, severity, path, None, message)
    return Finding(
        CHECK, severity, path, row, label + problem["message"], _fix(problem, file, row)
    )


def _fix(problem, file, row):
    """Ruff's fix as a one-line Fix, when it is safe and changes only that line."""
    fix = problem.get("fix")
    if not fix or fix.get("applicability") != "safe":
        return None
    edits = fix["edits"]
    if not edits or any(
        edit["location"]["row"] != row
        or edit["end_location"]["row"] != row
        or "\n" in edit["content"]
        or "\r" in edit["content"]
        for edit in edits
    ):
        return None
    lines = file.read_bytes().decode("utf-8", errors="replace").split("\n")
    if row > len(lines):
        return None
    before = lines[row - 1].removesuffix("\r")
    after = before
    # Ruff's columns count characters from 1; apply the edits right to left.
    for edit in sorted(edits, key=lambda e: e["location"]["column"], reverse=True):
        start = edit["location"]["column"] - 1
        end = edit["end_location"]["column"] - 1
        after = after[:start] + edit["content"] + after[end:]
    return None if after == before else Fix(row, before, after)
