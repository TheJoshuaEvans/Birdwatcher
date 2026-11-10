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
from collections.abc import Callable
from pathlib import Path

from textual.app import App

from birdwatcher.checks import ALL_CHECKS
from birdwatcher.core.config import Config, load_config, save_config
from birdwatcher.core.course import check_course, course_problem
from birdwatcher.core.fix_log import FIX_LOG_FILE
from birdwatcher.core.ignores import IGNORE_FILE
from birdwatcher.core.run import RunResult
from birdwatcher.ui.system import (
    choose_folder_dialog,
    open_in_vscode,
    show_in_file_browser,
)
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
    reason). The setup page takes the course folder's path; Enter or the Save
    button checks that the folder can be used, saves it, and checks the course.
    An unusable folder is explained on the page and not saved. The Browse
    button (or Ctrl+O) picks the folder in a folder picker instead, starting at
    the typed path; a picked folder is filled in and saved the same way, and a
    cancelled picker changes nothing. If no picker can be shown, the page says
    so and typing the path still works. From the findings, s reopens the setup
    page filled in with the current folder, and Escape there returns without
    changes.

    The findings view's subtitle names the course folder and the number of
    findings. Checking runs in a background thread, so the window stays
    responsive; a run that fails shows its error in the window instead of
    closing it. Failures to open the editor are reported as notifications.

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
        open_in_editor (Callable[[Path, int], object]): Opens a file at a
            1-based line. Findings about a whole file open at line 1.
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
    """

    TITLE = "Birdwatcher"
    CSS_PATH = "birdwatcher.tcss"

    def __init__(
        self,
        config_path: Path,
        *,
        check: Callable[[Path], RunResult] = check_with_every_check,
        open_in_editor: Callable[[Path, int], object] = open_in_vscode,
        choose_folder: Callable[[Path | None], Path | None] = choose_folder_dialog,
        open_url: Callable[[str], object] = webbrowser.open,
        show_folder: Callable[[Path], object] = show_in_file_browser,
        fix_log_path: Path | None = None,
        ignore_path: Path | None = None,
    ):
        super().__init__()
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
        self._open_in_editor = open_in_editor
        self._choose_folder = choose_folder
        self._findings = None

    def on_mount(self):
        config = load_config(self._config_path)
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
        return SetupScreen(
            course_dir,
            problem,
            can_cancel=can_cancel,
            choose_folder=self._choose_folder,
        )

    def _course_chosen(self, course_dir):
        if course_dir is None:
            return
        save_config(self._config_path, Config(course_dir=course_dir))
        self._show_findings(course_dir)

    def _show_findings(self, course_dir):
        if self._findings is None:
            self._findings = FindingsScreen(
                course_dir,
                self._check,
                self._open_in_editor,
                self._open_url,
                self._show_folder,
                self._fix_log_path,
                self._ignore_path,
            )
            self.push_screen(self._findings)
        else:
            self._findings.change_course(course_dir)
