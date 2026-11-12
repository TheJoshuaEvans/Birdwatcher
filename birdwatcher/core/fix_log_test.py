"""
Contract tests for birdwatcher.core.fix_log.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
import sys
from datetime import UTC, datetime

import pytest

from birdwatcher.core.findings import Destination, Edit, Finding, Fix, Severity
from birdwatcher.core.fix_log import FixedFinding, load_fixed, save_fixed

WHEN = datetime(2026, 11, 10, 12, 30, tzinfo=UTC)
LINK_FIX = Fix(
    line=25,
    before="#goalmdashrules",
    after="#goalrules",
    destination=Destination(
        "docs/Page.md", 31, "https://lcc-cit.github.io/CS212/Page.html#goalrules"
    ),
)
FIXED = FixedFinding(
    Finding("broken-section-link", Severity.ERROR, "docs/Page.md", 25, "m", LINK_FIX),
    WHEN,
)
PLAIN = FixedFinding(
    Finding(
        "other",
        Severity.WARNING,
        "docs/B.md",
        3,
        "n",
        Fix(3, "x", "y", destination=None),
    ),
    WHEN,
)


def test_saved_fixes_load_back(tmp_path):
    log = tmp_path / "fixes.json"
    course = tmp_path / "course"
    save_fixed(log, course, [FIXED, PLAIN])
    assert load_fixed(log, course) == [FIXED, PLAIN]


def test_a_fix_with_further_edits_loads_back(tmp_path):
    log = tmp_path / "fixes.json"
    course = tmp_path / "course"
    fix = Fix(1, "Python", "", also=(Edit(3, "```", "```python"),))
    fixed = FixedFinding(
        Finding("stray-language-label", Severity.WARNING, "docs/P.md", 1, "m", fix),
        WHEN,
    )
    save_fixed(log, course, [fixed])
    assert load_fixed(log, course) == [fixed]


def test_each_course_folder_has_its_own_fixes(tmp_path):
    log = tmp_path / "settings" / "fixes.json"
    first, second = tmp_path / "first", tmp_path / "second"
    save_fixed(log, first, [FIXED])
    save_fixed(log, second, [PLAIN])
    assert load_fixed(log, first) == [FIXED]
    assert load_fixed(log, second) == [PLAIN]


def test_saving_an_empty_list_forgets_only_that_folder(tmp_path):
    log = tmp_path / "fixes.json"
    first, second = tmp_path / "first", tmp_path / "second"
    save_fixed(log, first, [FIXED])
    save_fixed(log, second, [PLAIN])
    save_fixed(log, first, [])
    assert load_fixed(log, first) == []
    assert load_fixed(log, second) == [PLAIN]


def test_the_same_folder_spelled_differently_is_the_same_course(tmp_path, monkeypatch):
    log = tmp_path / "fixes.json"
    (tmp_path / "course").mkdir()
    monkeypatch.chdir(tmp_path)
    save_fixed(log, tmp_path / "course", [FIXED])
    assert load_fixed(log, "course") == [FIXED]


def test_missing_log_remembers_nothing(tmp_path):
    assert load_fixed(tmp_path / "fixes.json", tmp_path) == []


@pytest.mark.parametrize("content", ["", "not json", "[]", '{"x": 5}'])
def test_unreadable_log_remembers_nothing(tmp_path, content):
    log = tmp_path / "fixes.json"
    log.write_text(content, encoding="utf-8")
    assert load_fixed(log, tmp_path) == []


def test_unreadable_entries_are_left_out(tmp_path):
    log = tmp_path / "fixes.json"
    course = tmp_path / "course"
    save_fixed(log, course, [FIXED])
    data = json.loads(log.read_text(encoding="utf-8"))
    [key] = data
    data[key].append({"nonsense": True})
    log.write_text(json.dumps(data), encoding="utf-8")
    assert load_fixed(log, course) == [FIXED]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
