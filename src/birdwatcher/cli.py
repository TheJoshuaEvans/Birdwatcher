"""
Command line: fetch the course, run the checks, write the report, print a summary.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import argparse
import webbrowser
from pathlib import Path

from platformdirs import user_cache_dir
from rich.console import Console
from rich.table import Table
from rich.text import Text

from birdwatcher.checks import ALL_CHECKS
from birdwatcher.checks.anchors import published_site_url
from birdwatcher.console import print_event, print_findings, print_summary
from birdwatcher.fetch import COURSE_REPO, CourseFetchError, ensure_materials, http_get
from birdwatcher.report import stub_path, write_report
from birdwatcher.run import run_checks

DEFAULT_OUT = "birdwatcher-report"
EXIT_OK = 0
EXIT_FAILED = 2  # the course could not be fetched (argparse also uses 2 for bad usage)


def main(argv=None, *, fetch=http_get, console=None, open_browser=None):
    """
    Run Birdwatcher with command-line arguments.

    Options: --repo OWNER/NAME (default: the CS 212 course), --cache-dir DIR
    (default: the user's cache folder), --out DIR (default: ./birdwatcher-report),
    --check ID (repeatable; default: all checks), --list-checks (print the checks
    and exit without fetching), --verbose (also print progress and every
    finding), --open (open the report in a browser at the first finding).

    Args:
        argv (list[str] | None): Arguments without the program name; None means
            sys.argv[1:].
        fetch (FetchBytes): Performs HTTP requests; replaced in tests.
        console (rich.console.Console | None): Where to print; None means a new
            console on standard output.
        open_browser (Callable[[str], object] | None): Opens a URL; None means
            webbrowser.open.

    Returns:
        int: EXIT_OK after writing the report, whatever it found; EXIT_FAILED if
            the course could not be fetched. Invalid arguments exit through
            argparse (status 2).
    """
    args = _parser().parse_args(argv)
    console = console or Console()
    open_browser = open_browser or webbrowser.open

    if args.list_checks:
        _print_checks(console)
        return EXIT_OK

    checks = [check for check in ALL_CHECKS if not args.check or check.id in args.check]
    try:
        snapshot = ensure_materials(args.cache_dir, repo=args.repo, fetch=fetch)
    except CourseFetchError as error:
        console.print(Text(f"Could not get {args.repo}: {error}", style="red"))
        return EXIT_FAILED

    on_event = (lambda event: print_event(console, event)) if args.verbose else None
    run = run_checks(
        snapshot,
        args.repo,
        checks,
        site_url=published_site_url(args.repo),
        on_event=on_event,
    )
    index = write_report(run, args.out)
    if args.verbose:
        print_findings(console, run, args.out)
    print_summary(console, run, index)

    if args.open:
        findings = run.findings
        start = stub_path(args.out, findings[0]) if findings else index
        open_browser(Path(start).absolute().as_uri())
    return EXIT_OK


def _parser():
    parser = argparse.ArgumentParser(
        prog="birdwatcher",
        description="Watch course materials for consistency problems and blind spots.",
    )
    parser.add_argument(
        "--repo",
        default=COURSE_REPO,
        help=f"GitHub repository to check (default: {COURSE_REPO})",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(user_cache_dir("birdwatcher", appauthor=False)),
        help="where downloaded course files are kept (default: your user cache folder)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(DEFAULT_OUT),
        help=f"report folder (default: ./{DEFAULT_OUT})",
    )
    parser.add_argument(
        "--check",
        action="append",
        choices=[check.id for check in ALL_CHECKS],
        metavar="ID",
        help="run only this check (repeatable; see --list-checks)",
    )
    parser.add_argument(
        "--list-checks", action="store_true", help="list the checks and exit"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="also print progress and every finding",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="open the report in a browser at the first finding",
    )
    return parser


def _print_checks(console):
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("Check")
    table.add_column("What it looks for")
    for check in ALL_CHECKS:
        table.add_row(
            Text(check.id, style="bold"), Text(f"{check.title}. {check.description}")
        )
    console.print(table)
