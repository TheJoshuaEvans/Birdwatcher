"""
Contract tests for birdwatcher.core.log.

Joshua Evans, 2026-11-24 (written with Claude Opus 5.5)
"""

import logging
import re
import sys

import pytest

from birdwatcher.core.log import (
    BACKUP_COUNT,
    delete_log,
    log_files,
    start_logging,
    stop_logging,
)

EVENT_START = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d{3} ")


@pytest.fixture
def logs(tmp_path):
    """Starts logging into tmp_path/logs/birdwatcher.log (a folder that does
    not exist yet) and always stops it; yields a function that starts it."""
    handlers = []

    def start(max_bytes=None):
        path = tmp_path / "logs" / "birdwatcher.log"
        options = {} if max_bytes is None else {"max_bytes": max_bytes}
        handlers.append(start_logging(path, **options))
        return path

    yield start
    for handler in handlers:
        stop_logging(handler)


def read(path):
    return path.read_text(encoding="utf-8")


def test_events_are_written_with_time_level_and_short_name(logs):
    path = logs()
    logging.getLogger("birdwatcher.ai").info("asking %s", "openrouter/free")
    [line] = read(path).splitlines()
    assert EVENT_START.match(line)
    assert line.split()[2:] == ["INFO", "ai", "asking", "openrouter/free"]


def test_debug_events_are_kept(logs):
    path = logs()
    logging.getLogger("birdwatcher.ai").debug("the full prompt")
    assert "DEBUG" in read(path) and "the full prompt" in read(path)


def test_the_lines_of_a_long_message_stay_with_their_event(logs):
    path = logs()
    log = logging.getLogger("birdwatcher.ai")
    log.info("first\nsecond\nthird")
    log.info("next")
    lines = read(path).splitlines()
    assert [bool(EVENT_START.match(line)) for line in lines] == [
        True,
        False,
        False,
        True,
    ]
    assert lines[1].strip() == "second"


def test_other_libraries_are_not_logged(logs):
    path = logs()
    logging.getLogger("httpx").warning("Authorization: Bearer sk-secret")
    logging.getLogger().warning("root logger")
    logging.getLogger("birdwatcher").info("ours")
    assert "secret" not in read(path) and "root logger" not in read(path)
    assert "ours" in read(path)


def test_logging_appends_to_an_earlier_log(logs):
    path = logs()
    path.write_text("earlier\n", encoding="utf-8")
    logging.getLogger("birdwatcher").info("later")
    assert read(path).startswith("earlier\n")


def test_starting_twice_writes_each_event_once(logs):
    path = logs()
    logs()
    logging.getLogger("birdwatcher").info("once")
    assert read(path).count("once") == 1


def test_a_full_log_is_moved_aside(logs):
    path = logs(max_bytes=200)
    log = logging.getLogger("birdwatcher")
    for number in range(20):
        log.info("event %d %s", number, "x" * 40)
    assert log_files(path) == [
        path,
        *(path.with_name(f"{path.name}.{n}") for n in range(1, BACKUP_COUNT + 1)),
    ]
    assert "event 19" in read(path)


def test_after_stopping_nothing_more_is_written(tmp_path):
    path = tmp_path / "birdwatcher.log"
    handler = start_logging(path)
    logging.getLogger("birdwatcher").info("before")
    stop_logging(handler)
    logging.getLogger("birdwatcher").info("after")
    assert "before" in read(path) and "after" not in read(path)
    path.unlink()  # closed: Windows refuses to delete an open file


def test_no_log_has_no_files(tmp_path):
    assert log_files(tmp_path / "birdwatcher.log") == []


def test_deleting_the_log_while_writing_starts_a_new_one(logs):
    path = logs(max_bytes=200)
    log = logging.getLogger("birdwatcher")
    for number in range(10):
        log.info("old event %d %s", number, "x" * 40)
    count = len(log_files(path))
    assert count == 1 + BACKUP_COUNT  # the files were moved aside
    assert delete_log(path) == count
    assert log_files(path) == []
    log.info("new event")
    assert read(path).count("event") == 1 and "new event" in read(path)


def test_deleting_no_log_deletes_nothing(tmp_path):
    assert delete_log(tmp_path / "birdwatcher.log") == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
