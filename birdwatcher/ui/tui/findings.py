"""
The findings view: every finding in a table, the highlighted one in detail.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from typing import ClassVar

from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from birdwatcher.ui.severity import SEVERITY_STYLES

CONTEXT_LINES = 6  # source lines shown above and below a finding
NO_FINDINGS = "No findings. Every check came back clean."


class FindingsScreen(Screen):
    """
    The findings view for one course folder; checks it as soon as it opens.
    See BirdwatcherApp for the behaviour as a whole.

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
