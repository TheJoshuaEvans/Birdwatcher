"""
A draggable divider between two side-by-side panes.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from textual import events
from textual.widget import Widget

DRAGGING_CLASS = "-dragging"  # styled like :hover, so the bar stays lit mid-drag


class Divider(Widget):
    """
    A vertical bar between two side-by-side panes. Pressing the mouse on it and
    dragging moves the bar: the pane on its left (`target`) is resized so its
    right edge follows the pointer, until the button is released. Neither pane
    shrinks below `min_width` columns. Moving the mouse without pressing on the
    bar changes nothing. The bar's look, and its look while hovered or dragged
    (class "-dragging"), come from the stylesheet.

    Args:
        target (str): CSS selector, within the same screen, of the pane on the
            divider's left.
        min_width (int): The fewest columns either pane may shrink to.
        id (str | None): The widget's id.
    """

    def __init__(self, target, *, min_width, id=None):
        super().__init__(id=id)
        self._target = target
        self._min_width = min_width
        self._dragging = False

    def render(self):
        # The bar is drawn by its background; without this, Textual shows the
        # widget's name and classes as text.
        return ""

    def on_mouse_down(self, event: events.MouseDown):
        self._dragging = True
        self.add_class(DRAGGING_CLASS)
        # Captured, the bar keeps getting mouse moves when the pointer leaves it.
        self.capture_mouse()
        event.stop()

    def on_mouse_move(self, event: events.MouseMove):
        if not self._dragging:
            return
        pane = self.screen.query_one(self._target)
        container = self.parent.region
        widest = container.right - pane.region.x - self.size.width - self._min_width
        width = event.screen_x - pane.region.x
        pane.styles.width = max(self._min_width, min(width, widest))
        event.stop()

    def on_mouse_up(self, event: events.MouseUp):
        if not self._dragging:
            return
        self._dragging = False
        self.remove_class(DRAGGING_CLASS)
        self.release_mouse()
        event.stop()
