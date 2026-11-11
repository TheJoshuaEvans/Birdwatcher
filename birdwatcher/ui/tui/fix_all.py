"""
The fix-all dialog: confirms fixing every fixable finding in a branch.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Button, Static


def _plural(count, one, many):
    return f"{count} {one if count == 1 else many}"


class FixAllDialog(ModalScreen):
    """
    Asks whether to apply a batch of fixes. It names the branch and says how
    many lines in how many files will change, and that each fix can be undone
    on its own. Enter or the Fix button
    closes it with True; Escape or the Cancel button with False.

    Args:
        branch (str): The branch's label (a check's title, a folder or file).
        findings (Sequence[Finding]): The findings whose fixes will be applied.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Fix them all"),
    ]

    def __init__(self, branch, findings):
        super().__init__()
        self._branch = branch
        self._findings = list(findings)

    def compose(self) -> ComposeResult:
        count = len(self._findings)
        lines = len({(f.path, f.fix.line) for f in self._findings})
        files = len({f.path for f in self._findings})
        text = Text()
        text.append(f"{self._branch}\n\n", style="bold")
        text.append(
            f"{_plural(count, 'fix', 'fixes')} will change "
            f"{_plural(lines, 'line', 'lines')} in {_plural(files, 'file', 'files')} "
            "of your course folder. Each is the suggested fix shown for its "
            "finding; afterwards they are listed as FIXED, where each can be "
            "checked and undone on its own."
        )
        with Vertical(id="fix-all-dialog") as dialog:
            dialog.border_title = Content("[ FIX THEM ALL? ]")
            yield Static(text, id="fix-all-text")
            with Horizontal(id="fix-all-buttons"):
                yield Button(
                    Content(f"[↵] FIX {count}"), variant="success", id="confirm-fix-all"
                )
                yield Button(Content("[ESC] CANCEL"), id="cancel-fix-all")

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        if event.button.id == "confirm-fix-all":
            self.action_confirm()
        else:
            self.action_cancel()

    def action_confirm(self):
        self.dismiss(True)

    def action_cancel(self):
        self.dismiss(False)
