"""
Small widgets for Birdwatcher's retro terminal look.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from textual.widgets import Checkbox


class StatusChip(Checkbox):
    """
    A checkbox drawn as "[X] LABEL" when on and "[ ] LABEL" when off, so its
    state reads from the characters, not only from colors (Textual's own
    checkbox always draws an X and shows the state by color alone).

    Takes the same arguments as Checkbox.
    """

    BUTTON_LEFT = "["
    BUTTON_RIGHT = "]"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.BUTTON_INNER = "X" if self.value else " "

    def watch_value(self):
        # Checkbox's own watch_value posts Changed, which the list listens to.
        super().watch_value()
        self.BUTTON_INNER = "X" if self.value else " "
        self.refresh()
