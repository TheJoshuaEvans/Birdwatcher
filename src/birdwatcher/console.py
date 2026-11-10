"""
Console output: the operator's view of a run (the HTML report is the reader's).

Course text and error messages always go through rich Text objects, never through
rich markup, so square brackets in them are printed as they are.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from itertools import groupby
from pathlib import Path

from rich.style import Style
from rich.table import Table
from rich.text import Text

from birdwatcher.findings import Finding, Severity
from birdwatcher.report import stub_path
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


def print_findings(console, run, out_dir):
    """
    Print every finding, grouped by file.

    Each finding shows its line, severity and message. Its location links to the
    source on GitHub at the checked commit, and its message links to the
    finding's place in the HTML report (via report.stub_path).

    Args:
        console (rich.console.Console): Where to print.
        run (RunResult): The run.
        out_dir (Path): The report folder.
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
            stub_uri = Path(stub_path(out_dir, finding)).absolute().as_uri()
            line = Text("  ")
            line.append(where, style=Style(link=run.source_url(finding)))
            line.append(f"  {label:<7}  ", style=style)
            line.append(finding.message, style=Style(link=stub_uri))
            console.print(line)
    console.print()


def print_summary(console, run, index):
    """
    Print the run summary: repository and commit (and whether the copy was
    downloaded, cached, or possibly out of date), a table of checks with their
    finding counts and times (or errors), totals by severity, and a link to the
    report.

    Args:
        console (rich.console.Console): Where to print.
        run (RunResult): The run.
        index (Path): The report's index.html.
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

    report = Text("Report: ")
    report.append(
        str(index), style=Style(link=Path(index).absolute().as_uri(), underline=True)
    )
    console.print(report)


def _plural(count, singular, plural):
    return f"{count} {singular if count == 1 else plural}"
