"""
Download and cache a course-materials repository from GitHub.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import http.client
import io
import re
import shutil
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

COURSE_REPO = "lcc-cit/CS212-CourseMaterials"
DEFAULT_BRANCH = "main"

COMMIT_API_URL = "https://api.github.com/repos/{repo}/commits/{branch}"
ARCHIVE_URL = "https://github.com/{repo}/archive/{commit}.zip"
# Accept header that makes the commit API return only the SHA
SHA_MEDIA_TYPE = "application/vnd.github.sha"
USER_AGENT = "birdwatcher"  # GitHub's API rejects requests without one
REQUEST_TIMEOUT_SECONDS = 60
LATEST_FILE = "latest"  # names the commit of the complete cached copy; written last
PARTIAL_PREFIX = ".partial-"
COMMIT_SHA = re.compile(r"[0-9a-f]{40}")

FetchBytes = Callable[[str, Mapping[str, str]], bytes]
"""Fetches a URL with the given request headers and returns the response body.

Raises OSError (urllib's URLError and HTTPError are subclasses) on failure."""


class CourseFetchError(Exception):
    """The course materials could not be obtained, or the download was unsafe."""


@dataclass(frozen=True)
class Snapshot:
    """A local copy of the course repository at one commit.

    Attributes:
        root: Folder holding the repository's files (its top level).
        commit: Full SHA of the commit the files come from.
        downloaded: True if this call downloaded the files, False if they came
            from the cache.
        stale: True if GitHub could not be reached or the new archive could not
            be downloaded, so the cached copy may be older than the repository.
    """

    root: Path
    commit: str
    downloaded: bool
    stale: bool


def http_get(url, headers):
    """
    Fetch a URL over HTTPS and return the response body.

    Args:
        url (str): The URL to fetch; redirects are followed.
        headers (Mapping[str, str]): Request headers to send.

    Returns:
        bytes: The response body.

    Raises:
        OSError: On any network or HTTP error.
    """
    request = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            return response.read()
    except http.client.HTTPException as error:
        # A dropped connection mid-body raises IncompleteRead, which is not an OSError
        raise OSError(f"HTTP error fetching {url}: {error}") from error


def ensure_materials(
    cache_dir, *, repo=COURSE_REPO, branch=DEFAULT_BRANCH, fetch=http_get
):
    """
    Return a local copy of the course repository, downloading it only when it changed.

    Asks GitHub for the latest commit on the branch. If the cache already holds
    that commit, the cached copy is returned without downloading anything.
    Otherwise the archive of exactly that commit is downloaded, extracted into
    the cache (replacing any older copy) and returned. An interrupted or failed
    download never leaves a partial copy that a later call would trust.

    When GitHub cannot be reached, or the new archive cannot be downloaded, the
    cached copy is returned with stale=True.

    Args:
        cache_dir (Path): Folder for cached copies; created if missing.
        repo (str): GitHub repository as "owner/name".
        branch (str): Branch whose latest commit is wanted.
        fetch (FetchBytes): Performs HTTP requests; replaced in tests.

    Returns:
        Snapshot: The local copy and how it was obtained.

    Raises:
        CourseFetchError: If no copy can be obtained (offline with an empty
            cache), or the archive is malformed or contains a path that would
            land outside the cache (nothing from that archive is kept).
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = _cached_copy(cache_dir)

    try:
        api_url = COMMIT_API_URL.format(repo=repo, branch=branch)
        response = fetch(api_url, {"User-Agent": USER_AGENT, "Accept": SHA_MEDIA_TYPE})
    except OSError as error:
        return _stale_or_raise(cached, error)
    latest = response.decode("ascii", errors="replace").strip()
    if not COMMIT_SHA.fullmatch(latest):
        raise CourseFetchError(
            f"GitHub returned an unexpected commit id: {latest[:80]!r}"
        )

    if cached is not None and cached[0] == latest:
        return Snapshot(root=cached[1], commit=latest, downloaded=False, stale=False)

    try:
        archive = fetch(
            ARCHIVE_URL.format(repo=repo, commit=latest), {"User-Agent": USER_AGENT}
        )
    except OSError as error:
        return _stale_or_raise(cached, error)
    root = _install(cache_dir, latest, archive)
    return Snapshot(root=root, commit=latest, downloaded=True, stale=False)


def _cached_copy(cache_dir):
    """Return (commit, root) of the complete cached copy, or None if there is none."""
    latest_file = cache_dir / LATEST_FILE
    if not latest_file.is_file():
        return None
    commit = latest_file.read_text(encoding="ascii").strip()
    if not COMMIT_SHA.fullmatch(commit):
        return None
    try:
        return commit, _top_folder(cache_dir / commit)
    except CourseFetchError:
        return None


def _stale_or_raise(cached, error):
    """Return the cached copy marked stale, or raise if there is no cached copy."""
    if cached is None:
        raise CourseFetchError(
            f"Could not download the course materials: {error}"
        ) from error
    commit, root = cached
    return Snapshot(root=root, commit=commit, downloaded=False, stale=True)


def _install(cache_dir, commit, archive):
    """Extract an archive into the cache as the copy of `commit`; return its root."""
    partial = Path(tempfile.mkdtemp(prefix=PARTIAL_PREFIX, dir=cache_dir))
    try:
        _safe_extract(archive, partial)
        _top_folder(partial)
        final = cache_dir / commit
        if final.exists():
            shutil.rmtree(final)
        partial.rename(final)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    (cache_dir / LATEST_FILE).write_text(commit, encoding="ascii")
    _remove_other_copies(cache_dir, keep=commit)
    return _top_folder(final)


def _safe_extract(archive, destination):
    """Extract a zip into destination after checking every entry stays inside it."""
    try:
        zip_file = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as error:
        raise CourseFetchError(
            f"The downloaded archive is not a valid zip: {error}"
        ) from error
    with zip_file:
        inside = destination.resolve()
        for name in zip_file.namelist():
            windows_path = PureWindowsPath(name)
            escapes = (
                PurePosixPath(name).is_absolute()
                or windows_path.is_absolute()
                or bool(windows_path.drive)
                or not (inside / name).resolve().is_relative_to(inside)
            )
            if escapes:
                raise CourseFetchError(
                    f"Archive entry would land outside the cache: {name!r}"
                )
        try:
            zip_file.extractall(destination)
        except (zipfile.BadZipFile, OSError) as error:
            raise CourseFetchError(f"Could not extract the archive: {error}") from error


def _top_folder(folder):
    """Return the single top-level folder of an extracted GitHub archive."""
    entries = list(folder.iterdir()) if folder.is_dir() else []
    if len(entries) != 1 or not entries[0].is_dir():
        raise CourseFetchError(f"Expected one top-level folder in {folder}")
    return entries[0]


def _remove_other_copies(cache_dir, keep):
    """Delete cached copies of other commits and leftovers of interrupted downloads."""
    for entry in cache_dir.iterdir():
        is_copy = COMMIT_SHA.fullmatch(entry.name) or entry.name.startswith(
            PARTIAL_PREFIX
        )
        if entry.is_dir() and is_copy and entry.name != keep:
            shutil.rmtree(entry, ignore_errors=True)
