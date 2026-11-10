"""
The setup page: choose the course folder by typing, pasting or browsing.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from birdwatcher.core.course import DOCS_FOLDER, course_problem

SETUP_INTRO = (
    "Birdwatcher checks a local clone of the course repository. Enter the path "
    f"of its folder: the one that contains {DOCS_FOLDER}/."
)
EMPTY_PATH = "Enter the path of the course repository's folder."


class SetupScreen(Screen):
    """
    The setup page: asks for the course folder, and closes with it once it can
    be used (or with None when cancelled). See BirdwatcherApp for the behaviour
    as a whole.

    Args:
        course_dir (Path | None): The path to fill in.
        problem (str | None): Why that path cannot be used, shown at once.
        can_cancel (bool): Whether Escape closes the page without a choice.
        choose_folder (Callable[[Path | None], Path | None]): The folder picker.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+o", "browse", "Browse"),
        Binding("escape", "cancel", "Back"),
        Binding("ctrl+q", "app.quit", "Quit"),
    ]

    def __init__(self, course_dir, problem, *, can_cancel, choose_folder):
        super().__init__()
        self._course_dir = course_dir
        self._problem = problem
        self._can_cancel = can_cancel
        self._choose_folder = choose_folder

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="setup"):
            yield Static("Course folder", id="setup-title")
            yield Static(SETUP_INTRO, id="setup-intro")
            with Horizontal(id="setup-path"):
                yield Input(
                    value="" if self._course_dir is None else str(self._course_dir),
                    placeholder=r"C:\path\to\CS212-CourseMaterials",
                    id="course-dir",
                )
                yield Button("Browse…", id="browse")
            yield Static(self._problem or "", id="setup-error")
            with Horizontal():
                yield Button("Save", variant="primary", id="save")
        yield Footer()

    def check_action(self, action, parameters):
        if action == "cancel":
            return self._can_cancel
        return True

    def action_cancel(self):
        if self._can_cancel:
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted):
        self._save()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "browse":
            self.action_browse()
        else:
            self._save()

    def action_browse(self):
        text = self._typed()
        start = Path(text).expanduser() if text else None
        try:
            chosen = self._choose_folder(start)
        except OSError as error:
            self._show_problem(
                f"Could not open a folder picker ({error}). Type the path instead."
            )
            return
        if chosen is None:
            return
        self.query_one("#course-dir", Input).value = str(chosen)
        self._save()

    def _typed(self):
        # Explorer's "Copy as path" adds quotes; "~" is common on a Mac.
        return self.query_one("#course-dir", Input).value.strip().strip('"')

    def _save(self):
        text = self._typed()
        if not text:
            self._show_problem(EMPTY_PATH)
            return
        course_dir = Path(text).expanduser()
        problem = course_problem(course_dir)
        if problem:
            self._show_problem(problem)
            return
        self.dismiss(course_dir)

    def _show_problem(self, problem):
        self.query_one("#setup-error", Static).update(Text(problem))
