"""
The activity log: everything Birdwatcher does, one event per line, in a file
next to its settings, so a session can be followed afterwards.

Every module logs through a child of the "birdwatcher" logger
(logging.getLogger(__name__)). Only those loggers reach the file: other
libraries' loggers do not (httpx's debug lines carry request headers, the API
key among them). Nothing logged may contain an API key.

Joshua Evans, 2026-11-24 (written with Claude Opus 5.5)
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE = "birdwatcher.log"
LOGGER = "birdwatcher"  # the logger whose events (and its children's) are kept
MAX_BYTES = 1_000_000  # a log file this large is moved aside and a new one begun
BACKUP_COUNT = 2  # older files kept: birdwatcher.log.1, birdwatcher.log.2
CONTINUATION = "    "  # starts the second and later lines of an event
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class _EventFormatter(logging.Formatter):
    """'<time>.<ms> <LEVEL> <short name>  <message>', later lines indented."""

    def __init__(self):
        super().__init__(
            "%(asctime)s.%(msecs)03d %(levelname)-5s %(short_name)s  %(message)s",
            TIME_FORMAT,
        )

    def format(self, record):
        record.short_name = record.name.removeprefix(f"{LOGGER}.")
        text = super().format(record)
        return text.replace("\n", "\n" + CONTINUATION)


def start_logging(path, max_bytes=MAX_BYTES):
    """
    Write every event of the LOGGER logger and its children, DEBUG and up, to
    a log file, appending to what is there.

    Each event starts a line with its local time to the millisecond, its
    level and its logger's name without the "birdwatcher." prefix:
    "2026-11-24 10:18:29.123 INFO  ai  asking ...". The lines after the first
    of a multi-line message are indented, so every line that does not start
    with a time belongs to the event above it. A file that reaches max_bytes
    is renamed path.1 (the older path.1 becoming path.2, up to BACKUP_COUNT)
    and a new one begun. Starting again with a path already being written
    changes nothing.

    Args:
        path (Path): The log file; its folder is created if needed.
        max_bytes (int): The size at which the file is moved aside.

    Returns:
        logging.Handler: The handler writing the file, for stop_logging.
    """
    path = Path(path).absolute()
    logger = logging.getLogger(LOGGER)
    logger.setLevel(logging.DEBUG)
    existing = _handlers_for(path)
    if existing:
        return existing[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=BACKUP_COUNT, encoding="utf-8", delay=True
    )
    handler.setFormatter(_EventFormatter())
    logger.addHandler(handler)
    return handler


def stop_logging(handler):
    """
    Stop writing a log file started by start_logging, and close it.

    Args:
        handler (logging.Handler): What start_logging returned.
    """
    logging.getLogger(LOGGER).removeHandler(handler)
    handler.close()


def log_files(path):
    """
    The log file and its moved-aside copies that exist.

    Args:
        path (Path): The log file.

    Returns:
        list[Path]: path, then path.1, path.2 ..., only those that exist.
    """
    path = Path(path)
    candidates = [path, *(path.with_name(f"{path.name}.{n}") for n in range(1, 10))]
    # Numbering past BACKUP_COUNT too, in case an earlier version kept more.
    return [candidate for candidate in candidates if candidate.is_file()]


def delete_log(path):
    """
    Delete the log file and its moved-aside copies, even while it is being
    written; events from then on go to a new file.

    Args:
        path (Path): The log file.

    Returns:
        int: How many files were deleted.
    """
    path = Path(path).absolute()
    handlers = _handlers_for(path)
    for handler in handlers:
        handler.acquire()  # no event is written halfway through
    try:
        for handler in handlers:
            if handler.stream is not None:
                handler.stream.close()
                handler.stream = None  # the next event opens a new file
        files = log_files(path)
        for file in files:
            file.unlink()
        return len(files)
    finally:
        for handler in handlers:
            handler.release()


def _handlers_for(path):
    """The handlers on LOGGER writing to a file at path."""
    return [
        handler
        for handler in logging.getLogger(LOGGER).handlers
        if isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename) == path
    ]
