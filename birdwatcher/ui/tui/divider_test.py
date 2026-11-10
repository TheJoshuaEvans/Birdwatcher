"""
Contract tests for birdwatcher.ui.tui.divider, dragged headless with Textual's
test pilot in a small two-pane app.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import asyncio
import sys

import pytest
from textual.app import App
from textual.containers import Horizontal
from textual.widgets import Static

from birdwatcher.ui.tui.divider import Divider

SCREEN_WIDTH = 100
LEFT_WIDTH = 40
MIN_WIDTH = 10


class TwoPanes(App):
    CSS = f"""
    #left {{ width: {LEFT_WIDTH}; }}
    #right {{ width: 1fr; }}
    Divider {{ width: 1; }}
    """

    def compose(self):
        with Horizontal():
            yield Static("left", id="left")
            yield Divider("#left", min_width=MIN_WIDTH)
            yield Static("right", id="right")


def run_panes(steps):
    """Run TwoPanes headless and return the left pane's width afterwards."""
    app = TwoPanes()

    async def main():
        async with app.run_test(size=(SCREEN_WIDTH, 10)) as pilot:
            await steps(pilot)
            await pilot.pause()
            return app.query_one("#left").size.width

    return asyncio.run(main())


async def drag(pilot, columns):
    """Press on the divider, move `columns` sideways, release there.

    The pointer's destination is a screen position: the divider moves during
    the drag, so offsets from it would shift under the pointer.
    """
    start = pilot.app.query_one(Divider).region.x
    destination = (start + columns, 0)
    await pilot.mouse_down(Divider)
    await pilot.hover(None, offset=destination)
    await pilot.mouse_up(None, offset=destination)


def test_the_bar_shows_no_text():
    async def steps(pilot):
        assert str(pilot.app.query_one(Divider).render()).strip() == ""

    run_panes(steps)


@pytest.mark.parametrize("columns", [-15, 20], ids=["left", "right"])
def test_dragging_moves_the_left_panes_edge_with_the_pointer(columns):
    assert run_panes(lambda pilot: drag(pilot, columns)) == LEFT_WIDTH + columns


def test_the_left_pane_keeps_its_minimum_width():
    assert run_panes(lambda pilot: drag(pilot, -LEFT_WIDTH)) == MIN_WIDTH


def test_the_right_pane_keeps_its_minimum_width():
    right_edge = SCREEN_WIDTH - 1 - LEFT_WIDTH
    widest = SCREEN_WIDTH - 1 - MIN_WIDTH  # the divider takes one column
    assert run_panes(lambda pilot: drag(pilot, right_edge)) == widest


def test_moving_without_pressing_changes_nothing():
    async def steps(pilot):
        await pilot.hover(Divider)
        await pilot.hover(None, offset=(LEFT_WIDTH - 15, 0))

    assert run_panes(steps) == LEFT_WIDTH


def test_moving_after_release_changes_nothing():
    async def steps(pilot):
        await drag(pilot, -5)
        await pilot.hover(None, offset=(LEFT_WIDTH - 20, 0))

    assert run_panes(steps) == LEFT_WIDTH - 5


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
