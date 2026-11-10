"""
The app: starts on the right screen, moves between screens, saves settings.

The setup page (setup.py) takes the path of the local course repository. The
findings view (findings.py) shows every finding in a table on the left and the
highlighted finding on the right: its check, severity, location, message, and
the source lines around it. Mouse and keyboard both work:

- Click a finding (or move to it with the arrow keys) to show it.
- Click it again, or press Enter or o, to open the file at that line in the
  editor.
- r runs the checks again, so a fix can be confirmed without leaving the app.
- s opens the setup page, to choose another course folder.
- q quits.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import webbrowser
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path

from textual.app import App

from birdwatcher.checks import ALL_CHECKS
from birdwatcher.core.config import (
    DEFAULT_EDITOR,
    THEME_AUTO,
    Config,
    load_config,
    save_config,
    with_course,
)
from birdwatcher.core.course import check_course, course_problem
from birdwatcher.core.fix_log import FIX_LOG_FILE
from birdwatcher.core.ignores import IGNORE_FILE
from birdwatcher.core.run import RunResult
from birdwatcher.ui.system import (
    Editor,
    choose_folder_dialog,
    desktop_editors,
    show_in_file_browser,
    system_prefers_dark,
)

DARK_THEME, LIGHT_THEME = "textual-dark", "textual-light"  # for THEME_AUTO
from birdwatcher.ui.tui.findings import FindingsScreen
from birdwatcher.ui.tui.setup import SetupScreen


def check_with_every_check(course_dir):
    """
    Run every registered check over a course folder.

    Args:
        course_dir (Path): The course folder.

    Returns:
        RunResult: The results of checks.ALL_CHECKS.
    """
    return check_course(course_dir, ALL_CHECKS)


class BirdwatcherApp(App):
    """
    The Birdwatcher window.

    It opens on the setup page when no course folder is saved, or when the saved
    folder can no longer be used (the page then shows the saved path and the
    reason). The setup page lists the recent course folders (most recent
    first; choosing one switches to it at once, unless it can no longer be
    used, which the page explains), takes another course folder's path, and
    offers the editors (those not found on this computer cannot be chosen; the
    saved one is selected). Enter or the Save button checks that the folder
    can be used, saves it with the chosen editor, and checks the course. An
    unusable folder is explained on the page and not saved. The Browse button
    (or Ctrl+O) picks the folder in a folder picker instead, starting at the
    typed path; a picked folder is filled in and saved the same way, and a
    cancelled picker changes nothing. If no picker can be shown, the page says
    so and typing the path still works. Every chosen folder goes to the front
    of the recent list. From the findings, s reopens the setup page filled in
    with the current folder, and Escape there returns without changes.

    Theme: the setup page also lists the color themes, starting with "Match
    the system", the default, which shows textual-light in the system's light
    mode and textual-dark otherwise. Choosing a theme there shows it at once;
    Save keeps it and Escape puts the previous one back. A theme chosen from
    Textual's command palette (Ctrl+P) is saved too.

    The findings view's subtitle names the course folder and the number of
    findings. Checking runs in a background thread, so the window stays
    responsive; a run that fails shows its error in the window instead of
    closing it. Files open in the chosen editor; one that cannot go to a line
    opens the file at the top and a notification names the line. Failures to
    open the editor are reported as notifications.

    Fixing: a finding with a fix shows the change (before and after) and a FIX
    button at the bottom of its panel; the button or f applies it to the file
    and checks again. A fix that no longer applies (the line changed) is
    refused with a notification. Fixed findings are remembered per course
    folder in the fix log, across launches, and stay in the list in their
    finding's place, labelled FIXED, with the change, whether the re-check
    still reports the problem, and buttons (with keys): View in editor (e)
    opens the fixed line, View on site (w) opens the section the fixed link
    leads to on the published site (only when its address is known), Undo (u)
    puts the original text back and checks again (refused if the line changed
    since), and Clear (c) forgets the fix without touching the file. C clears
    every fixed finding of the course. The footer lists only the keys that
    apply to the selected row.

    Ignoring: i or the Ignore button on an open finding opens a dialog that
    names it and takes an optional reason (for an error, it also warns that
    readers are affected); confirming hides the finding, cancelling changes
    nothing. Ignores are remembered per course folder, across launches, and
    match a finding by its check, file and message, so they survive line
    changes. The subtitle counts ignored findings; h shows them in place,
    labelled IGNORED with their reason, and i (or Un-ignore) on one brings it
    back at once. Fixed findings cannot be ignored.

    Args:
        config_path (Path): The settings file to read and save.
        check (Callable[[Path], RunResult]): Checks a course folder; called
            when the findings view opens and on every re-run. May raise.
            Defaults to check_with_every_check.
        editors (Mapping[str, Editor] | None): The editors on offer, by id, in
            display order; None means system.desktop_editors(). Findings about
            a whole file open at line 1.
        choose_folder (Callable[[Path | None], Path | None]): Shows a folder
            picker starting at a folder; returns the choice, or None when
            cancelled. May raise OSError when no picker can be shown.
        open_url (Callable[[str], object]): Opens an address in a browser.
        show_folder (Callable[[Path], object]): Shows a folder in the file
            browser; used to open findings about folders (Enter, o or a second
            click), which the editor cannot show.
        fix_log_path (Path | None): The fix log; None means fix_log.FIX_LOG_FILE
            in the settings file's folder.
        ignore_path (Path | None): The ignore list; None means
            ignores.IGNORE_FILE in the settings file's folder.
        prefers_dark (Callable[[], bool | None]): Whether the system is in
            dark mode (None when unknown). Defaults to
            system.system_prefers_dark.
    """

    TITLE = "Birdwatcher"
    CSS_PATH = "birdwatcher.tcss"

    def __init__(
        self,
        config_path: Path,
        *,
        check: Callable[[Path], RunResult] = check_with_every_check,
        editors: Mapping[str, Editor] | None = None,
        choose_folder: Callable[[Path | None], Path | None] = choose_folder_dialog,
        open_url: Callable[[str], object] = webbrowser.open,
        show_folder: Callable[[Path], object] = show_in_file_browser,
        fix_log_path: Path | None = None,
        ignore_path: Path | None = None,
        prefers_dark: Callable[[], bool | None] = system_prefers_dark,
    ):
        super().__init__()
        self._prefers_dark = prefers_dark
        self._own_theme = None  # the theme this app last set itself
        self._ignore_path = (
            Path(config_path).with_name(IGNORE_FILE)
            if ignore_path is None
            else Path(ignore_path)
        )
        self._open_url = open_url
        self._show_folder = show_folder
        self._fix_log_path = (
            Path(config_path).with_name(FIX_LOG_FILE)
            if fix_log_path is None
            else Path(fix_log_path)
        )
        self._config_path = Path(config_path)
        self._check = check
        self._editors = desktop_editors() if editors is None else dict(editors)
        self._choose_folder = choose_folder
        self._config = None
        self._findings = None

    def on_mount(self):
        self._config = load_config(self._config_path)
        config = self._config
        self._apply_theme(THEME_AUTO if config is None else config.theme)
        self.theme_changed_signal.subscribe(self, self._theme_changed)
        problem = course_problem(config.course_dir) if config else None
        if config is None or problem:
            saved = config.course_dir if config else None
            self.push_screen(self._setup(saved, problem, False), self._course_chosen)
        else:
            self._show_findings(config.course_dir)

    def action_open_setup(self):
        """Open the setup page, filled in with the current course folder."""
        current = self._findings.course_dir if self._findings else None
        self.push_screen(self._setup(current, None, True), self._course_chosen)

    def _setup(self, course_dir, problem, can_cancel):
        config = self._config
        return SetupScreen(
            course_dir,
            problem,
            can_cancel=can_cancel,
            choose_folder=self._choose_folder,
            recent=() if config is None else config.recent,
            editors=self._editors,
            editor=DEFAULT_EDITOR if config is None else config.editor,
            themes=sorted(self.available_themes),
            theme=THEME_AUTO if config is None else config.theme,
            preview_theme=self._apply_theme,
        )

    def _course_chosen(self, choice):
        if choice is None:
            # Cancelled: undo any theme the page was previewing.
            self._apply_theme(
                THEME_AUTO if self._config is None else self._config.theme
            )
            return
        base = self._config or Config(course_dir=choice.course_dir, recent=())
        self._config = with_course(
            replace(base, editor=choice.editor, theme=choice.theme), choice.course_dir
        )
        save_config(self._config_path, self._config)
        self._apply_theme(choice.theme)
        self._show_findings(choice.course_dir)

    def _apply_theme(self, setting):
        """Show a theme setting: a theme's name, or THEME_AUTO for the system's
        light or dark mode (dark when it cannot be told)."""
        if setting in self.available_themes:
            name = setting
        else:
            name = LIGHT_THEME if self._prefers_dark() is False else DARK_THEME
        self._own_theme = name
        self.theme = name

    def _theme_changed(self, theme):
        # The signal arrives after the change, so compare names rather than set
        # a flag: a theme this app did not set came from the user (Ctrl+P).
        if theme.name == self._own_theme:
            return
        self._own_theme = theme.name
        if self._config is not None:
            self._config = replace(self._config, theme=theme.name)
            save_config(self._config_path, self._config)

    def _open_file(self, path, line):
        """Open a file at a line in the chosen editor (see the class docs)."""
        editor_id = DEFAULT_EDITOR if self._config is None else self._config.editor
        editor = self._editors.get(editor_id)
        if editor is None or not editor.available:
            raise FileNotFoundError(f"the chosen editor ({editor_id}) was not found")
        editor.open(path, line)
        if not editor.opens_at_line and line > 1:
            self.notify(f"{editor.name} opens files at the top: look at line {line}.")

    def _show_findings(self, course_dir):
        if self._findings is None:
            self._findings = FindingsScreen(
                course_dir,
                self._check,
                self._open_file,
                self._open_url,
                self._show_folder,
                self._fix_log_path,
                self._ignore_path,
            )
            self.push_screen(self._findings)
        else:
            self._findings.change_course(course_dir)
