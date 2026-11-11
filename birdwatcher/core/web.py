"""
Asking web servers whether addresses work: one address at a time, or many
at once with a cache of recent answers.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import http.client
import itertools
import json
import os
import queue
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import truststore

from birdwatcher.core.check import ignore_progress

LINK_CACHE_FILE = "links.json"  # next to the settings
MAX_AGE = timedelta(days=1)  # how long an answer is reused
TIMEOUT = 15  # seconds to wait for a server
MAX_REDIRECTS = 10
WORKERS = 16  # addresses asked about at once
PER_HOST = 2  # addresses asked about at once from one host
SERVER_ERRORS = range(500, 600)  # not cached: often temporary
USER_AGENT = "Mozilla/5.0 (compatible; Birdwatcher link checker)"
REDIRECTS = range(300, 400)
PERMANENT_REDIRECTS = frozenset({301, 308})


@dataclass(frozen=True)
class LinkStatus:
    """What a server said about an address.

    Attributes:
        status: The HTTP status of the final answer, after following
            redirects; None when no answer came (see error).
        moved_to: Where the address has moved permanently, when its first
            answer is a permanent redirect (301 or 308): the address after
            the run of permanent redirects that starts there. None otherwise.
        error: Why no answer came (a timeout, an unknown host, too many
            redirects...), or None.
    """

    status: int | None
    moved_to: str | None = None
    error: str | None = None


def fetch_status(url, timeout=TIMEOUT):
    """
    Ask a server about one address with a GET request, following up to
    MAX_REDIRECTS redirects, without reading the page itself.

    Args:
        url (str): An http or https address, without a #fragment.
        timeout (float): Seconds to wait for each answer.

    Returns:
        LinkStatus: The final status and any permanent move; or the error,
            when no answer came or the redirects went on too long. Never
            raises.
    """
    moved_to = None
    moving = True  # still in the run of permanent redirects from the start
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        request = urllib.request.Request(
            _ascii(current), headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
        )
        try:
            with _OPENER.open(request, timeout=timeout) as response:
                status, location = response.status, None
        except urllib.error.HTTPError as error:
            status, location = error.code, error.headers.get("Location")
            error.close()
        except (OSError, ValueError, http.client.HTTPException) as error:
            return LinkStatus(None, moved_to, _describe(error))
        if not (status in REDIRECTS and location):
            return LinkStatus(status, moved_to)
        current = urllib.parse.urljoin(current, location)
        moving = moving and status in PERMANENT_REDIRECTS
        if moving:
            moved_to = current
    return LinkStatus(None, moved_to, f"more than {MAX_REDIRECTS} redirects")


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Hands every redirect back as an HTTPError, so each hop can be seen."""

    def redirect_request(self, *args, **kwargs):
        return None


# Certificates are checked by the operating system, as browsers do: Python's
# own list lacks the intermediate certificates some servers leave out.
_OPENER = urllib.request.build_opener(
    _NoRedirects,
    urllib.request.HTTPSHandler(context=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)),
)


def _ascii(url):
    """An address with non-ASCII characters percent-encoded, as browsers send it."""
    return urllib.parse.quote(url, safe=":/?#[]@!$&'()*+,;=%~")


def _describe(error):
    """A short reason for a failed request."""
    reason = getattr(error, "reason", None) or error
    return str(reason) or type(error).__name__


def look_up_links(
    urls,
    report_progress=ignore_progress,
    *,
    cache_path=None,
    fetch=fetch_status,
    now=None,
    max_age=MAX_AGE,
    workers=WORKERS,
):
    """
    Ask about many addresses at once, reusing recent answers.

    Answers in the cache younger than max_age are used as they are; the other
    addresses are fetched on up to `workers` background threads, never more
    than PER_HOST at once from one host, so no server is swamped. Each
    fetched answer below 500 is saved in the cache; server errors (5xx) and
    failures are not, so they are asked again next time. With no addresses
    to fetch, the cache file is not touched.

    Args:
        urls (Iterable[str]): The addresses (repeats are asked about once).
        report_progress (Callable[[int, int, str | None], None]): Called on
            the calling thread after each fetched answer with (answers so
            far, addresses to fetch, the answered address's host). If it
            raises (CheckStopped when a run is stopped), the look-up stops at
            once without waiting for fetches still going, saves the answers
            so far, and lets the exception through.
        cache_path (Path | None): The cache file (JSON), created when needed;
            None means no cache.
        fetch (Callable[[str], LinkStatus]): Asks about one address;
            fetch_status by default. Called from background threads.
        now (Callable[[], datetime] | None): The current time, timezone-aware;
            None means the real clock.
        max_age (timedelta): How long a cached answer is used.
        workers (int): Addresses fetched at once.

    Returns:
        dict[str, LinkStatus]: An answer for every address.
    """
    now = now or (lambda: datetime.now(UTC))
    cache = _read_cache(cache_path)
    answers, to_fetch = {}, []
    for url in dict.fromkeys(urls):
        entry = cache.get(url)
        if entry is not None and now() - entry[1] <= max_age:
            answers[url] = entry[0]
        else:
            to_fetch.append(url)
    if not to_fetch:
        return answers

    pending, finished = queue.SimpleQueue(), queue.SimpleQueue()
    stopping = threading.Event()
    by_host = defaultdict(list)
    for url in to_fetch:
        by_host[_host(url)].append(url)
    # Hosts take turns in the queue, so workers seldom wait on a busy host.
    for turn in itertools.zip_longest(*by_host.values()):
        for url in turn:
            if url is not None:
                pending.put(url)
    host_slots = {host: threading.Semaphore(PER_HOST) for host in by_host}

    def work():
        while not stopping.is_set():
            try:
                url = pending.get_nowait()
            except queue.Empty:
                return
            with host_slots[_host(url)]:
                try:
                    answer = fetch(url)
                except Exception as error:  # noqa: BLE001 - a fetch must not hang the look-up
                    answer = LinkStatus(None, error=_describe(error))
            finished.put((url, answer))

    # Daemon threads, so a stop (or quitting) never waits for a slow server.
    for _ in range(min(workers, len(to_fetch))):
        threading.Thread(target=work, daemon=True).start()
    try:
        for done in range(1, len(to_fetch) + 1):
            url, answer = finished.get()
            answers[url] = answer
            if answer.status is not None and answer.status not in SERVER_ERRORS:
                cache[url] = (answer, now())
            report_progress(done, len(to_fetch), _host(url))
    finally:
        stopping.set()
        _write_cache(cache_path, cache, now() - max_age)
    return answers


def _host(url):
    """An address's host name, or "" when it has none."""
    return urllib.parse.urlsplit(url).hostname or ""


def _read_cache(path):
    """{address: (LinkStatus, when it was asked)} from the cache file; empty
    when there is none or it can't be read."""
    if path is None:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return {
            url: (
                LinkStatus(entry["status"], entry.get("moved_to")),
                datetime.fromisoformat(entry["asked_at"]),
            )
            for url, entry in data.items()
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {}


def _write_cache(path, cache, oldest):
    """Save the answers asked since `oldest`, through a temporary file."""
    if path is None:
        return
    path = Path(path)
    data = {
        url: {
            "status": answer.status,
            "moved_to": answer.moved_to,
            "asked_at": asked_at.isoformat(),
        }
        for url, (answer, asked_at) in sorted(cache.items())
        if asked_at >= oldest
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(temporary, path)
