"""
Contract tests for birdwatcher.checks.python_style. They run the real Ruff,
over small courses made for each test.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
import sys

import pytest

from birdwatcher.checks.python_style import CHECK, RuffError, check_python_style
from birdwatcher.core.findings import Severity

RULES = '[lint]\nselect = ["E", "W", "F", "I"]\n'


def course(root, config=RULES, where="GradingAssistant/ruff.toml"):
    """A course folder with the given Ruff settings (none when config is None)."""
    (root / "docs").mkdir(parents=True, exist_ok=True)
    if config is not None:
        (root / where).parent.mkdir(parents=True, exist_ok=True)
        (root / where).write_text(config, encoding="utf-8")
    return root


def write(root, path, text, newline="\n"):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(text.replace("\n", newline).encode("utf-8"))


def only(findings, code):
    return [f for f in findings if f.message.startswith(f"{code}:")]


def test_findings_name_the_rule_and_the_line(tmp_path):
    course(tmp_path)
    write(tmp_path, "docs/lab.py", "import os\n\nx = 1\n")
    [finding] = check_python_style(tmp_path)
    assert (finding.check, finding.path, finding.line) == (CHECK, "docs/lab.py", 1)
    assert finding.message.startswith("F401: ")
    assert "os" in finding.message


@pytest.mark.parametrize(
    ("source", "code", "severity"),
    [
        ("import os\n", "F401", Severity.WARNING),
        ("print(undefined_name)\n", "F821", Severity.WARNING),
        ("x = 1   \n", "W291", Severity.INFO),
        ("import sys\nimport os\n\nprint(os, sys)\n", "I001", Severity.INFO),
    ],
    ids=["unused-import", "undefined-name", "trailing-space", "unsorted-imports"],
)
def test_correctness_problems_are_warnings_and_style_is_info(
    tmp_path, source, code, severity
):
    course(tmp_path)
    write(tmp_path, "docs/lab.py", source)
    [finding] = only(check_python_style(tmp_path), code)
    assert finding.severity == severity


def test_a_syntax_error_is_a_warning(tmp_path):
    course(tmp_path)
    write(tmp_path, "docs/lab.py", "def broken(:\n    pass\n")
    findings = check_python_style(tmp_path)
    assert findings
    assert all(f.severity == Severity.WARNING for f in findings)
    assert findings[0].message.startswith("Syntax error: ")


@pytest.mark.parametrize(
    ("source", "line", "before", "after"),
    [
        ("x = 1   \n", 1, "x = 1   ", "x = 1"),
        ("def f():\n    x = 1\n    \n    return x\n", 3, "    ", ""),
    ],
    ids=["trailing-space", "blank-line-with-spaces"],
)
@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_a_safe_one_line_fix_becomes_a_fix(
    tmp_path, source, line, before, after, newline
):
    course(tmp_path)
    write(tmp_path, "docs/lab.py", source, newline)
    [finding] = [f for f in check_python_style(tmp_path) if f.line == line]
    assert (finding.fix.line, finding.fix.before, finding.fix.after) == (
        line,
        before,
        after,
    )


@pytest.mark.parametrize(
    ("config", "source", "code"),
    [
        (RULES, "import sys\nimport os\n\nprint(os, sys)\n", "I001"),  # several lines
        (RULES, "import os\nx = 1\n", "F401"),  # deletes the whole line
        (RULES, "def f():\n    unused = 1\n", "F841"),  # unsafe
    ],
    ids=["multi-line", "line-deleted", "unsafe"],
)
def test_other_fixes_stay_messages(tmp_path, config, source, code):
    course(tmp_path, config)
    write(tmp_path, "docs/lab.py", source)
    [finding] = only(check_python_style(tmp_path), code)
    assert finding.fix is None


def test_notebook_findings_name_the_cell_and_have_no_line(tmp_path):
    course(tmp_path)
    notebook = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": ["# Lab\n"]},
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["x = 1\n", "import os\n", "y = 2   "],
            },
        ],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    write(tmp_path, "docs/Lab.ipynb", json.dumps(notebook))
    findings = check_python_style(tmp_path)
    assert {f.message.split(":")[0] for f in findings} >= {"Cell 2, line 2"}
    assert all(f.line is None and f.fix is None for f in findings)
    assert all(f.path == "docs/Lab.ipynb" for f in findings)
    [unused] = [f for f in findings if "F401" in f.message]
    assert unused.message.startswith("Cell 2, line 2: F401: ")


def test_only_files_under_docs_are_checked(tmp_path):
    course(tmp_path)
    write(tmp_path, "GradingAssistant/grade.py", "import os\n")
    write(tmp_path, "docs/lab.py", "import sys\n")
    assert [f.path for f in check_python_style(tmp_path)] == ["docs/lab.py"]


def test_a_settings_file_at_the_root_is_used_when_there_is_no_grading_one(tmp_path):
    course(tmp_path, '[lint]\nselect = ["W"]\n', where="ruff.toml")
    write(tmp_path, "docs/lab.py", "import os\nx = 1   \n")
    assert [f.message[:4] for f in check_python_style(tmp_path)] == ["W291"]


def test_without_course_settings_ruff_finds_settings_near_the_files(tmp_path):
    course(tmp_path, config=None)
    write(tmp_path, "docs/Example/pyproject.toml", '[tool.ruff.lint]\nselect = ["W"]\n')
    write(tmp_path, "docs/Example/lab.py", "import os\nx = 1   \n")
    assert [f.message[:4] for f in check_python_style(tmp_path)] == ["W291"]


def test_ruff_leaves_no_cache_in_the_course(tmp_path):
    course(tmp_path)
    write(tmp_path, "docs/lab.py", "import os\n")
    check_python_style(tmp_path)
    assert not list(tmp_path.rglob(".ruff_cache"))


def test_broken_settings_raise(tmp_path):
    course(tmp_path, "this is [not toml")
    write(tmp_path, "docs/lab.py", "x = 1\n")
    with pytest.raises(RuffError):
        check_python_style(tmp_path)


def test_findings_are_in_file_and_line_order(tmp_path):
    course(tmp_path)
    write(tmp_path, "docs/b.py", "import os\n\nx = 1   \n")
    write(tmp_path, "docs/a.py", "import sys\n")
    assert [(f.path, f.line) for f in check_python_style(tmp_path)] == [
        ("docs/a.py", 1),
        ("docs/b.py", 1),
        ("docs/b.py", 3),
    ]


def test_no_docs_folder_means_no_findings(tmp_path):
    assert check_python_style(tmp_path) == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
