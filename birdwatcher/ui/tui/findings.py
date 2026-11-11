"""
The findings view: the findings in a grouped tree, the highlighted one in
detail, with fixing (and undoing and clearing fixes) and ignoring.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import threading
from dataclasses import replace
from datetime import UTC, datetime
from typing import ClassVar

from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, HorizontalScroll, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Static,
    Tab,
    Tabs,
    Tree,
)

from birdwatcher.core.config import DEFAULT_SPLIT, SPLIT_RANGE
from birdwatcher.core.findings import Severity
from birdwatcher.core.fix_log import FixedFinding, load_fixed, save_fixed
from birdwatcher.core.fixes import FixError, apply_fix, undo_fix
from birdwatcher.core.ignores import ignore_finding, load_ignores, save_ignores
from birdwatcher.core.run import CheckFinished, CheckProgress, CheckStarted, RunResult
from birdwatcher.ui.tui.divider import Divider
from birdwatcher.ui.tui.fix_all import FixAllDialog
from birdwatcher.ui.tui.grouping import Grouping, group_rows
from birdwatcher.ui.tui.ignore import IgnoreDialog
from birdwatcher.ui.tui.retro import StatusChip
from birdwatcher.ui.tui.rows import Row, row_order
from birdwatcher.ui.tui.search import SearchBox
from birdwatcher.ui.tui.tree import BranchKey, FindingsTree
from birdwatcher.ui.tui.watch import WatchStrip

CONTEXT_LINES = 6  # source lines shown above and below a finding
MIN_PANE_WIDTH = 20  # columns each side keeps when the divider is dragged
NO_FINDINGS = "No findings. Every check came back clean: all quiet in the canopy."
ALL_HIDDEN = "Every finding is hidden by the SHOW chips or the FIND box above."
SEARCH_HINT = "type / to search files, messages and checks"
SEVERITY_CHIP_PREFIX = "show-"  # the severity chips' ids: show-error, show-warning...
TAB_PREFIX = "by-"  # grouping tab ids: by-check, by-severity, by-folder
NARROW_WIDTH = 120  # below this many columns, one pane at a time
NARROW_CLASS, ZOOMED_CLASS = "-narrow", "-zoomed"  # layout states, styled in tcss
# Each action button and the screen action it runs
BUTTON_ACTIONS = {
    "fix": "fix",
    "view-editor": "view_editor",
    "view-site": "view_site",
    "undo": "undo",
    "clear": "clear",
    "ignore": "ignore",
    "unignore": "ignore",
}
STOP_BUTTON = "stop"  # the watch strip's button, which runs action_stop


class FindingsScreen(Screen):
    """
    The findings view for one course folder; checks it as soon as it opens.
    See BirdwatcherApp for the behavior as a whole.

    Args:
        course_dir (Path): The course folder.
        check (Callable[..., RunResult]): Checks a course folder, as
            check(course_dir, on_event=..., should_stop=..., fresh=...),
            passing events and stopping on as core.course.check_course does;
            fresh=True (ctrl+r) asks web sites again instead of reusing
            recent answers. Called on a background thread.
        open_in_editor (Callable[[Path, int], object]): Opens a file at a line.
        open_url (Callable[[str], object]): Opens an address in a browser.
        show_folder (Callable[[Path], object]): Shows a folder in the file browser.
        fix_log_path (Path): The fix log.
        ignore_path (Path): The ignore list.
        split (int): The findings pane's share of the width when the panes are
            side by side, in percent.
        save_split (Callable[[int], object]): Remembers a split the user
            dragged, in percent.
        shown_severities (Set[Severity]): The severities the list starts
            showing; the SHOW chips (or keys 1, 2, 3) change them.
        save_severities (Callable[[frozenset[Severity]], object]): Remembers
            the shown severities whenever they change.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f", "fix", "Fix"),
        Binding("e", "view_editor", "View in editor"),
        Binding("w", "view_site", "View on site"),
        Binding("u", "undo", "Undo"),
        Binding("c", "clear", "Clear"),
        Binding("C", "clear_all", "Clear all fixed"),
        Binding("i", "ignore", "Ignore / un-ignore"),
        Binding("h", "toggle_ignored", "Show/hide ignored"),
        Binding("z", "toggle_zoom", "Zoom"),
        Binding("escape", "unzoom", "Back"),
        Binding("g", "next_grouping", "Grouping"),
        Binding("n", "next_finding", "Next"),
        Binding("p", "previous_finding", "Previous"),
        Binding("o", "open_editor", "Open in editor"),
        Binding("r", "rerun", "Re-run checks"),
        Binding("ctrl+r", "hard_rerun", "Hard refresh"),
        Binding("x", "stop", "Stop checking"),
        Binding("s", "app.open_setup", "Setup"),
        Binding("q", "app.quit", "Quit"),
        Binding("slash", "find", "Find", show=False),
        Binding("minus", "fold_level", "Fold a level", show=False),
        Binding("plus,equals_sign", "unfold_level", "Unfold a level", show=False),
        Binding("1", "toggle_severity('error')", "Errors", show=False),
        Binding("2", "toggle_severity('warning')", "Warnings", show=False),
        Binding("3", "toggle_severity('info')", "Info", show=False),
    ]

    def __init__(
        self,
        course_dir,
        check,
        open_in_editor,
        open_url,
        show_folder,
        fix_log_path,
        ignore_path,
        split=DEFAULT_SPLIT,
        save_split=None,
        shown_severities=frozenset(Severity),
        save_severities=None,
    ):
        super().__init__()
        self._shown_severities = frozenset(shown_severities)
        self._save_severities = save_severities or (lambda severities: None)
        self._split = split
        self._save_split = save_split or (lambda percent: None)
        self._zoomed = False
        self.course_dir = course_dir
        self._check = check
        self._open_in_editor = open_in_editor
        self._open_url = open_url
        self._show_folder = show_folder
        self._fix_log_path = fix_log_path
        self._ignore_path = ignore_path
        self._run = None  # the latest result of every check, merged across runs
        self._stale = set()  # ids of checks whose findings are from an earlier run
        self._generation = 0  # numbers the runs; events from older runs are dropped
        self._stop_asked = threading.Event()  # set by x for the current run
        self._running = False
        self._running_title = None  # the check the current run is on
        self._fixed = []
        self._ignores = []
        self._grouping = Grouping.CHECK
        # A Row.key or BranchKey the next redraw puts the cursor on
        self._next_cursor = None
        self._batch_report = None  # (BranchKey, Text): the last fix-all's outcome

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="findings-pane"):
                yield Tabs(
                    *(
                        Tab(grouping.value.upper(), id=f"{TAB_PREFIX}{grouping.value}")
                        for grouping in Grouping
                    ),
                    id="grouping",
                )
                with Vertical(id="chips"):
                    with Horizontal(classes="chip-row"):
                        yield Static("SHOW", classes="chip-label")
                        for severity in Severity:
                            yield StatusChip(
                                f"{severity.value.upper()} 0",
                                value=severity in self._shown_severities,
                                id=f"{SEVERITY_CHIP_PREFIX}{severity.value}",
                            )
                    with Horizontal(classes="chip-row"):
                        yield Static("", classes="chip-label")
                        yield StatusChip("FIXED 0", value=True, id="show-fixed")
                        yield StatusChip("IGNORED 0", value=False, id="show-ignored")
                    with Horizontal(classes="chip-row", id="find-row"):
                        yield Static("FIND", classes="chip-label")
                        yield SearchBox(placeholder=SEARCH_HINT, id="find")
                yield FindingsTree(id="findings")
                yield WatchStrip(id="watch")
            yield Divider("#findings-pane", min_width=MIN_PANE_WIDTH)
            with VerticalScroll(id="detail-scroll"):
                yield Static("Checking the course...", id="detail")
                # Source lines keep their shape and scroll sideways; the
                # message above wraps to the panel.
                with HorizontalScroll(id="excerpt-scroll"):
                    yield Static(id="excerpt")
                yield Static(id="fix-summary")
                with Horizontal(id="actions"):
                    # Each label shows the button's key.
                    yield Button(Content("[F] FIX"), variant="success", id="fix")
                    yield Button(Content("[E] VIEW IN EDITOR"), id="view-editor")
                    yield Button(Content("[W] VIEW ON SITE"), id="view-site")
                    yield Button(Content("[U] UNDO"), variant="warning", id="undo")
                    yield Button(Content("[C] CLEAR"), id="clear")
                    yield Button(Content("[I] IGNORE"), id="ignore")
                    yield Button(Content("[I] UN-IGNORE"), id="unignore")
        yield Footer()

    def on_mount(self):
        self.query_one("#findings-pane").border_title = Content("[ FINDINGS ]")
        self.query_one("#detail-scroll").border_title = Content("[ DETAIL ]")
        self._load_course_state()
        self._apply_layout()
        self._show_row(None)
        self._start_checking()

    # Layout: side by side when wide; one pane at a time when narrow or zoomed

    def on_resize(self, event):
        self._apply_layout()

    def _apply_layout(self):
        narrow = self.size.width < NARROW_WIDTH
        self.set_class(narrow, NARROW_CLASS)
        self.set_class(self._zoomed, ZOOMED_CLASS)
        # A width set here outranks the stylesheet, so it is set for both cases.
        pane = self.query_one("#findings-pane")
        pane.styles.width = "1fr" if narrow else f"{self._split}%"
        self.refresh_bindings()

    def action_toggle_zoom(self):
        self._zoomed = not self._zoomed
        self._apply_layout()

    def action_unzoom(self):
        if self._zoomed:
            self.action_toggle_zoom()

    def on_divider_released(self, event: Divider.Released):
        # Remember the split as a share of the width, for other window sizes;
        # the pane keeps the exact width it was dragged to until the next resize.
        total = self.query_one("#findings-pane").parent.size.width
        percent = round(event.width * 100 / total)
        self._split = min(max(percent, SPLIT_RANGE.start), SPLIT_RANGE.stop - 1)
        self._save_split(self._split)

    def change_course(self, course_dir):
        """Switch to another course folder and check it."""
        self.course_dir = course_dir
        self._run, self._stale = None, set()  # another course's findings don't apply
        self.query_one(WatchStrip).hide()
        self._load_course_state()
        self._start_checking()

    def _load_course_state(self):
        self._fixed = load_fixed(self._fix_log_path, self.course_dir)
        self._ignores = load_ignores(self._ignore_path, self.course_dir)

    # Checking

    def _start_checking(self, fresh=False):
        # A new generation makes any run still going stop at its next progress
        # report, and drops whatever it sends from then on.
        self._generation += 1
        self._stop_asked = threading.Event()
        self._running = True
        self._running_title = None
        if self._run is not None:
            self._stale = {result.check.id for result in self._run.results}
        self.app.sub_title = f"{self.course_dir}  ·  checking..."
        self.refresh_bindings()
        generation, stop_asked = self._generation, self._stop_asked
        self._check_in_background(
            self.course_dir,
            generation,
            lambda: stop_asked.is_set() or generation != self._generation,
            fresh,
        )

    @work(thread=True)
    def _check_in_background(self, course_dir, generation, should_stop, fresh):
        # A thread worker that raises would close the app, so every failure is
        # handed to the window instead.
        def on_event(event):
            if generation == self._generation:
                self.app.call_from_thread(self._on_run_event, generation, event)

        try:
            run = self._check(
                course_dir, on_event=on_event, should_stop=should_stop, fresh=fresh
            )
        except Exception as error:  # noqa: BLE001
            if generation == self._generation:
                self.app.call_from_thread(self._show_error, generation, error)
        else:
            if generation == self._generation:
                self.app.call_from_thread(self._finish, generation, run)

    def on_unmount(self):
        self._generation += 1  # stops a run still going

    def _on_run_event(self, generation, event):
        if generation != self._generation:
            return
        strip = self.query_one(WatchStrip)
        if isinstance(event, CheckStarted):
            self._running_title = event.check.title
        elif isinstance(event, CheckProgress):
            if not self._stop_asked.is_set():
                strip.show_running(
                    event.check.title, event.done, event.total, event.detail
                )
        elif isinstance(event, CheckFinished):
            self._running_title = None
            self._merge(event.result)
            if not self._stop_asked.is_set():
                strip.hide()
            self._show_rows()

    def _merge(self, result):
        """Put a check's newest result in place of its previous one."""
        self._stale.discard(result.check.id)
        if self._run is None:
            self._run = RunResult(self.course_dir, datetime.now(UTC), (result,))
            return
        results = list(self._run.results)
        ids = [previous.check.id for previous in results]
        if result.check.id in ids:
            results[ids.index(result.check.id)] = result
        else:
            results.append(result)
        self._run = replace(self._run, results=tuple(results))

    def _finish(self, generation, run):
        if generation != self._generation:
            return
        self._running = False
        strip = self.query_one(WatchStrip)
        if run.stopped:
            if self._run is None:
                self._run = replace(run, results=())
            for result in run.results:
                self._merge(result)
            titles = [
                result.check.title
                for result in self._run.results
                if result.check.id in self._stale
            ]
            if self._running_title and self._running_title not in titles:
                titles.append(self._running_title)
            strip.show_stopped(titles)
        else:
            self._run = run
            self._stale = set()
            strip.hide()
        self._running_title = None
        self.refresh_bindings()
        self._show_rows()

    def _show_error(self, generation, error):
        if generation != self._generation:
            return
        self._running = False
        self.query_one(WatchStrip).hide()
        self.refresh_bindings()
        self.app.sub_title = f"{self.course_dir}  ·  check failed"
        self._show_row(None)
        self._detail().update(Text(f"Could not check the course: {error}", style="red"))

    # The list

    def _show_rows(self):
        open_rows, ignored_rows = [], []
        for finding in self._run.findings:
            ignore = self._ignore_for(finding)
            if ignore is None:
                open_rows.append(Row(finding))
            else:
                ignored_rows.append(Row(finding, ignore=ignore))
        fixed_rows = [Row(entry.finding, entry) for entry in self._fixed]
        show_fixed = self.query_one("#show-fixed", Checkbox)
        show_ignored = self.query_one("#show-ignored", Checkbox)
        show_fixed.label = f"FIXED {len(fixed_rows)}"
        show_ignored.label = f"IGNORED {len(ignored_rows)}"
        for severity in Severity:
            count = sum(1 for row in open_rows if row.finding.severity == severity)
            self._severity_chip(severity).label = f"{severity.value.upper()} {count}"
        shown = [
            row
            for row in (
                open_rows
                + (fixed_rows if show_fixed.value else [])
                + (ignored_rows if show_ignored.value else [])
            )
            if row.finding.severity in self._shown_severities
            and self._matches_search(row)
        ]

        count = len(open_rows)
        showing = sum(1 for row in shown if row.is_open)
        found = f"{count} {'finding' if count == 1 else 'findings'}"
        if showing != count:
            found = f"{showing} of {found}"
        subtitle = f"{self.course_dir}  ·  {found}"
        if fixed_rows:
            subtitle += f"  ·  {len(fixed_rows)} fixed"
        if ignored_rows:
            subtitle += f"  ·  {len(ignored_rows)} ignored"
        if self._running:
            subtitle += "  ·  checking..."
        self.app.sub_title = subtitle

        tree = self.query_one(FindingsTree)
        current = tree.current_row()
        branch = tree.current_branch()
        keep = self._next_cursor or (
            current.key if current is not None else branch and branch.data
        )
        self._next_cursor = None
        titles = {result.check.id: result.check.title for result in self._run.results}
        tree.show(
            group_rows(
                sorted(shown, key=row_order),
                self._grouping,
                titles,
                lambda path: (self.course_dir / path).is_dir(),
            ),
            keep=keep,
        )
        if self.focused is not self.query_one("#find", SearchBox):
            tree.focus()  # but never out of the search box while typing
        if not shown:
            self._show_row(None)
            self._detail().update(NO_FINDINGS if not open_rows else ALL_HIDDEN)
            return
        if tree.current_branch() is not None:
            self._show_branch(tree.current_branch())
        else:
            self._show_row(tree.current_row())

    def _current(self):
        return self.query_one(FindingsTree).current_row()

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted):
        row = event.node.data
        if isinstance(row, Row):
            self._show_row(row)
        elif isinstance(row, BranchKey):
            self._show_branch(event.node)

    def on_findings_tree_fix_clicked(self, event: FindingsTree.FixClicked):
        self.action_fix()

    def on_tree_node_selected(self, event: Tree.NodeSelected):
        if isinstance(event.node.data, Row):
            self._open(event.node.data)

    def on_tabs_tab_activated(self, event: Tabs.TabActivated):
        self._grouping = Grouping(event.tab.id.removeprefix(TAB_PREFIX))
        if self._run is not None:
            self._show_rows()

    def on_checkbox_changed(self, event: Checkbox.Changed):
        severity_ids = {f"{SEVERITY_CHIP_PREFIX}{s.value}" for s in Severity}
        if event.checkbox.id in severity_ids:
            self._shown_severities = frozenset(
                severity for severity in Severity if self._severity_chip(severity).value
            )
            self._save_severities(self._shown_severities)
        if self._run is not None:
            self._show_rows()

    def _matches_search(self, row):
        text = self.query_one("#find", SearchBox).value.strip().lower()
        if not text:
            return True
        finding = row.finding
        where = [
            finding.path,
            finding.message,
            finding.check,
            self._check_title(finding),
        ]
        return text in " ".join(where).lower()

    def action_find(self):
        self.query_one("#find", SearchBox).focus()

    def on_input_changed(self, event: SearchBox.Changed):
        if event.input.id == "find" and self._run is not None:
            self._show_rows()

    def on_input_submitted(self, event: SearchBox.Submitted):
        if event.input.id == "find":
            self.query_one(FindingsTree).focus()

    def on_search_box_cleared(self, event: SearchBox.Cleared):
        self.query_one(FindingsTree).focus()

    def _severity_chip(self, severity):
        return self.query_one(f"#{SEVERITY_CHIP_PREFIX}{severity.value}", Checkbox)

    def action_fold_level(self):
        self.query_one(FindingsTree).fold_level()

    def action_unfold_level(self):
        self.query_one(FindingsTree).unfold_level()

    def action_toggle_severity(self, name):
        self._severity_chip(Severity(name)).toggle()

    def action_next_grouping(self):
        groupings = list(Grouping)
        following = groupings[(groupings.index(self._grouping) + 1) % len(groupings)]
        self.query_one("#grouping", Tabs).active = f"{TAB_PREFIX}{following.value}"

    def action_next_finding(self):
        self.query_one(FindingsTree).step(1)

    def action_previous_finding(self):
        self.query_one(FindingsTree).step(-1)

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
        buttons["ignore"].display = row.is_open
        buttons["unignore"].display = row.ignore is not None
        if row.is_open and fix is not None:
            summary.update(_change("Suggested fix (f):", fix))
            summary.display = True
            buttons["fix"].label = Content("[F] FIX")
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
        label, style = row.label
        header = Text()
        header.append(f" {label} ", style=f"reverse {style}")
        header.append(f"  {self._check_title(finding)}\n\n", style="bold")
        header.append(finding.path, style="underline")
        header.append(f"  line {finding.line}" if finding.line else "  whole file")
        header.append("\n\n")
        if row.fixed:
            when = row.fixed.fixed_at.astimezone().strftime("%Y-%m-%d %H:%M")
            header.append(f"Fixed {when}. It was: ", style="italic")
        if row.ignore:
            when = row.ignore.ignored_at.astimezone().strftime("%Y-%m-%d %H:%M")
            reason = row.ignore.reason or "no reason given"
            header.append(f"Ignored {when}: {reason}\n\n", style="italic")
        if row.fixed is None and finding.check in self._stale:
            note = (
                "From an earlier check; this check is running again now."
                if self._running
                else "From an earlier check: the last run was stopped before this "
                "check finished, so it was not re-checked. Press r to check again."
            )
            header.append(f"{note}\n\n", style="italic")
        header.append(finding.message)
        header.append("\n")
        return header

    def _check_title(self, finding):
        if self._run is not None:
            for result in self._run.results:
                if result.check.id == finding.check:
                    return result.check.title
        return finding.check

    def _ignore_for(self, finding):
        return next((i for i in self._ignores if i.matches(finding)), None)

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
            if row is None:
                return bool(self._fixable_in_branch()) if self.is_mounted else False
            return row.is_open and row.finding.fix is not None
        if action in ("view_editor", "undo", "clear"):
            return is_fixed
        if action == "view_site":
            return is_fixed and _site_url(row) is not None
        if action == "clear_all":
            return bool(self._fixed)
        if action == "ignore":
            return row is not None and not is_fixed
        if action == "toggle_ignored":
            return bool(self._ignores)
        if action == "unzoom":
            return self._zoomed
        if action == "stop":
            return self._running and not self._stop_asked.is_set()
        return True

    def action_stop(self):
        if not self._running or self._stop_asked.is_set():
            return
        self._stop_asked.set()
        self.query_one(WatchStrip).show_stopping()
        self.refresh_bindings()

    def action_ignore(self):
        """Open the ignore dialog for an open finding; un-ignore an ignored one."""
        row = self._current()
        if row is None or row.fixed is not None:
            return
        finding = row.finding
        if row.ignore is not None:
            self._ignores = [i for i in self._ignores if not i.matches(finding)]
            self._save_ignores()
            self._show_rows()
            return

        def ignored(reason):
            if reason is None:
                return
            self._ignores.append(ignore_finding(finding, reason, datetime.now(UTC)))
            self._save_ignores()
            self._show_rows()

        self.app.push_screen(IgnoreDialog(finding, self._check_title(finding)), ignored)

    def action_toggle_ignored(self):
        chip = self.query_one("#show-ignored", Checkbox)
        chip.value = not chip.value  # the chip's Changed event redraws the list

    def _save_ignores(self):
        save_ignores(self._ignore_path, self.course_dir, self._ignores)

    def on_button_pressed(self, event: Button.Pressed):
        action = BUTTON_ACTIONS.get(event.button.id)
        if event.button.id == STOP_BUTTON:
            action = "stop"
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
        if self._current() is None and self._fixable_in_branch():
            self._ask_to_fix_branch()
            return
        row = self._current()
        if row is None or not row.is_open or row.finding.fix is None:
            return
        try:
            apply_fix(self.course_dir / row.finding.path, row.finding.fix)
        except FixError as error:
            self.notify(f"Not fixed: {error}", severity="error")
            return
        fixed = FixedFinding(row.finding, datetime.now(UTC))
        self._fixed.append(fixed)
        self._save_fixed()
        self._next_cursor = Row(row.finding, fixed).key  # land on the outcome
        self._start_checking()

    def _fixable_in_branch(self):
        """The findings the branch under the cursor can fix (empty off a branch)."""
        branch = self.query_one(FindingsTree).current_branch()
        if branch is None:
            return []
        return [
            row.finding
            for row in FindingsTree.rows_under(branch)
            if row.is_open and row.finding.fix is not None
        ]

    def _ask_to_fix_branch(self):
        branch = self.query_one(FindingsTree).current_branch()
        findings = self._fixable_in_branch()

        def answered(confirmed):
            if confirmed:
                self._fix_all(branch.data, findings)

        self.app.push_screen(FixAllDialog(branch.data.labels[-1], findings), answered)

    def _fix_all(self, branch_key, findings):
        """Apply each finding's fix, skipping the ones that fail, then check
        once; the outcome shows on the branch and in a notification."""
        failures = []
        for finding in findings:
            try:
                apply_fix(self.course_dir / finding.path, finding.fix)
            except FixError as error:
                failures.append((finding, error))
                continue
            self._fixed.append(FixedFinding(finding, datetime.now(UTC)))
        self._save_fixed()
        done = len(findings) - len(failures)
        outcome = f"Fixed {done} of {len(findings)}."
        report = Text(outcome, style="bold")
        if failures:
            report.append(f" {len(failures)} could not be fixed:\n", style="bold")
            for finding, error in failures:
                report.append(
                    f"\n{finding.path}  line {finding.fix.line}\n", style="underline"
                )
                report.append(f"{error}\n")
            outcome += f" {len(failures)} could not be fixed; see the detail."
        self._batch_report = (branch_key, report)
        self.notify(outcome, severity="warning" if failures else "information")
        self._next_cursor = branch_key
        self._start_checking()

    def _show_branch(self, node):
        """Fill the detail panel with a summary of a branch's open findings."""
        for name in BUTTON_ACTIONS:
            self.query_one(f"#{name}", Button).display = False
        self.query_one("#fix-summary", Static).display = False
        self._show_excerpt(None)
        rows = [row for row in FindingsTree.rows_under(node) if row.is_open]
        fixable = [row.finding for row in rows if row.finding.fix is not None]
        text = Text()
        text.append(" GROUP ", style="reverse bold")
        text.append(f"  {node.data.labels[-1]}\n\n", style="bold")
        counts = []
        for severity in Severity:
            count = sum(1 for row in rows if row.finding.severity == severity)
            if count:
                plural = "" if count == 1 or severity == Severity.INFO else "s"
                counts.append(f"{count} {severity.value}{plural}")
        text.append(f"{len(rows)} {'finding' if len(rows) == 1 else 'findings'} here")
        text.append(f": {', '.join(counts)}.\n" if counts else ".\n")
        titles = [self._check_title(row.finding) for row in rows]
        if len(set(titles)) > 1:
            by_check = ", ".join(
                f"{title} {titles.count(title)}" for title in dict.fromkeys(titles)
            )
            text.append(f"By check: {by_check}\n")
        if fixable:
            files = len({finding.path for finding in fixable})
            noun = "file" if files == 1 else "files"
            text.append(f"{len(fixable)} can be fixed, in {files} {noun}.\n")
        else:
            text.append("Nothing here can be fixed automatically.\n")
        if self._batch_report is not None and self._batch_report[0] == node.data:
            text.append("\n")
            text.append_text(self._batch_report[1])
        self._detail().update(text)
        fix_button = self.query_one("#fix", Button)
        fix_button.label = Content(f"[F] FIX ALL {len(fixable)}")
        fix_button.display = bool(fixable)
        self.query_one("#actions").display = bool(fixable)
        self.refresh_bindings()

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
        self._next_cursor = Row(row.finding).key  # land on the reopened finding
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

    def action_hard_rerun(self):
        self._start_checking(fresh=True)

    def _save_fixed(self):
        save_fixed(self._fix_log_path, self.course_dir, self._fixed)


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
