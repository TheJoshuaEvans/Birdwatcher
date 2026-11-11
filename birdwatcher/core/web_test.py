"""
Contract tests for birdwatcher.core.web. fetch_status is tested against a
real HTTP server on this computer, so no test needs the internet.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import socket
import sys
import threading
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from birdwatcher.core.check import CheckStopped
from birdwatcher.core.web import LinkStatus, fetch_status, look_up_links

# path: (status, Location header or None)
ROUTES = {
    "/ok": (200, None),
    "/gone": (404, None),
    "/old": (301, "/ok"),
    "/old-chain": (301, "/old-2"),
    "/old-2": (308, "/ok"),
    "/temp": (302, "/ok"),
    "/old-then-temp": (301, "/temp"),
    "/moved-dead": (301, "/gone"),
    "/loop": (301, "/loop"),
    "/relative": (301, "ok"),
    "/elsewhere": (301, "http://127.0.0.1:{port}/ok"),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/slow":
            time.sleep(2)
        status, location = ROUTES.get(self.path, (200, None))
        self.send_response(status)
        if location:
            self.send_header("Location", location.format(port=self.server.server_port))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.mark.parametrize(
    ("path", "status", "moved_to"),
    [
        ("/ok", 200, None),
        ("/gone", 404, None),
        ("/old", 200, "/ok"),
        ("/old-chain", 200, "/ok"),
        ("/temp", 200, None),
        ("/old-then-temp", 200, "/temp"),
        ("/moved-dead", 404, "/gone"),
        ("/relative", 200, "/ok"),
        ("/elsewhere", 200, "/ok"),
    ],
)
def test_fetch_status_follows_redirects_and_notes_permanent_moves(
    server, path, status, moved_to
):
    answer = fetch_status(server + path)
    assert answer.status == status
    assert answer.moved_to == (None if moved_to is None else server + moved_to)
    assert answer.error is None


def test_a_redirect_loop_is_an_error(server):
    answer = fetch_status(server + "/loop")
    assert answer.status is None
    assert "redirect" in answer.error


def test_a_slow_server_is_an_error(server):
    answer = fetch_status(server + "/slow", timeout=0.3)
    assert answer.status is None
    assert answer.error


def test_a_server_that_is_not_there_is_an_error():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    answer = fetch_status(f"http://127.0.0.1:{port}/")
    assert answer.status is None
    assert answer.error


class FakeFetch:
    """Answers from a dict (an Exception value is raised); counts calls."""

    def __init__(self, answers):
        self.answers = answers
        self.asked = []
        self.lock = threading.Lock()

    def __call__(self, url):
        with self.lock:
            self.asked.append(url)
        return self.answers[url]


OK = LinkStatus(200)
GONE = LinkStatus(404)
DOWN = LinkStatus(None, error="timed out")
NOON = datetime(2026, 11, 10, 12, tzinfo=UTC)


def clock(*times):
    """A now() that returns each time in turn (the last one repeats)."""
    calls = []

    def now():
        calls.append(None)
        return times[min(len(calls), len(times)) - 1]

    return now


def test_every_address_gets_an_answer_and_repeats_are_asked_once(tmp_path):
    fetch = FakeFetch({"https://a.example/1": OK, "https://b.example/2": GONE})
    answers = look_up_links(
        ["https://a.example/1", "https://b.example/2", "https://a.example/1"],
        fetch=fetch,
        cache_path=tmp_path / "links.json",
    )
    assert answers == {"https://a.example/1": OK, "https://b.example/2": GONE}
    assert sorted(fetch.asked) == ["https://a.example/1", "https://b.example/2"]


def test_recent_answers_come_from_the_cache(tmp_path):
    cache = tmp_path / "links.json"
    urls = ["https://a.example/1", "https://b.example/2"]
    look_up_links(urls, fetch=FakeFetch(dict.fromkeys(urls, OK)), cache_path=cache)
    again = FakeFetch({"https://a.example/1": GONE, "https://b.example/2": GONE})
    answers = look_up_links(
        urls, fetch=again, cache_path=cache, now=clock(datetime.now(UTC))
    )
    assert again.asked == []
    assert answers == dict.fromkeys(urls, OK)


def test_old_answers_are_asked_again(tmp_path):
    cache = tmp_path / "links.json"
    url = "https://a.example/1"
    look_up_links([url], fetch=FakeFetch({url: OK}), cache_path=cache, now=clock(NOON))
    later = NOON + timedelta(days=1, minutes=1)
    again = FakeFetch({url: GONE})
    answers = look_up_links([url], fetch=again, cache_path=cache, now=clock(later))
    assert again.asked == [url]
    assert answers == {url: GONE}


def test_a_max_age_of_zero_asks_again_and_forgets_older_answers(tmp_path):
    cache = tmp_path / "links.json"
    first, second = "https://a.example/1", "https://b.example/2"
    look_up_links(
        [first, second],
        fetch=FakeFetch({first: OK, second: OK}),
        cache_path=cache,
        now=clock(NOON),
    )
    later = NOON + timedelta(minutes=5)
    fresh = FakeFetch({first: GONE})
    answers = look_up_links(
        [first], fetch=fresh, cache_path=cache, now=clock(later), max_age=timedelta(0)
    )
    assert answers == {first: GONE}
    assert fresh.asked == [first]
    # The older answer about the second address is gone from the cache too
    again = FakeFetch({second: GONE})
    look_up_links([second], fetch=again, cache_path=cache, now=clock(later))
    assert again.asked == [second]


def test_moves_are_cached_with_their_answer(tmp_path):
    cache = tmp_path / "links.json"
    url = "http://a.example/1"
    moved = LinkStatus(200, moved_to="https://a.example/1")
    look_up_links(
        [url], fetch=FakeFetch({url: moved}), cache_path=cache, now=clock(NOON)
    )
    answers = look_up_links(
        [url], fetch=FakeFetch({}), cache_path=cache, now=clock(NOON)
    )
    assert answers == {url: moved}


@pytest.mark.parametrize("failure", [DOWN, LinkStatus(502)], ids=["no-answer", "5xx"])
def test_failures_and_server_errors_are_not_cached(tmp_path, failure):
    cache = tmp_path / "links.json"
    url = "https://a.example/1"
    look_up_links(
        [url], fetch=FakeFetch({url: failure}), cache_path=cache, now=clock(NOON)
    )
    again = FakeFetch({url: OK})
    assert look_up_links([url], fetch=again, cache_path=cache, now=clock(NOON)) == {
        url: OK
    }
    assert again.asked == [url]


def test_nothing_to_fetch_leaves_the_cache_file_alone(tmp_path):
    cache = tmp_path / "links.json"
    assert look_up_links([], fetch=FakeFetch({}), cache_path=cache) == {}
    assert not cache.exists()


def test_an_unreadable_cache_is_ignored(tmp_path):
    cache = tmp_path / "links.json"
    cache.write_text("not json", encoding="utf-8")
    url = "https://a.example/1"
    assert look_up_links([url], fetch=FakeFetch({url: OK}), cache_path=cache) == {
        url: OK
    }
    # The answer was saved over the broken file
    assert look_up_links([url], fetch=FakeFetch({}), cache_path=cache) == {url: OK}


def test_progress_is_reported_after_each_answer_with_its_host(tmp_path):
    urls = ["https://a.example/1", "https://b.example/2", "https://c.example/3"]
    reports = []
    look_up_links(
        urls,
        lambda done, total, detail=None: reports.append((done, total, detail)),
        fetch=FakeFetch(dict.fromkeys(urls, OK)),
    )
    assert [(done, total) for done, total, _ in reports] == [(1, 3), (2, 3), (3, 3)]
    assert sorted(detail for _, _, detail in reports) == [
        "a.example",
        "b.example",
        "c.example",
    ]


def test_cached_answers_are_not_counted_as_progress(tmp_path):
    cache = tmp_path / "links.json"
    cached, fresh = "https://a.example/1", "https://b.example/2"
    look_up_links([cached], fetch=FakeFetch({cached: OK}), cache_path=cache)
    reports = []
    look_up_links(
        [cached, fresh],
        lambda done, total, detail=None: reports.append((done, total)),
        fetch=FakeFetch({fresh: OK}),
        cache_path=cache,
    )
    assert reports == [(1, 1)]


def test_one_host_is_asked_about_at_most_two_addresses_at_once():
    urls = [f"https://busy.example/{n}" for n in range(6)]
    urls += [f"https://other.example/{n}" for n in range(6)]
    lock = threading.Lock()
    current = Counter()
    most = Counter()

    def fetch(url):
        host = url.split("/")[2]
        with lock:
            current[host] += 1
            most[host] = max(most[host], current[host])
        time.sleep(0.05)
        with lock:
            current[host] -= 1
        return OK

    answers = look_up_links(urls, fetch=fetch, workers=8)
    assert len(answers) == len(urls)
    assert most == {"busy.example": 2, "other.example": 2}


def test_a_stop_ends_the_look_up_at_once_and_keeps_the_answers_so_far(tmp_path):
    cache = tmp_path / "links.json"
    quick, stuck = "https://a.example/quick", "https://b.example/stuck"
    release = threading.Event()

    def fetch(url):
        if url == stuck:
            release.wait(10)
        return OK

    def report(done, total, detail=None):
        raise CheckStopped

    started = time.monotonic()
    try:
        with pytest.raises(CheckStopped):
            look_up_links([quick, stuck], report, fetch=fetch, cache_path=cache)
        assert time.monotonic() - started < 2  # did not wait for the stuck fetch
    finally:
        release.set()
    again = FakeFetch({stuck: GONE})
    answers = look_up_links([quick, stuck], fetch=again, cache_path=cache)
    assert answers == {quick: OK, stuck: GONE}
    assert again.asked == [stuck]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
