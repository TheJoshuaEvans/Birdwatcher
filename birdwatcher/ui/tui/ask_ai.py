"""
The ask-the-AI dialog: shows what asking a model about a branch's misspelled
words will cost, before any request is sent.

Joshua Evans, 2026-11-23 (written with Claude Opus 5.5)
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
    return f"{count:,} {one if count == 1 else many}"


class AskAiDialog(ModalScreen):
    """
    Asks whether to send a branch's words to the model. It names the branch,
    the number of words and requests, the model and the rough number of
    tokens (more for models that think before answering), and says that
    verdicts arrive as suggested fixes, so nothing in the course changes
    until they are applied. Enter or the Ask button closes it with True;
    Escape or the Cancel button with False.

    Args:
        branch (str): The branch's label (a check's title, a folder or file).
        findings (int): The spelling errors to ask about.
        estimate (spelling_triage.Estimate): What asking will cost.
        model (str): The model that will be asked.
        warning (str | None): A caution about that model
            (core.ai.model_warning), shown last; None shows none.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Ask"),
    ]

    def __init__(self, branch, findings, estimate, model, warning=None):
        super().__init__()
        self._branch = branch
        self._findings = findings
        self._estimate = estimate
        self._model = model
        self._warning = warning

    def compose(self) -> ComposeResult:
        estimate = self._estimate
        text = Text()
        text.append(f"{self._branch}\n\n", style="bold")
        text.append(
            f"Ask {self._model} about {_plural(self._findings, 'error', 'errors')} "
            "(the words the dictionary cannot fix; warnings and info have their "
            f"own fixes), in {_plural(estimate.requests, 'request', 'requests')}. "
            f"About {estimate.tokens:,} tokens (models that think before "
            "answering use several times more).\n\n"
        )
        text.append(
            "Each verdict arrives as a suggested fix, or as a word to keep. "
            "Nothing in your course folder changes until you apply them."
        )
        if self._warning:
            text.append(f"\n\nNOTE {self._warning}", style="italic")
        with Vertical(id="ask-ai-dialog") as dialog:
            dialog.border_title = Content("[ ASK THE AI? ]")
            yield Static(text, id="ask-ai-text")
            with Horizontal(id="ask-ai-buttons"):
                yield Button(
                    Content(f"[↵] ASK ABOUT {self._findings:,}"),
                    variant="success",
                    id="confirm-ask-ai",
                )
                yield Button(Content("[ESC] CANCEL"), id="cancel-ask-ai")

    def on_button_pressed(self, event: Button.Pressed):
        event.stop()
        if event.button.id == "confirm-ask-ai":
            self.action_confirm()
        else:
            self.action_cancel()

    def action_confirm(self):
        self.dismiss(True)

    def action_cancel(self):
        self.dismiss(False)
