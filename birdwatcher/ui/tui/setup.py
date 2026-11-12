"""
The setup page: choose the course folder (from the recent ones, or by typing,
pasting or browsing) and the editor that opens files.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.content import Content
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    OptionList,
    RadioButton,
    RadioSet,
    Select,
    Static,
)
from textual.widgets.option_list import Option

from birdwatcher.core.config import THEME_AUTO
from birdwatcher.core.course import DOCS_FOLDER, course_problem
from birdwatcher.ui.tui.reset import ResetDialog

SETUP_INTRO = (
    "Birdwatcher checks a local clone of a course repository: the folder that "
    f"holds its pages, in {DOCS_FOLDER}/ or at the top."
)
EMPTY_PATH = "Enter the path of the course repository's folder."
EDITOR_ID_PREFIX = "editor-"
MATCH_SYSTEM = "Match the system (light or dark)"


@dataclass(frozen=True)
class SetupChoice:
    """
    What the setup page was closed with.

    Attributes:
        course_dir (Path): The chosen course folder (it can be used).
        editor (str): The id of the chosen editor.
        theme (str): The chosen theme's name, or core.config.THEME_AUTO.
    """

    course_dir: Path
    editor: str
    theme: str = THEME_AUTO


class SetupScreen(Screen):
    """
    The setup page: closes with a SetupChoice once a usable folder is chosen
    (or with None when cancelled). See BirdwatcherApp for the behavior as a
    whole.

    Args:
        course_dir (Path | None): The path to fill in.
        problem (str | None): Why that path cannot be used, shown at once.
        can_cancel (bool): Whether Escape closes the page without a choice.
        choose_folder (Callable[[Path | None], Path | None]): The folder picker.
        recent (Sequence[Path]): Recent course folders, most recent first.
        editors (Mapping[str, Editor]): The editors on offer, in order.
        editor (str): The id of the editor to select at first.
        themes (Sequence[str]): The theme names on offer, after "Match the
            system".
        theme (str): The theme setting to select at first.
        preview_theme (Callable[[str], object]): Shows a theme setting while
            the page is open (the app puts the saved one back on cancel).
        reset (Callable[[], object] | None): Forgets everything Birdwatcher
            has saved; with it, a RESET EVERYTHING button asks first (see
            reset.ResetDialog) and calls it when confirmed.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("ctrl+o", "browse", "Browse"),
        Binding("escape", "cancel", "Back"),
        # q leaves: back to the course, or (on a first run, with nothing to go
        # back to) out of Birdwatcher. In the path box it is just a letter.
        Binding("q", "cancel", "Back"),
        Binding("q", "quit_first_run", "Quit"),
        Binding("ctrl+q", "app.quit", "Quit"),
    ]

    def __init__(
        self,
        course_dir,
        problem,
        *,
        can_cancel,
        choose_folder,
        recent=(),
        editors=None,
        editor=None,
        themes=(),
        theme=THEME_AUTO,
        preview_theme=None,
        reset=None,
    ):
        super().__init__()
        self._reset = reset
        self._themes = tuple(themes)
        self._theme = theme if theme in self._themes else THEME_AUTO
        self._preview_theme = preview_theme or (lambda setting: None)
        self._course_dir = course_dir
        self._problem = problem
        self._can_cancel = can_cancel
        self._choose_folder = choose_folder
        self._recent = tuple(recent)
        self._editors = dict(editors or {})
        self._editor = editor

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="setup"):
            yield Static(SETUP_INTRO, id="setup-intro")
            recent_label = Static("RECENT COURSES", classes="setup-section")
            recent = OptionList(
                *(
                    Option(_recent_prompt(folder), id=str(index))
                    for index, folder in enumerate(self._recent)
                ),
                id="recent",
            )
            recent_label.display = recent.display = bool(self._recent)
            yield recent_label
            yield recent
            yield Static("ANOTHER FOLDER", classes="setup-section")
            with Horizontal(id="setup-path"):
                yield Input(
                    value="" if self._course_dir is None else str(self._course_dir),
                    placeholder=r"C:\path\to\CS212-CourseMaterials",
                    id="course-dir",
                )
                yield Button(Content("[^O] BROWSE"), id="browse")
            yield Static("OPEN FILES WITH", classes="setup-section")
            with RadioSet(id="editor"):
                for editor in self._editors.values():
                    yield RadioButton(
                        _editor_label(editor),
                        value=editor.id == self._editor,
                        id=f"{EDITOR_ID_PREFIX}{editor.id}",
                        disabled=not editor.available,
                    )
            yield Static("COLOR THEME", classes="setup-section")
            yield Select(
                [(MATCH_SYSTEM, THEME_AUTO), *((name, name) for name in self._themes)],
                value=self._theme,
                allow_blank=False,
                id="theme",
            )
            yield Static(self._problem or "", id="setup-error")
            with Horizontal(id="setup-buttons"):
                yield Button(Content("[↵] SAVE"), variant="primary", id="save")
                if self._reset is not None:
                    yield Button(
                        Content("RESET EVERYTHING…"), variant="error", id="reset"
                    )
        yield Footer()

    def on_mount(self):
        self.query_one("#setup").border_title = Content("[ COURSE FOLDER ]")

    def check_action(self, action, parameters):
        if action == "cancel":
            return self._can_cancel
        if action == "quit_first_run":
            return not self._can_cancel
        return True

    def action_cancel(self):
        if self._can_cancel:
            self.dismiss(None)

    def action_quit_first_run(self):
        if not self._can_cancel:
            self.app.exit()

    def on_input_submitted(self, event: Input.Submitted):
        self._choose(self._typed_folder())

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "browse":
            self.action_browse()
        elif event.button.id == "save":
            self._choose(self._typed_folder())
        elif event.button.id == "reset":
            self.app.push_screen(ResetDialog(), self._reset_answered)

    def _reset_answered(self, confirmed):
        if confirmed:
            self._reset()

    def on_select_changed(self, event: Select.Changed):
        self._preview_theme(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        folder = self._recent[int(event.option.id)]
        self.query_one("#course-dir", Input).value = str(folder)
        self._choose(folder)

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
        self._choose(Path(chosen))

    def _typed(self):
        # Explorer's "Copy as path" adds quotes; "~" is common on a Mac.
        return self.query_one("#course-dir", Input).value.strip().strip('"')

    def _typed_folder(self):
        text = self._typed()
        return Path(text).expanduser() if text else None

    def _choose(self, course_dir):
        if course_dir is None:
            self._show_problem(EMPTY_PATH)
            return
        problem = course_problem(course_dir)
        if problem:
            self._show_problem(problem)
            return
        theme = self.query_one("#theme", Select).value
        self.dismiss(SetupChoice(course_dir, self._chosen_editor(), theme))

    def _chosen_editor(self):
        pressed = self.query_one("#editor", RadioSet).pressed_button
        if pressed is not None:
            return pressed.id.removeprefix(EDITOR_ID_PREFIX)
        # The saved editor is not on offer here: keep it rather than guess.
        return self._editor

    def _show_problem(self, problem):
        self.query_one("#setup-error", Static).update(Text(problem))


def _recent_prompt(folder):
    prompt = Text(folder.name or str(folder), style="bold")
    prompt.append(f"   {folder}", style="dim")
    return prompt


def _editor_label(editor):
    where = "opens at the exact line" if editor.opens_at_line else "opens at the top"
    label = f"{editor.name}: {where}"
    return label if editor.available else f"{label} (not found)"
