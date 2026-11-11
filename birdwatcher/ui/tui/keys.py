"""
The keys popup (?): every key of the findings view, grouped by purpose, with
the ones that do not apply right now marked.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from dataclasses import dataclass
from typing import ClassVar

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Static

NOT_NOW = "not now"


@dataclass(frozen=True)
class Key:
    """
    One line of the popup.

    Attributes:
        keys (str): The key or keys, as shown ("n / p").
        does (str): What they do.
        actions (tuple[str, ...]): The screen actions behind them (without
            parameters or the "app." prefix); empty for keys the list or the
            app handles itself. The line counts as available when any of its
            actions is.
    """

    keys: str
    does: str
    actions: tuple[str, ...] = ()


# (group, keys) in display order
KEY_GROUPS = (
    (
        "MOVE",
        (
            Key("↑ ↓  enter", "move; fold or unfold a branch"),
            Key(
                "n / p", "next / previous finding", ("next_finding", "previous_finding")
            ),
            Key("- / +", "fold / unfold a level", ("fold_level", "unfold_level")),
            Key("g", "group by check / by folder", ("next_grouping",)),
            Key("z", "zoom the detail", ("toggle_zoom",)),
            Key("esc", "back from the zoomed detail", ("unzoom",)),
        ),
    ),
    (
        "FILTER",
        (
            Key("1 2 3", "show / hide errors, warnings, info", ("toggle_severity",)),
            Key("h", "show / hide ignored findings", ("toggle_ignored",)),
            Key("/", "find (Enter keeps it, Escape clears it)", ("find",)),
        ),
    ),
    (
        "ACT",
        (
            Key("f", "fix (on a branch: fix all)", ("fix",)),
            Key("o  enter", "open the finding in the editor", ("open_editor",)),
            Key("e", "view the fixed line in the editor", ("view_editor",)),
            Key("w", "view where the fixed link leads", ("view_site",)),
            Key("u", "undo a fix", ("undo",)),
            Key("c", "clear a fixed finding from the list", ("clear",)),
            Key("C", "clear every fixed finding", ("clear_all",)),
            Key("i", "ignore / un-ignore", ("ignore",)),
        ),
    ),
    (
        "CHECK",
        (
            Key("r", "run the checks again", ("rerun",)),
            Key("ctrl+r", "hard refresh: ask every web site again", ("hard_rerun",)),
            Key("x", "stop checking", ("stop",)),
        ),
    ),
    (
        "APP",
        (
            Key("s", "setup: course folder, editor, theme", ("open_setup",)),
            Key("ctrl+p", "command palette (themes and more)"),
            Key("?", "this list", ("show_keys",)),
            Key("q", "quit", ("quit",)),
        ),
    ),
)


class KeysDialog(ModalScreen):
    """
    Lists KEY_GROUPS (#keys-list). A line none of whose actions is available
    right now is dimmed and says NOT_NOW, so it is marked in words as well as
    by color. Escape, ? or q closes it.

    Args:
        available (Callable[[str], bool]): Whether a screen action applies
            right now.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape,question_mark,q", "close", "Close"),
    ]

    def __init__(self, available):
        super().__init__()
        self._available = available

    def compose(self) -> ComposeResult:
        table = Table.grid(padding=(0, 2))
        table.add_column()  # group
        table.add_column()  # keys
        table.add_column()  # what they do
        table.add_column()  # not now
        for number, (group, keys) in enumerate(KEY_GROUPS):
            if number:
                table.add_row()  # a blank line between groups
            for index, key in enumerate(keys):
                now = not key.actions or any(self._available(a) for a in key.actions)
                dim = "" if now else "dim"
                table.add_row(
                    Text(group if index == 0 else "", style="bold"),
                    Text(key.keys, style=f"bold {dim}"),
                    Text(key.does, style=dim),
                    Text("" if now else NOT_NOW, style="dim italic"),
                )
        with VerticalScroll(id="keys-dialog") as dialog:
            dialog.border_title = Content("[ KEYS ]")
            yield Static(table, id="keys-list")

    def action_close(self):
        self.dismiss()
