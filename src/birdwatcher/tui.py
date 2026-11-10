"""
Interactive terminal app: browse the findings, open them, re-run the checks.

The window shows every finding in a table on the left and the highlighted
finding on the right: its check, severity, location, message, and the source
lines around it. Mouse and keyboard both work:

- Click a finding (or move to it with the arrow keys) to show it.
- Click it again, or press Enter or o, to open the file at that line in the
  editor.
- g opens the finding's source on GitHub, at the checked commit.
- r runs the checks again, so a fix can be confirmed without leaving the app.
- q quits.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import shutil
import subprocess
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Static

from birdwatcher.findings import Severity
from birdwatcher.run import RunResult

EDITOR_COMMAND = "code"  # VS Code's command-line launcher
SHORT_COMMIT = 7  # characters of a commit SHA shown to people
CONTEXT_LINES = 6  # source lines shown above and below a finding
SEVERITY_STYLES = {
    Severity.ERROR: ("ERROR", "bold red"),
    Severity.WARNING: ("WARNING", "bold yellow"),
    Severity.INFO: ("INFO", "bold cyan"),
}
NO_FINDINGS = "No findings. Every check came back clean."


@dataclass(frozen=True)
class Checked:
    """
    One checked copy of the course.

    Attributes:
        root (Path): The folder holding the course files that were checked.
        run (RunResult): The results of checking them.
    """

    root: Path
    run: RunResult


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
    The Birdwatcher window. Its subtitle names the repository, the checked commit
    and the number of findings, and flags a cached copy that may be out of date.

    Loading runs in a background thread, so the window appears at once and stays
    responsive. A load that fails (for example, the course cannot be fetched)
    shows its error in the window instead of closing it. Failures to open the
    editor or browser are reported as notifications.

    Args:
        load (Callable[[], Checked]): Fetches and checks the course; called at
            start and again on every re-run. May raise.
        open_in_editor (Callable[[Path, int], object]): Opens a file at a
            1-based line. Findings about a whole file open at line 1.
        open_url (Callable[[str], object]): Opens a URL in a browser.
    """

    TITLE = "Birdwatcher"
    CSS = """
    #findings { width: 45%; }
    #detail-scroll { width: 1fr; border-left: tall $accent; padding: 0 1; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("o", "open_editor", "Open in editor"),
        Binding("g", "open_github", "GitHub"),
        Binding("r", "rerun", "Re-run checks"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        load: Callable[[], Checked],
        *,
        open_in_editor: Callable[[Path, int], object] = open_in_vscode,
        open_url: Callable[[str], object] = webbrowser.open,
    ):
        super().__init__()
        self._load = load
        self._open_in_editor = open_in_editor
        self._open_url = open_url
        self._checked = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield DataTable(id="findings", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="detail-scroll"):
                yield Static("Fetching the course...", id="detail")
        yield Footer()

    def on_mount(self):
        self.query_one(DataTable).add_columns("Severity", "File", "Line")
        self._start_loading()

    def _start_loading(self):
        self.sub_title = "checking..."
        self._load_in_background()

    @work(thread=True, exclusive=True)
    def _load_in_background(self):
        # A thread worker that raises would close the app, so every failure is
        # handed to the window instead.
        try:
            checked = self._load()
        except Exception as error:  # noqa: BLE001
            self.call_from_thread(self._show_error, error)
        else:
            self.call_from_thread(self._show, checked)

    def _show_error(self, error):
        self.sub_title = "check failed"
        self._detail().update(Text(f"Could not check the course: {error}", style="red"))

    def _show(self, checked):
        self._checked = checked
        run = checked.run
        table = self.query_one(DataTable)
        previous_row = table.cursor_row
        table.clear()
        for finding in run.findings:
            label, style = SEVERITY_STYLES[finding.severity]
            line = "" if finding.line is None else str(finding.line)
            table.add_row(Text(label, style=style), finding.path, line)

        count = len(run.findings)
        subtitle = f"{run.repo} @ {run.commit[:SHORT_COMMIT]}  ·  "
        subtitle += f"{count} {'finding' if count == 1 else 'findings'}"
        if run.stale:
            subtitle += "  ·  cached copy, may be out of date"
        self.sub_title = subtitle

        table.focus()
        if not run.findings:
            self._detail().update(NO_FINDINGS)
            return
        table.move_cursor(row=min(max(previous_row, 0), count - 1))
        self._show_finding(table.cursor_row)

    def _detail(self):
        return self.query_one("#detail", Static)

    def _finding(self, row):
        if self._checked is None or not 0 <= row < len(self._checked.run.findings):
            return None
        return self._checked.run.findings[row]

    def _show_finding(self, row):
        finding = self._finding(row)
        if finding is None:
            return
        label, style = SEVERITY_STYLES[finding.severity]
        titles = {
            result.check.id: result.check.title for result in self._checked.run.results
        }
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
        source = self._checked.root / finding.path
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
            self._open_in_editor(self._checked.root / finding.path, finding.line or 1)
        except OSError as error:
            self.notify(f"Could not open the editor: {error}", severity="error")

    def action_open_github(self):
        finding = self._finding(self.query_one(DataTable).cursor_row)
        if finding is not None:
            self._open_url(self._checked.run.source_url(finding))

    def action_rerun(self):
        self._start_loading()
