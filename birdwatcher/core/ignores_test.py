"""
Contract tests for birdwatcher.core.ignores.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import json
import sys
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from birdwatcher.core.findings import Finding, Fix, Severity
from birdwatcher.core.ignores import (
    Ignore,
    ignore_finding,
    load_ignores,
    save_ignores,
)

WHEN = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
FINDING = Finding("links", Severity.ERROR, "docs/Page.md", 25, "Broken link.")


def test_an_ignore_matches_its_finding_and_keeps_the_reason():
    ignore = ignore_finding(FINDING, "  kept on purpose ", WHEN)
    assert ignore.matches(FINDING)
    assert ignore.reason == "kept on purpose"
    assert ignore.ignored_at == WHEN


@pytest.mark.parametrize(
    "change",
    [
        {"line": 40},
        {"line": None},
        {"severity": Severity.INFO},
        {"fix": Fix(1, "a", "b")},
    ],
    ids=["moved-line", "no-line", "severity", "fix"],
)
def test_an_ignore_still_matches_when_line_or_severity_change(change):
    ignore = ignore_finding(FINDING, "", WHEN)
    assert ignore.matches(replace(FINDING, **change))


@pytest.mark.parametrize(
    "change",
    [{"check": "other"}, {"path": "docs/Other.md"}, {"message": "Else."}],
    ids=["check", "path", "message"],
)
def test_an_ignore_does_not_match_other_findings(change):
    ignore = ignore_finding(FINDING, "", WHEN)
    assert not ignore.matches(replace(FINDING, **change))


def test_saved_ignores_load_back_per_course(tmp_path):
    store = tmp_path / "ignored.json"
    first = ignore_finding(FINDING, "why", WHEN)
    second = Ignore("numbering", "docs/Labs/Lab02-X", "Shared.", "", WHEN)
    save_ignores(store, tmp_path / "a", [first, second])
    save_ignores(store, tmp_path / "b", [second])
    assert load_ignores(store, tmp_path / "a") == [first, second]
    assert load_ignores(store, tmp_path / "b") == [second]


def test_unreadable_ignores_are_left_out(tmp_path):
    store = tmp_path / "ignored.json"
    course = tmp_path / "course"
    good = ignore_finding(FINDING, "", WHEN)
    save_ignores(store, course, [good])
    data = json.loads(store.read_text(encoding="utf-8"))
    [key] = data
    data[key].append({"check": "x"})
    store.write_text(json.dumps(data), encoding="utf-8")
    assert load_ignores(store, course) == [good]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
