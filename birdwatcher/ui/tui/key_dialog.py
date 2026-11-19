"""
The API key dialog: takes a provider's key without showing it.

Joshua Evans, 2026-11-18 (written with Claude Opus 5.5)
"""

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static


class KeyDialog(ModalScreen):
    """
    Asks for a provider's API key in a masked box (#key-input). Enter or the
    Save button (#save-key) closes it with the key, without surrounding
    spaces (None when the box is blank); Escape or Cancel (#cancel-key) with
    None. The text (#key-text) says the key goes to the system keyring, never
    the settings file.

    Args:
        provider_name (str): The provider the key is for, e.g. "OpenRouter".
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, provider_name):
        super().__init__()
        self._provider_name = provider_name

    def compose(self) -> ComposeResult:
        with Vertical(id="key-dialog") as dialog:
            dialog.border_title = Content("[ API KEY ]")
            yield Static(
                Text(
                    f"Paste your {self._provider_name} API key. Birdwatcher keeps "
                    "it in the system keyring (Credential Manager on Windows, "
                    "Keychain on a Mac), never in its settings file."
                ),
                id="key-text",
            )
            yield Input(password=True, placeholder="API key", id="key-input")
            with Horizontal(id="key-buttons"):
                yield Button(Content("[↵] SAVE"), variant="primary", id="save-key")
                yield Button(Content("[ESC] CANCEL"), id="cancel-key")

    def on_mount(self):
        self.query_one("#key-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted):
        event.stop()
        self._save()

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        if event.button.id == "save-key":
            self._save()
        else:
            self.action_cancel()

    def _save(self):
        key = self.query_one("#key-input", Input).value.strip()
        self.dismiss(key or None)

    def action_cancel(self):
        self.dismiss(None)
