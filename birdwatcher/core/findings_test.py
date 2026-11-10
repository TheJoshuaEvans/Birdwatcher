"""
Contract tests for birdwatcher.core.findings.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import os
import re
import subprocess
import sys
from dataclasses import replace

import pytest

from birdwatcher.core.findings import Finding, Fix, Severity

BASE = Finding(
    check="broken-section-link",
    severity=Severity.ERROR,
    path="docs/Page.md",
    line=12,
    message="Section link '#x' points nowhere.",
)


def test_id_is_twelve_hex_characters():
    assert re.fullmatch(r"[0-9a-f]{12}", BASE.id)


def test_id_is_the_same_for_equal_findings():
    assert Finding(**vars(BASE)).id == BASE.id


def id_in_fresh_interpreter(hash_seed):
    """Compute BASE's id in a new Python process with the given hash seed."""
    code = (
        "from birdwatcher.core.findings import Finding, Severity\n"
        f"print(Finding('broken-section-link', Severity.ERROR, {BASE.path!r}, "
        f"{BASE.line!r}, {BASE.message!r}).id)"
    )
    env = {**os.environ, "PYTHONHASHSEED": str(hash_seed)}
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return result.stdout.strip()


def test_id_is_the_same_on_every_run():
    assert id_in_fresh_interpreter(1) == id_in_fresh_interpreter(2) == BASE.id


@pytest.mark.parametrize(
    "change",
    [
        {"check": "other-check"},
        {"severity": Severity.WARNING},
        {"path": "docs/Other.md"},
        {"line": 13},
        {"line": None},
        {"message": "Something else."},
    ],
    ids=["check", "severity", "path", "line", "no-line", "message"],
)
def test_id_differs_when_any_field_differs(change):
    assert replace(BASE, **change).id != BASE.id


def test_id_does_not_depend_on_the_fix():
    fixed = replace(BASE, fix=Fix(line=12, before="#x", after="#y"))
    assert fixed.id == BASE.id


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
