"""
Command line: open the interactive app, or check once and print a summary.

    birdwatcher                 open the app (see birdwatcher.tui)
    birdwatcher check           check once and print a summary, for scripts
    birdwatcher check --verbose also print progress and every finding

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import argparse
from pathlib import Path

from platformdirs import user_cache_dir
from rich.console import Console
from rich.table import Table
from rich.text import Text

from birdwatcher.checks import ALL_CHECKS
from birdwatcher.checks.anchors import published_site_url
from birdwatcher.console import print_event, print_findings, print_summary
from birdwatcher.fetch import COURSE_REPO, CourseFetchError, ensure_materials, http_get
from birdwatcher.run import run_checks
from birdwatcher.tui import BirdwatcherApp, Checked

EXIT_OK = 0
EXIT_FAILED = 2  # the course could not be fetched (argparse also uses 2 for bad usage)
CHECK_COMMAND = "check"


def main(argv=None, *, fetch=http_get, console=None, run_app=None):
    """
    Run Birdwatcher with command-line arguments.

    Without a command, opens the interactive app. With `check`, fetches and
    checks the course once and prints a summary.

    Options for every command (before or after the command name): --repo
    OWNER/NAME (default: the CS 212 course), --cache-dir DIR (default: the
    user's cache folder). Options for `check`: --check ID (repeatable; default:
    all checks), --list-checks (print the checks and exit without fetching),
    --verbose (also print progress and every finding).

    Args:
        argv (list[str] | None): Arguments without the program name; None means
            sys.argv[1:].
        fetch (FetchBytes): Performs HTTP requests; replaced in tests.
        console (rich.console.Console | None): Where `check` prints; None means a
            new console on standard output.
        run_app (Callable[[BirdwatcherApp], object] | None): Runs the app until
            it is closed; None means BirdwatcherApp.run.

    Returns:
        int: EXIT_OK after the app closes, or after `check` finishes whatever it
            found; EXIT_FAILED if `check` could not fetch the course (the app
            shows that error in its window instead). Invalid arguments exit
            through argparse (status 2).
    """
    args = _parser().parse_args(argv)
    if args.command == CHECK_COMMAND:
        return _check(args, fetch, console or Console())

    run_app = run_app or BirdwatcherApp.run
    run_app(
        BirdwatcherApp(
            lambda: load_course(args.repo, args.cache_dir, fetch, ALL_CHECKS)
        )
    )
    return EXIT_OK


def load_course(repo, cache_dir, fetch, checks, on_event=None):
    """
    Fetch the course (or use the cached copy) and run checks over it.

    Args:
        repo (str): GitHub repository, as OWNER/NAME.
        cache_dir (Path): Where downloaded copies are kept.
        fetch (FetchBytes): Performs HTTP requests.
        checks (Sequence[Check]): The checks to run.
        on_event (Callable[[CheckStarted | CheckFinished], object] | None):
            Receives progress events.

    Returns:
        Checked: The checked copy's folder and the results.

    Raises:
        CourseFetchError: The course could not be fetched and no copy is cached.
    """
    snapshot = ensure_materials(cache_dir, repo=repo, fetch=fetch)
    run = run_checks(
        snapshot, repo, checks, site_url=published_site_url(repo), on_event=on_event
    )
    return Checked(snapshot.root, run)


def _check(args, fetch, console):
    if args.list_checks:
        _print_checks(console)
        return EXIT_OK

    checks = [check for check in ALL_CHECKS if not args.check or check.id in args.check]
    on_event = (lambda event: print_event(console, event)) if args.verbose else None
    try:
        checked = load_course(args.repo, args.cache_dir, fetch, checks, on_event)
    except CourseFetchError as error:
        console.print(Text(f"Could not get {args.repo}: {error}", style="red"))
        return EXIT_FAILED

    if args.verbose:
        print_findings(console, checked.run)
    print_summary(console, checked.run)
    return EXIT_OK


def _parser():
    parser = argparse.ArgumentParser(
        prog="birdwatcher",
        description="Watch course materials for consistency problems and blind spots. "
        "Without a command, opens the interactive app.",
        parents=[_shared_options(with_defaults=True)],
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    check = commands.add_parser(
        CHECK_COMMAND,
        help="check once and print a summary",
        description="Check the course once and print a summary.",
        parents=[_shared_options(with_defaults=False)],
    )
    check.add_argument(
        "--check",
        action="append",
        choices=[check.id for check in ALL_CHECKS],
        metavar="ID",
        help="run only this check (repeatable; see --list-checks)",
    )
    check.add_argument(
        "--list-checks", action="store_true", help="list the checks and exit"
    )
    check.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="also print progress and every finding",
    )
    return parser


def _shared_options(with_defaults):
    # The command's copy of these options leaves unset values out (SUPPRESS),
    # so a value given before the command name is not overwritten by a default.
    options = argparse.ArgumentParser(add_help=False)
    options.add_argument(
        "--repo",
        default=COURSE_REPO if with_defaults else argparse.SUPPRESS,
        help=f"GitHub repository to check (default: {COURSE_REPO})",
    )
    options.add_argument(
        "--cache-dir",
        type=Path,
        default=(
            Path(user_cache_dir("birdwatcher", appauthor=False))
            if with_defaults
            else argparse.SUPPRESS
        ),
        help="where downloaded course files are kept (default: your user cache folder)",
    )
    return options


def _print_checks(console):
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("Check")
    table.add_column("What it looks for")
    for check in ALL_CHECKS:
        table.add_row(
            Text(check.id, style="bold"), Text(f"{check.title}. {check.description}")
        )
    console.print(table)
