"""
The watch strip: a status strip at the bottom of the findings pane that says
what Birdwatcher is checking while checks run, and which checks were not
re-checked after a run was stopped.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.content import Content
from textual.widgets import Button, Static

BAR_WIDTH = 16  # characters in the progress bar
BAR_DONE, BAR_LEFT = "▓", "░"


def progress_bar(done, total, width=BAR_WIDTH):
    """
    A text progress bar.

    Args:
        done (int): Units done.
        total (int): Units in all.
        width (int): Characters in the bar.

    Returns:
        str: width characters: BAR_DONE for the share done (rounded down,
            and never full until done reaches total), BAR_LEFT for the rest.
            A total of 0 or less gives a full bar; done is clamped to 0..total.
    """
    if total <= 0:
        return BAR_DONE * width
    done = min(max(done, 0), total)
    filled = width if done == total else min(width - 1, done * width // total)
    return BAR_DONE * filled + BAR_LEFT * (width - filled)


class WatchStrip(Horizontal):
    """
    The strip: two lines of status (#watch-status) and a [X] STOP button
    (#stop, shown only while checks run). Hidden until one of the show_
    methods is called, and again after hide().
    """

    def compose(self) -> ComposeResult:
        yield Static(id="watch-status")
        yield Button(Content("[X] STOP"), variant="error", id="stop")

    def show_running(self, title, done=None, total=None, detail=None):
        """
        Show that a check is running, with the STOP button.

        Args:
            title (str): The running check's title.
            done (int | None): Units done, when the check reports progress.
            total (int | None): Units in all, when the check reports progress.
            detail (str | None): What it is working on, when it says.

        The first line reads "WATCHING", then (with progress) the bar and
        "done/total"; the second line is the title, followed by " · detail"
        when there is a detail.
        """
        status = Text("WATCHING", style="bold")
        if done is not None and total is not None:
            status.append(f"  {progress_bar(done, total)}  {done}/{total}")
        status.append(f"\n{title}")
        if detail:
            status.append(f" · {detail}", style="dim")
        self._show(status, stop=True)

    def show_stopping(self):
        """Show that a stop was asked for and the running check is finishing
        its current step: the first line reads "STOPPING", the STOP button
        hides."""
        self._show(Text("STOPPING\nFinishing the current step...", style="bold"))

    def show_stopped(self, titles):
        """
        Show that the last run was stopped, without the STOP button.

        Args:
            titles (Sequence[str]): The titles of the checks that didn't
                finish; the first line reads "STOPPED", the second names them
                and says that r checks again.
        """
        status = Text("STOPPED", style="bold")
        if titles:
            status.append(
                f"\nDidn't finish: {', '.join(titles)}. Press r to check again."
            )
        else:
            status.append("\nNot every check ran. Press r to check again.")
        self._show(status)

    def hide(self):
        """Hide the strip."""
        self.display = False

    def _show(self, status, stop=False):
        self.query_one("#watch-status", Static).update(status)
        self.query_one("#stop", Button).display = stop
        self.display = True
