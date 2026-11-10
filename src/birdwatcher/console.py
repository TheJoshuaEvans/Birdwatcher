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

from birdwatcher.findings import Finding, Severity
from birdwatcher.run import CheckStarted

SHORT_COMMIT = 7  # characters of a commit SHA shown to people
SEVERITY_STYLES = {
    Severity.ERROR: ("ERROR", "bold red"),
    Severity.WARNING: ("WARNING", "yellow"),
    Severity.INFO: ("INFO", "cyan"),
}


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
    link to the source on GitHub at the checked commit.

    Args:
        console (rich.console.Console): Where to print.
        run (RunResult): The run.
    """
    for path, items in groupby(run.findings, key=lambda finding: finding.path):
        whole_file = Finding(
            check="", severity=Severity.INFO, path=path, line=None, message=""
        )
        console.print()
        console.print(
            Text(path, style=Style(bold=True, link=run.source_url(whole_file)))
        )
        for finding in items:
            label, style = SEVERITY_STYLES[finding.severity]
            where = f"{finding.line:>5}" if finding.line is not None else " file"
            line = Text("  ")
            line.append(where, style=Style(link=run.source_url(finding)))
            line.append(f"  {label:<7}  ", style=style)
            line.append(finding.message)
            console.print(line)
    console.print()


def print_summary(console, run):
    """
    Print the run summary: repository and commit (linked to the commit on
    GitHub, and saying whether the copy was downloaded, cached, or possibly out
    of date), a table of checks with their finding counts and times (or errors),
    and totals by severity.

    Args:
        console (rich.console.Console): Where to print.
        run (RunResult): The run.
    """
    if run.stale:
        source = "cached copy, may be out of date"
    elif run.downloaded:
        source = "downloaded"
    else:
        source = "cached"
    header = Text("Birdwatcher  ", style="bold")
    header.append(f"{run.repo} @ ", style="")
    commit_url = f"https://github.com/{run.repo}/commit/{run.commit}"
    header.append(run.commit[:SHORT_COMMIT], style=Style(link=commit_url))
    header.append(f" ({source})", style="yellow" if run.stale else "dim")
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
