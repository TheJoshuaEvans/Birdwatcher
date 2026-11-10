"""
Interactive terminal app: choose the course, browse the findings, open them,
re-run the checks.

The setup page takes the path of the local course repository. The findings
view shows every finding in a table on the left and the highlighted finding on
the right: its check, severity, location, message, and the source lines around
it. Mouse and keyboard both work:

- Click a finding (or move to it with the arrow keys) to show it.
- Click it again, or press Enter or o, to open the file at that line in the
  editor.
- r runs the checks again, so a fix can be confirmed without leaving the app.
- s opens the setup page, to choose another course folder.
- q quits.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from birdwatcher.config import Config, load_config, save_config
from birdwatcher.course import DOCS_FOLDER, check_course, course_problem
from birdwatcher.findings import Severity
from birdwatcher.run import RunResult

EDITOR_COMMAND = "code"  # VS Code's command-line launcher
CONTEXT_LINES = 6  # source lines shown above and below a finding
SEVERITY_STYLES = {
    Severity.ERROR: ("ERROR", "bold red"),
    Severity.WARNING: ("WARNING", "bold yellow"),
    Severity.INFO: ("INFO", "bold cyan"),
}
NO_FINDINGS = "No findings. Every check came back clean."
SETUP_INTRO = (
    "Birdwatcher checks a local clone of the course repository. Enter the path "
    f"of its folder: the one that contains {DOCS_FOLDER}/."
)
EMPTY_PATH = "Enter the path of the course repository's folder."


def open_in_vscode(path, line):
    """
    Open a file in VS Code with the cursor on a line, without waiting for it.

    Args:
        path (Path): The file.
        line (int): The 1-based line number.

    Raises:
        FileNotFoundError: VS Code's `code` command is not on the PATH. (On a
            Mac, VS Code's command "Shell Command: Install 'code' command in
            PATH" adds it.)
    """
    command = shutil.which(EDITOR_COMMAND)
    if command is None:
        raise FileNotFoundError(
            f"VS Code's '{EDITOR_COMMAND}' command is not on the PATH"
        )
    subprocess.Popen(
        [command, "--goto", f"{path}:{line}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class BirdwatcherApp(App):
    """
    The Birdwatcher window.

    It opens on the setup page when no course folder is saved, or when the saved
    folder can no longer be used (the page then shows the saved path and the
    reason). The setup page takes the course folder's path; Enter or the Save
    button checks that the folder can be used, saves it, and checks the course.
    An unusable folder is explained on the page and not saved. From the
    findings, s reopens the setup page filled in with the current folder, and
    Escape there returns without changes.

    The findings view's subtitle names the course folder and the number of
    findings. Checking runs in a background thread, so the window stays
    responsive; a run that fails shows its error in the window instead of
    closing it. Failures to open the editor are reported as notifications.

    Args:
        config_path (Path): The settings file to read and save.
        check (Callable[[Path], RunResult]): Checks a course folder; called
            when the findings view opens and on every re-run. May raise.
        open_in_editor (Callable[[Path, int], object]): Opens a file at a
            1-based line. Findings about a whole file open at line 1.
    """

    TITLE = "Birdwatcher"
    CSS = """
    #findings { width: 45%; }
    #detail-scroll { width: 1fr; border-left: tall $accent; padding: 0 1; }
    #setup { padding: 1 2; max-width: 100; }
    #setup-title { text-style: bold; margin-bottom: 1; }
    #setup-intro { margin-bottom: 1; }
    #setup-error { color: $error; margin: 1 0; }
    """

    def __init__(
        self,
        config_path: Path,
        *,
        check: Callable[[Path], RunResult] = check_course,
        open_in_editor: Callable[[Path, int], object] = open_in_vscode,
    ):
        super().__init__()
        self._config_path = Path(config_path)
        self._check = check
        self._open_in_editor = open_in_editor
        self._findings = None

    def on_mount(self):
        config = load_config(self._config_path)
        problem = course_problem(config.course_dir) if config else None
        if config is None or problem:
            saved = config.course_dir if config else None
            self.push_screen(
                SetupScreen(saved, problem, can_cancel=False), self._course_chosen
            )
        else:
            self._show_findings(config.course_dir)

    def action_open_setup(self):
        """Open the setup page, filled in with the current course folder."""
        current = self._findings.course_dir if self._findings else None
        self.push_screen(
            SetupScreen(current, None, can_cancel=True), self._course_chosen
        )

    def _course_chosen(self, course_dir):
        if course_dir is None:
            return
        save_config(self._config_path, Config(course_dir=course_dir))
        self._show_findings(course_dir)

    def _show_findings(self, course_dir):
        if self._findings is None:
            self._findings = FindingsScreen(
                course_dir, self._check, self._open_in_editor
            )
            self.push_screen(self._findings)
        else:
            self._findings.change_course(course_dir)


class SetupScreen(Screen):
    """
    The setup page: asks for the course folder, and closes with it once it can
    be used (or with None when cancelled).

    Args:
        course_dir (Path | None): The path to fill in.
        problem (str | None): Why that path cannot be used, shown at once.
        can_cancel (bool): Whether Escape closes the page without a choice.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Back"),
        Binding("ctrl+q", "app.quit", "Quit"),
    ]

    def __init__(self, course_dir, problem, *, can_cancel):
        super().__init__()
        self._course_dir = course_dir
        self._problem = problem
        self._can_cancel = can_cancel

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="setup"):
            yield Static("Course folder", id="setup-title")
            yield Static(SETUP_INTRO, id="setup-intro")
            yield Input(
                value="" if self._course_dir is None else str(self._course_dir),
                placeholder=r"C:\path\to\CS212-CourseMaterials",
                id="course-dir",
            )
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
        self._save()

    def _save(self):
        # Explorer's "Copy as path" adds quotes; "~" is common on a Mac.
        text = self.query_one("#course-dir", Input).value.strip().strip('"')
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


class FindingsScreen(Screen):
    """
    The findings view for one course folder; checks it as soon as it opens.

    Args:
        course_dir (Path): The course folder.
        check (Callable[[Path], RunResult]): Checks a course folder.
        open_in_editor (Callable[[Path, int], object]): Opens a file at a line.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("o", "open_editor", "Open in editor"),
        Binding("r", "rerun", "Re-run checks"),
        Binding("s", "app.open_setup", "Setup"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, course_dir, check, open_in_editor):
        super().__init__()
        self.course_dir = course_dir
        self._check = check
        self._open_in_editor = open_in_editor
        self._run = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield DataTable(id="findings", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="detail-scroll"):
                yield Static("Checking the course...", id="detail")
        yield Footer()

    def on_mount(self):
        self.query_one(DataTable).add_columns("Severity", "File", "Line")
        self._start_checking()

    def change_course(self, course_dir):
        """Switch to another course folder and check it."""
        self.course_dir = course_dir
        self._start_checking()

    def _start_checking(self):
        self.app.sub_title = f"{self.course_dir}  ·  checking..."
        self._check_in_background(self.course_dir)

    @work(thread=True, exclusive=True)
    def _check_in_background(self, course_dir):
        # A thread worker that raises would close the app, so every failure is
        # handed to the window instead.
        try:
            run = self._check(course_dir)
        except Exception as error:  # noqa: BLE001
            self.app.call_from_thread(self._show_error, error)
        else:
            self.app.call_from_thread(self._show, run)

    def _show_error(self, error):
        self.app.sub_title = f"{self.course_dir}  ·  check failed"
        self._detail().update(Text(f"Could not check the course: {error}", style="red"))

    def _show(self, run):
        self._run = run
        table = self.query_one(DataTable)
        previous_row = table.cursor_row
        table.clear()
        for finding in run.findings:
            label, style = SEVERITY_STYLES[finding.severity]
            line = "" if finding.line is None else str(finding.line)
            table.add_row(Text(label, style=style), finding.path, line)

        count = len(run.findings)
        noun = "finding" if count == 1 else "findings"
        self.app.sub_title = f"{run.course_dir}  ·  {count} {noun}"

        table.focus()
        if not run.findings:
            self._detail().update(NO_FINDINGS)
            return
        table.move_cursor(row=min(max(previous_row, 0), count - 1))
        self._show_finding(table.cursor_row)

    def _detail(self):
        return self.query_one("#detail", Static)

    def _finding(self, row):
        if self._run is None or not 0 <= row < len(self._run.findings):
            return None
        return self._run.findings[row]

    def _show_finding(self, row):
        finding = self._finding(row)
        if finding is None:
            return
        label, style = SEVERITY_STYLES[finding.severity]
        titles = {result.check.id: result.check.title for result in self._run.results}
        header = Text()
        header.append(f" {label} ", style=f"reverse {style}")
        header.append(f"  {titles.get(finding.check, finding.check)}\n\n", style="bold")
        header.append(finding.path, style="underline")
        header.append(f"  line {finding.line}" if finding.line else "  whole file")
        header.append("\n\n")
        header.append(finding.message)
        header.append("\n")
        parts = [header]
        excerpt = self._excerpt(finding)
        if excerpt is not None:
            parts.append(excerpt)
        self._detail().update(Group(*parts))

    def _excerpt(self, finding):
        source = self._run.file_of(finding)
        if finding.line is None or not source.is_file():
            return None
        lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
        first = max(1, finding.line - CONTEXT_LINES)
        last = min(len(lines), finding.line + CONTEXT_LINES)
        return Syntax(
            "\n".join(lines[first - 1 : last]),
            "markdown",
            line_numbers=True,
            start_line=first,
            highlight_lines={finding.line},
            word_wrap=True,
            theme="monokai",
        )

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        self._show_finding(event.cursor_row)

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        self._open(event.cursor_row)

    def action_open_editor(self):
        self._open(self.query_one(DataTable).cursor_row)

    def _open(self, row):
        finding = self._finding(row)
        if finding is None:
            return
        try:
            self._open_in_editor(self._run.file_of(finding), finding.line or 1)
        except OSError as error:
            self.notify(f"Could not open the editor: {error}", severity="error")

    def action_rerun(self):
        self._start_checking()
