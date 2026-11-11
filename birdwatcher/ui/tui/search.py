"""
The search box of the findings view's FIND row.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.message import Message
from textual.widgets import Input


class SearchBox(Input):
    """
    A one-line search box. Typing changes its value (Input.Changed), Enter
    submits it (Input.Submitted), and Escape empties it and posts
    SearchBox.Cleared.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "clear", "Clear the search", show=False),
    ]

    class Cleared(Message):
        """The search was emptied with Escape."""

    def action_clear(self):
        self.value = ""
        self.post_message(self.Cleared())
