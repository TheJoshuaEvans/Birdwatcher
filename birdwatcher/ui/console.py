"""
Console output for `birdwatcher check`: a run summary for scripts and quick looks.

Course text and error messages always go through rich Text objects, never through
rich markup, so square brackets in them are printed as they are.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from itertools import groupby

from rich.style import Style
from rich.table import Table
from rich.text import Text

from birdwatcher.core.findings import Severity
from birdwatcher.core.run import CheckStarted
from birdwatcher.ui.severity import SEVERITY_STYLES
from birdwatcher.ui.system import editor_url


def print_event(console, event):
    """
    Print one progress line for a run event.

    Args:
        console (rich.console.Console): Where to print.
        event (CheckStarted | CheckFinished): The event. A finished check prints
            its finding count and time, or its error.
    """
    if isinstance(event, CheckStarted):
        console.print(Text(f"Running {event.check.title}...", style="dim"))
        return
    result = event.result
    if result.error:
        console.print(Text(f"{result.check.title} failed: {result.error}", style="red"))
    else:
        count = _plural(len(result.findings), "finding", "findings")
        console.print(Text(f"{result.check.title}: {count} ({result.seconds:.2f} s)"))


def print_findings(console, run):
    """
    Print every finding, grouped by file.

    Each finding shows its line, severity and message. Files and line numbers
    link to the file in VS Code (see editor_url), so the run's course folder
    should be an absolute path.

    Args:
        console (rich.console.Console): Where to print.
        run (RunResult): The run.
    """
    for path, items in groupby(run.findings, key=lambda finding: finding.path):
        file_url = editor_url(run.course_dir / path)
        console.print()
        console.print(Text(path, style=Style(bold=True, link=file_url)))
        for finding in items:
            label, style = SEVERITY_STYLES[finding.severity]
            where = f"{finding.line:>5}" if finding.line is not None else " file"
            line_url = editor_url(run.file_of(finding), finding.line)
            line = Text("  ")
            line.append(where, style=Style(link=line_url))
            line.append(f"  {label:<7}  ", style=style)
            line.append(finding.message)
            console.print(line)
    console.print()


def print_summary(console, run):
    """
    Print the run summary: the course folder, a table of checks with their
    finding counts and times (or errors), and totals by severity.

    Args:
        console (rich.console.Console): Where to print.
        run (RunResult): The run.
    """
    header = Text("Birdwatcher  ", style="bold")
    header.append(str(run.course_dir), style="")
    console.print(header)

    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("Check")
    table.add_column("Findings", justify="right")
    table.add_column("Time", justify="right")
    for result in run.results:
        if result.error:
            table.add_row(
                result.check.id, Text(f"failed: {result.error}", style="red"), ""
            )
        else:
            table.add_row(
                result.check.id, str(len(result.findings)), f"{result.seconds:.2f} s"
            )
    console.print()
    console.print(table)
    console.print()

    counts = [
        _plural(run.count(severity), name, f"{name}s")
        for severity, name in ((Severity.ERROR, "error"), (Severity.WARNING, "warning"))
    ]
    if run.count(Severity.INFO):
        counts.append(_plural(run.count(Severity.INFO), "info", "info"))
    total = _plural(len(run.findings), "finding", "findings")
    console.print(Text(f"{total} ({', '.join(counts)})"))


def _plural(count, singular, plural):
    return f"{count} {singular if count == 1 else plural}"
