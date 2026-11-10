"""
Command line: open the interactive app, or check once and print a summary.

    birdwatcher                 open the app (see birdwatcher.tui)
    birdwatcher check           check once and print a summary, for scripts
    birdwatcher check --verbose also print progress and every finding

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import argparse
from functools import partial
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from birdwatcher.checks import ALL_CHECKS
from birdwatcher.config import default_config_path, load_config
from birdwatcher.console import print_event, print_findings, print_summary
from birdwatcher.course import check_course, course_problem
from birdwatcher.tui import BirdwatcherApp

EXIT_OK = 0
EXIT_FAILED = 2  # no usable course folder (argparse also uses 2 for bad usage)
CHECK_COMMAND = "check"


def main(argv=None, *, config_path=None, console=None, run_app=None):
    """
    Run Birdwatcher with command-line arguments.

    Without a command, opens the interactive app, which starts on its setup
    page when no course folder is saved yet. With `check`, checks the course
    once and prints a summary.

    Options for `check`: --course-dir DIR (the course to check instead of the
    saved one), --check ID (repeatable; default: all checks), --list-checks
    (print the checks and exit), --verbose (also print progress and every
    finding).

    Args:
        argv (list[str] | None): Arguments without the program name; None means
            sys.argv[1:].
        config_path (Path | None): The settings file; None means
            config.default_config_path().
        console (rich.console.Console | None): Where `check` prints; None means a
            new console on standard output.
        run_app (Callable[[BirdwatcherApp], object] | None): Runs the app until
            it is closed; None means BirdwatcherApp.run.

    Returns:
        int: EXIT_OK after the app closes, or after `check` finishes whatever it
            found; EXIT_FAILED if `check` has no usable course folder (none
            saved and none given, or the folder cannot be used). Invalid
            arguments exit through argparse (status 2).
    """
    args = _parser().parse_args(argv)
    config_path = config_path or default_config_path()
    if args.command == CHECK_COMMAND:
        return _check(args, config_path, console or Console())

    run_app = run_app or BirdwatcherApp.run
    run_app(BirdwatcherApp(config_path))
    return EXIT_OK


def _check(args, config_path, console):
    if args.list_checks:
        _print_checks(console)
        return EXIT_OK

    course_dir = args.course_dir
    if course_dir is None:
        config = load_config(config_path)
        if config is None:
            console.print(
                Text(
                    "No course folder is set up yet. Run `birdwatcher` to choose "
                    "one, or pass --course-dir.",
                    style="red",
                )
            )
            return EXIT_FAILED
        course_dir = config.course_dir
    course_dir = Path(course_dir).absolute()
    problem = course_problem(course_dir)
    if problem:
        console.print(Text(problem, style="red"))
        return EXIT_FAILED

    checks = [check for check in ALL_CHECKS if not args.check or check.id in args.check]
    on_event = partial(print_event, console) if args.verbose else None
    run = check_course(course_dir, checks, on_event)
    if args.verbose:
        print_findings(console, run)
    print_summary(console, run)
    return EXIT_OK


def _parser():
    parser = argparse.ArgumentParser(
        prog="birdwatcher",
        description="Watch course materials for consistency problems and blind spots. "
        "Without a command, opens the interactive app.",
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    check = commands.add_parser(
        CHECK_COMMAND,
        help="check once and print a summary",
        description="Check the course once and print a summary.",
    )
    check.add_argument(
        "--course-dir",
        type=Path,
        metavar="DIR",
        help="the course repository to check (default: the one chosen in the app)",
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


def _print_checks(console):
    table = Table(box=None, padding=(0, 2), show_edge=False)
    table.add_column("Check")
    table.add_column("What it looks for")
    for check in ALL_CHECKS:
        table.add_row(
            Text(check.id, style="bold"), Text(f"{check.title}. {check.description}")
        )
    console.print(table)
