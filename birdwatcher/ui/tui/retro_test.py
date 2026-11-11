"""
Contract tests for birdwatcher.ui.tui.retro.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import asyncio
import sys

import pytest
from textual.app import App

from birdwatcher.ui.tui.retro import StatusChip


class OneChip(App):
    def __init__(self, value):
        super().__init__()
        self._value = value

    def compose(self):
        yield StatusChip("FIXED 3", value=self._value)


def chip_text(steps=None, value=True):
    app = OneChip(value)

    async def main():
        async with app.run_test() as pilot:
            chip = app.query_one(StatusChip)
            if steps:
                await steps(chip, pilot)
            await pilot.pause()
            return chip.render().plain

    return asyncio.run(main())


@pytest.mark.parametrize(("value", "box"), [(True, "[X]"), (False, "[ ]")])
def test_the_box_shows_the_state_in_characters(value, box):
    assert chip_text(value=value).startswith(f"{box} FIXED 3")


def test_toggling_redraws_the_box():
    async def toggle(chip, pilot):
        chip.toggle()

    assert chip_text(toggle, value=True).startswith("[ ] FIXED 3")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
