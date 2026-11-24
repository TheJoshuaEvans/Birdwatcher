"""
The reset dialog: confirms resetting Birdwatcher's settings (everything it
has saved except the activity log).

Joshua Evans, 2026-11-12 (written with Claude Opus 5.5)
"""

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Static

RESET_TEXT = (
    "Birdwatcher will forget what it has saved on this computer:\n\n"
    "  - your course folders and the recent list, the editor, theme and layout;\n"
    "  - the list of fixed findings (the fixes themselves stay in your files);\n"
    "  - every ignored finding, and its reason;\n"
    "  - the answers it keeps from web sites;\n"
    "  - the AI's spelling verdicts;\n"
    "  - the API keys saved in Birdwatcher (environment variables stay);\n"
    "  - the downloaded demo course.\n\n"
    "Your course folders are not touched: their files, and each course's "
    "cspell.json, stay as they are. The activity log stays too (DELETE LOG "
    "removes it)."
)


class ResetDialog(ModalScreen):
    """
    Asks whether to reset Birdwatcher's settings, saying what that forgets
    and that course folders and the activity log are not touched
    (#reset-text). Enter or the Reset button closes it with True; Escape or
    the Cancel button with False.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Reset settings"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="reset-dialog") as dialog:
            dialog.border_title = Content("[ START FRESH? ]")
            yield Static(Text(RESET_TEXT), id="reset-text")
            with Horizontal(id="reset-buttons"):
                yield Button(
                    Content("[↵] RESET SETTINGS"),
                    variant="error",
                    id="confirm-reset",
                )
                yield Button(Content("[ESC] CANCEL"), id="cancel-reset")

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        if event.button.id == "confirm-reset":
            self.action_confirm()
        else:
            self.action_cancel()

    def action_confirm(self):
        self.dismiss(True)

    def action_cancel(self):
        self.dismiss(False)
