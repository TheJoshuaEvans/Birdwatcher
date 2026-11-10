"""
The findings view: every finding in a table, the highlighted one in detail,
with fixing, undoing and clearing of fixes.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, HorizontalScroll, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Static

from birdwatcher.core.findings import Finding
from birdwatcher.core.fix_log import FixedFinding, load_fixed, save_fixed
from birdwatcher.core.fixes import FixError, apply_fix, undo_fix
from birdwatcher.ui.severity import SEVERITY_STYLES
from birdwatcher.ui.tui.divider import Divider

CONTEXT_LINES = 6  # source lines shown above and below a finding
MIN_PANE_WIDTH = 20  # columns each side keeps when the divider is dragged
NO_FINDINGS = "No findings. Every check came back clean."
FIXED_LABEL = ("FIXED", "bold green")
# Each action button and the screen action it runs
BUTTON_ACTIONS = {
    "fix": "fix",
    "view-editor": "view_editor",
    "view-site": "view_site",
    "undo": "undo",
    "clear": "clear",
}


@dataclass(frozen=True)
class Row:
    """
    One row of the findings list.

    Attributes:
        finding (Finding): The finding.
        fixed (FixedFinding | None): Its fix log entry when it was fixed; None
            for an open finding from the latest run.
    """

    finding: Finding
    fixed: FixedFinding | None = None


class FindingsScreen(Screen):
    """
    The findings view for one course folder; checks it as soon as it opens.
    See BirdwatcherApp for the behaviour as a whole.

    Args:
        course_dir (Path): The course folder.
        check (Callable[[Path], RunResult]): Checks a course folder.
        open_in_editor (Callable[[Path, int], object]): Opens a file at a line.
        open_url (Callable[[str], object]): Opens an address in a browser.
        show_folder (Callable[[Path], object]): Shows a folder in the file browser.
        fix_log_path (Path): The fix log.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f", "fix", "Fix"),
        Binding("e", "view_editor", "View in editor"),
        Binding("w", "view_site", "View on site"),
        Binding("u", "undo", "Undo"),
        Binding("c", "clear", "Clear"),
        Binding("C", "clear_all", "Clear all fixed"),
        Binding("o", "open_editor", "Open in editor"),
        Binding("r", "rerun", "Re-run checks"),
        Binding("s", "app.open_setup", "Setup"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(
        self, course_dir, check, open_in_editor, open_url, show_folder, fix_log_path
    ):
        super().__init__()
        self.course_dir = course_dir
        self._check = check
        self._open_in_editor = open_in_editor
        self._open_url = open_url
        self._show_folder = show_folder
        self._fix_log_path = fix_log_path
        self._run = None
        self._fixed = []
        self._rows = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield DataTable(id="findings", cursor_type="row", zebra_stripes=True)
            yield Divider("#findings", min_width=MIN_PANE_WIDTH)
            with VerticalScroll(id="detail-scroll"):
                yield Static("Checking the course...", id="detail")
                # Source lines keep their shape and scroll sideways; the
                # message above wraps to the panel.
                with HorizontalScroll(id="excerpt-scroll"):
                    yield Static(id="excerpt")
                yield Static(id="fix-summary")
                with Horizontal(id="actions"):
                    yield Button("FIX", variant="success", id="fix")
                    yield Button("View in editor", id="view-editor")
                    yield Button("View on site", id="view-site")
                    yield Button("Undo", variant="warning", id="undo")
                    yield Button("Clear", id="clear")
        yield Footer()

    def on_mount(self):
        self.query_one(DataTable).add_columns("Severity", "Line", "File")
        self._fixed = load_fixed(self._fix_log_path, self.course_dir)
        self._show_row(None)
        self._start_checking()

    def change_course(self, course_dir):
        """Switch to another course folder and check it."""
        self.course_dir = course_dir
        self._fixed = load_fixed(self._fix_log_path, self.course_dir)
        self._start_checking()

    # Checking

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
        self._show_row(None)
        self._detail().update(Text(f"Could not check the course: {error}", style="red"))

    def _show(self, run):
        self._run = run
        self._show_rows()

    # The list

    def _show_rows(self):
        open_rows = [Row(finding) for finding in self._run.findings]
        fixed_rows = [Row(entry.finding, entry) for entry in self._fixed]
        self._rows = sorted(open_rows + fixed_rows, key=_row_order)

        table = self.query_one(DataTable)
        previous_row = table.cursor_row
        table.clear()
        for row in self._rows:
            label, style = (
                FIXED_LABEL if row.fixed else SEVERITY_STYLES[row.finding.severity]
            )
            line = "" if row.finding.line is None else str(row.finding.line)
            table.add_row(
                Text(label, style=style),
                Text(line, justify="right"),
                row.finding.path,
            )

        count = len(open_rows)
        subtitle = (
            f"{self.course_dir}  ·  {count} {'finding' if count == 1 else 'findings'}"
        )
        if fixed_rows:
            subtitle += f"  ·  {len(fixed_rows)} fixed"
        self.app.sub_title = subtitle

        table.focus()
        if not self._rows:
            self._show_row(None)
            self._detail().update(NO_FINDINGS)
            self.refresh_bindings()
            return
        table.move_cursor(row=min(max(previous_row, 0), len(self._rows) - 1))
        self._show_row(self._row(table.cursor_row))

    def _row(self, index):
        return self._rows[index] if 0 <= index < len(self._rows) else None

    def _current(self):
        return self._row(self.query_one(DataTable).cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        self._show_row(self._row(event.cursor_row))

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        self._open(self._row(event.cursor_row))

    # The detail panel

    def _detail(self):
        return self.query_one("#detail", Static)

    def _show_row(self, row):
        """Fill the detail panel for a row (None empties it)."""
        summary = self.query_one("#fix-summary", Static)
        buttons = {name: self.query_one(f"#{name}", Button) for name in BUTTON_ACTIONS}
        for button in buttons.values():
            button.display = False
        summary.display = False
        self._show_excerpt(None)
        self.refresh_bindings()
        if row is None:
            self.query_one("#actions").display = False
            return

        finding = row.finding
        self._detail().update(self._header(row))
        self._show_excerpt(self._excerpt(finding))
        fix = finding.fix
        if row.fixed is None and fix is not None:
            summary.update(_change("Suggested fix (f):", fix))
            summary.display = True
            buttons["fix"].display = True
        elif row.fixed is not None:
            summary.update(self._fixed_summary(row))
            summary.display = True
            buttons["view-editor"].display = True
            buttons["view-site"].display = _site_url(row) is not None
            buttons["undo"].display = True
            buttons["clear"].display = True
        self.query_one("#actions").display = any(b.display for b in buttons.values())

    def _header(self, row):
        finding = row.finding
        label, style = FIXED_LABEL if row.fixed else SEVERITY_STYLES[finding.severity]
        titles = (
            {}
            if self._run is None
            else {result.check.id: result.check.title for result in self._run.results}
        )
        header = Text()
        header.append(f" {label} ", style=f"reverse {style}")
        header.append(f"  {titles.get(finding.check, finding.check)}\n\n", style="bold")
        header.append(finding.path, style="underline")
        header.append(f"  line {finding.line}" if finding.line else "  whole file")
        header.append("\n\n")
        if row.fixed:
            when = row.fixed.fixed_at.astimezone().strftime("%Y-%m-%d %H:%M")
            header.append(f"Fixed {when}. It was: ", style="italic")
        header.append(finding.message)
        header.append("\n")
        return header

    def _fixed_summary(self, row):
        summary = _change("The fix:", row.finding.fix)
        summary.append("\nRe-check: ", style="bold")
        if self._run is None:
            summary.append("not run yet")
        elif self._still_reported(row.finding):
            summary.append("still reported", style="bold red")
        else:
            summary.append("passes", style="bold green")
        return summary

    def _still_reported(self, finding):
        return any(
            (other.check, other.path, other.line)
            == (finding.check, finding.path, finding.line)
            for other in self._run.findings
        )

    def _show_excerpt(self, syntax):
        excerpt = self.query_one("#excerpt", Static)
        excerpt.display = syntax is not None
        excerpt.update("" if syntax is None else syntax)

    def _excerpt(self, finding):
        source = self.course_dir / finding.path
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
            word_wrap=False,
            theme="monokai",
        )

    # Actions

    def check_action(self, action, parameters):
        row = self._current() if self.is_mounted else None
        is_fixed = row is not None and row.fixed is not None
        if action == "fix":
            return row is not None and not is_fixed and row.finding.fix is not None
        if action in ("view_editor", "undo", "clear"):
            return is_fixed
        if action == "view_site":
            return is_fixed and _site_url(row) is not None
        if action == "clear_all":
            return bool(self._fixed)
        return True

    def on_button_pressed(self, event: Button.Pressed):
        action = BUTTON_ACTIONS.get(event.button.id)
        if action is not None:
            event.stop()
            # The action methods directly: Screen.run_action is a coroutine.
            getattr(self, f"action_{action}")()

    def action_open_editor(self):
        self._open(self._current())

    def _open(self, row):
        if row is None:
            return
        target = self.course_dir / row.finding.path
        if target.is_dir():
            try:
                self._show_folder(target)
            except OSError as error:
                self.notify(f"Could not show the folder: {error}", severity="error")
            return
        self._edit(target, row.finding.line or 1)

    def _edit(self, path, line):
        try:
            self._open_in_editor(path, line)
        except OSError as error:
            self.notify(f"Could not open the editor: {error}", severity="error")

    def action_fix(self):
        row = self._current()
        if row is None or row.fixed is not None or row.finding.fix is None:
            return
        try:
            apply_fix(self.course_dir / row.finding.path, row.finding.fix)
        except FixError as error:
            self.notify(f"Not fixed: {error}", severity="error")
            return
        self._fixed.append(FixedFinding(row.finding, datetime.now(UTC)))
        self._save_fixed()
        self._start_checking()

    def action_undo(self):
        row = self._current()
        if row is None or row.fixed is None:
            return
        try:
            undo_fix(self.course_dir / row.finding.path, row.finding.fix)
        except FixError as error:
            self.notify(f"Not undone: {error}", severity="error")
            return
        self._fixed.remove(row.fixed)
        self._save_fixed()
        self._start_checking()

    def action_clear(self):
        row = self._current()
        if row is None or row.fixed is None:
            return
        self._fixed.remove(row.fixed)
        self._save_fixed()
        self._show_rows()

    def action_clear_all(self):
        self._fixed = []
        self._save_fixed()
        self._show_rows()

    def action_view_editor(self):
        row = self._current()
        if row is None or row.fixed is None:
            return
        self._edit(self.course_dir / row.finding.path, row.finding.fix.line)

    def action_view_site(self):
        row = self._current()
        url = None if row is None or row.fixed is None else _site_url(row)
        if url is not None:
            self._open_url(url)

    def action_rerun(self):
        self._start_checking()

    def _save_fixed(self):
        save_fixed(self._fix_log_path, self.course_dir, self._fixed)


def _row_order(row):
    """Path, then line (whole-file first), then check. A fixed row comes before
    an open one on the same line, so the cursor stays on a fix's outcome."""
    finding = row.finding
    line = -1 if finding.line is None else finding.line
    return (finding.path, line, row.fixed is None, finding.check)


def _site_url(row):
    destination = row.finding.fix.destination
    return None if destination is None else destination.url


def _change(title, fix):
    """A fix's change as two lines, before and after, marked - and +."""
    change = Text()
    change.append(f"{title}\n", style="bold")
    change.append(f"- {fix.before}\n", style="red")
    change.append(f"+ {fix.after}\n", style="green")
    return change
