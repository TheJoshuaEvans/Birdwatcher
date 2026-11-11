"""
Contract tests for birdwatcher.ui.tui.keys (the popup itself is driven in
app_test).

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.ui.tui.findings import FindingsScreen
from birdwatcher.ui.tui.keys import KEY_GROUPS


def test_every_key_of_the_findings_view_is_in_the_popup():
    listed = {
        action for _, keys in KEY_GROUPS for key in keys for action in key.actions
    }
    bound = {
        binding.action.split("(")[0].removeprefix("app.")
        for binding in FindingsScreen.BINDINGS
    }
    assert bound - listed == set()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
