"""
Dead links to other sites: addresses on other web sites that no longer work,
asked about over the network.

The course's own link checker settings are followed: addresses matching a
regular expression in its .lycheeignore file or in the exclude list of its
lychee.toml are not checked.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import http
import re
import tomllib
import urllib.parse
from pathlib import Path

from birdwatcher.checks.pages import page_links, read_page, site_pages
from birdwatcher.core.check import ignore_progress
from birdwatcher.core.course import site_folder
from birdwatcher.core.findings import Destination, Finding, Fix, Severity

CHECK = "dead-external-link"
GONE = frozenset({404, 410})
REFUSED = frozenset({401, 403, 429})  # sites that turn automated checks away
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1"})
CLIENT_ERROR, SERVER_ERROR = 400, 500  # where those HTTP status ranges start
OFFLINE_MINIMUM = 3  # addresses that must all go unanswered to call it offline


class OfflineError(ConnectionError):
    """No site answered at all, so the computer is probably offline."""


def check_external_links(
    repo_root, site_url, look_up=None, report_progress=ignore_progress
):
    """
    Ask about every http and https address the site's Markdown and HTML pages
    link to, other than the site's own, and report the ones that don't work.

    Addresses are asked about once each, without their #fragment. Not asked
    about: addresses starting with site_url, addresses on this computer
    (localhost), and addresses matching the course's .lycheeignore or its
    lychee.toml exclude list (regular expressions, matched anywhere in the
    address).

    Args:
        repo_root (Path): Root folder of the course repository.
        site_url (str | None): Published site address ending in "/", or None.
        look_up (Callable | None): look_up(addresses, report_progress) returns
            {address: core.web.LinkStatus}, as core.web.look_up_links does.
            None means no network: nothing is asked and nothing reported.
        report_progress (Callable): Passed to look_up.

    Returns:
        list[Finding]: In file and line order, one per link, by the final
            answer for its address:
            - 404 or 410 (gone), any 5xx (server error), or no answer at all:
              an error naming the status or the reason;
            - 401, 403 or 429 (refused), or any other 4xx: info, saying the
              answer is inconclusive and to open the address in a browser;
            - a working answer after a permanent move to a different address:
              info with a Fix replacing the link with the new address (keeping
              its #fragment), whose destination is the page itself with the
              new address as its url. Moves that only add https, "www." or a
              trailing "/" are not reported.
            Empty when the repository has no docs/ folder.

    Raises:
        OfflineError: When at least OFFLINE_MINIMUM addresses were asked
            about and none of them answered.
    """
    repo_root = Path(repo_root).resolve()
    docs = site_folder(repo_root)
    if look_up is None or not docs.is_dir():
        return []
    excluded = _exclusions(repo_root)
    links = []  # (page, line, target, address)
    for page in site_pages(docs, suffixes=(".md", ".html")):
        is_html = page.suffix.lower() == ".html"
        for line, target in page_links(read_page(page), html=is_html):
            address = target.partition("#")[0]
            if _is_external(address, site_url, excluded):
                links.append((page, line, target, address))
    if not links:
        return []
    answers = look_up(list(dict.fromkeys(link[3] for link in links)), report_progress)
    if len(answers) >= OFFLINE_MINIMUM and all(
        answer.status is None for answer in answers.values()
    ):
        raise OfflineError("No site answered at all: is this computer offline?")
    findings = []
    for page, line, target, address in links:
        finding = _finding(
            page.relative_to(repo_root).as_posix(), line, target, answers[address]
        )
        if finding is not None:
            findings.append(finding)
    return sorted(findings, key=lambda finding: (finding.path, finding.line))


def _exclusions(repo_root):
    """The course's link checker exclusions, as compiled regular expressions
    (lines that are not valid expressions are skipped)."""
    patterns = []
    ignore_file = repo_root / ".lycheeignore"
    if ignore_file.is_file():
        for line in ignore_file.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    config_file = repo_root / "lychee.toml"
    if config_file.is_file():
        try:
            config = tomllib.loads(config_file.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            config = {}
        exclude = config.get("exclude", [])
        patterns += [item for item in exclude if isinstance(item, str)]
    compiled = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error:
            continue
    return compiled


def _is_external(address, site_url, excluded):
    """Whether this check asks about an address."""
    if not address.lower().startswith(("http://", "https://")):
        return False
    if site_url and address.startswith(site_url):
        return False
    if (urllib.parse.urlsplit(address).hostname or "") in LOOPBACK_HOSTS:
        return False
    return not any(pattern.search(address) for pattern in excluded)


def _finding(path, line, target, answer):
    """The finding for one link given its address's answer, or None."""
    status = answer.status

    def report(severity, message, fix=None):
        return Finding(CHECK, severity, path, line, message, fix)

    if status is None:
        return report(
            Severity.ERROR, f"Link '{target}' could not be reached: {answer.error}."
        )
    words = f"{status} {_phrase(status)}".strip()
    if status in GONE:
        return report(
            Severity.ERROR, f"Link '{target}' is dead: the server answers {words}."
        )
    if status >= SERVER_ERROR:
        return report(
            Severity.ERROR,
            f"Link '{target}' fails: the server answers {words}, a problem on its "
            "side that is sometimes temporary.",
        )
    if status in REFUSED:
        return report(
            Severity.INFO,
            f"Link '{target}' could not be checked: the site turned the automated "
            f"check away ({words}). Open it in a browser to be sure.",
        )
    if status >= CLIENT_ERROR:
        return report(
            Severity.INFO,
            f"Link '{target}' got an unexpected answer ({words}). Open it in a "
            "browser to be sure.",
        )
    moved_to = answer.moved_to
    if moved_to is None or _same_place(target.partition("#")[0], moved_to):
        return None
    fragment = target.partition("#")[2]
    after = f"{moved_to}#{fragment}" if fragment and "#" not in moved_to else moved_to
    return report(
        Severity.INFO,
        f"Link '{target}' has moved permanently to '{moved_to}'.",
        Fix(line, target, after, Destination(path=path, line=line, url=after)),
    )


def _phrase(status):
    """The standard name of an HTTP status ("Not Found"), or ""."""
    try:
        return http.HTTPStatus(status).phrase
    except ValueError:
        return ""


def _same_place(old, new):
    """Whether a move only adds https, "www." or a trailing "/" (or drops them)."""

    def place(address):
        parts = urllib.parse.urlsplit(address)
        host = (parts.hostname or "").removeprefix("www.")
        query = f"?{parts.query}" if parts.query else ""
        return host + parts.path.rstrip("/") + query

    return place(old) == place(new)
