"""
The ignore dialog: confirms ignoring a finding and takes an optional reason.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from birdwatcher.core.findings import Severity
from birdwatcher.ui.severity import SEVERITY_STYLES

ERROR_WARNING = "This is an error: readers are affected by it."


class IgnoreDialog(ModalScreen):
    """
    Asks whether to ignore a finding, with an optional one-line reason.

    It names the finding (severity, check, location, message). For an error,
    it also warns that readers are affected. Enter in the reason box or the
    Ignore button closes it with the reason ("" when none was typed); Escape
    or the Cancel button closes it with None.

    Args:
        finding (Finding): The finding to ignore.
        check_title (str): The title of the check that found it.
    """

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, finding, check_title):
        super().__init__()
        self._finding = finding
        self._check_title = check_title

    def compose(self) -> ComposeResult:
        finding = self._finding
        is_error = finding.severity == Severity.ERROR
        label, style = SEVERITY_STYLES[finding.severity]
        summary = Text()
        summary.append(f" {label} ", style=f"reverse {style}")
        summary.append(f"  {self._check_title}\n", style="bold")
        summary.append(finding.path, style="underline")
        summary.append(f"  line {finding.line}\n" if finding.line else "\n")
        summary.append(finding.message)
        with Vertical(id="ignore-dialog"):
            yield Static("Ignore this finding?", id="ignore-title")
            yield Static(summary, id="ignore-summary")
            warning = Static(ERROR_WARNING, id="ignore-warning")
            warning.display = is_error
            yield warning
            yield Static("Reason (optional):", id="ignore-reason-label")
            yield Input(placeholder="Why it can stay as it is", id="ignore-reason")
            with Horizontal(id="ignore-buttons"):
                yield Button(
                    "Ignore",
                    variant="error" if is_error else "primary",
                    id="confirm-ignore",
                )
                yield Button("Cancel", id="cancel-ignore")

    def on_input_submitted(self, event: Input.Submitted):
        event.stop()
        self._confirm()

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        if event.button.id == "confirm-ignore":
            self._confirm()
        else:
            self.action_cancel()

    def action_cancel(self):
        self.dismiss(None)

    def _confirm(self):
        self.dismiss(self.query_one("#ignore-reason", Input).value)
