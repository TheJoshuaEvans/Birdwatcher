"""
The demo course: a downloaded copy of the CS 212 course materials as they were
at one commit (DEMO_COMMIT), for trying Birdwatcher without cloning a
repository. It lives in Birdwatcher's cache
folder, apart from real courses.

Joshua Evans, 2026-11-12 (written with Claude Opus 5.5)
"""

import io
import shutil
import urllib.request
import zipfile
from importlib.resources import files
from pathlib import Path

from birdwatcher.core.course import REPO_MARKER

DEMO_REPO = "lcc-cit/CS212-CourseMaterials"
# Pinned to one commit (2026-11-11), not a branch: as the instructor fixes
# what Birdwatcher finds, the demo still has findings to show.
DEMO_COMMIT = "8e93b0a13b654808ee311748a280096d8ed2db77"
DEMO_URL = f"https://codeload.github.com/{DEMO_REPO}/zip/{DEMO_COMMIT}"
DEMO_FOLDER = "CS212-CourseMaterials"
USER_AGENT = "Birdwatcher demo download"
CHUNK = 256 * 1024  # bytes read between progress reports
# The course's own words (names, its terms), as its instructor's clone keeps
# them, so the demo's spelling findings match real use
DEMO_WORDS = "demo-cspell.json"


class DemoError(Exception):
    """The demo could not be downloaded or unpacked; the message says why."""


def fetch_url(url, report_progress):
    """
    Download a file.

    Args:
        url (str): The address.
        report_progress (Callable[[int, int | None], object]): Called as the
            download goes, with the bytes so far and the total (None when the
            server does not say).

    Returns:
        bytes: The file.

    Raises:
        OSError: The download failed.
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        length = response.headers.get("Content-Length")
        total = int(length) if length and length.isdigit() else None
        data = bytearray()
        while chunk := response.read(CHUNK):
            data += chunk
            report_progress(len(data), total)
        return bytes(data)


class DemoCourse:
    """
    The demo course's copy.

    Args:
        cache_dir (Path): Birdwatcher's cache folder; the copy lives in
            cache_dir/demo/DEMO_FOLDER.
        fetch (Callable[[str, Callable], bytes]): Downloads a file, as
            fetch_url does.
    """

    def __init__(self, cache_dir, fetch=fetch_url):
        self.folder = Path(cache_dir) / "demo" / DEMO_FOLDER
        self._fetch = fetch

    def ready(self):
        """
        Whether a copy has been downloaded.

        Returns:
            bool: True when the folder holds a downloaded copy.
        """
        return (self.folder / REPO_MARKER).is_file()

    def download(self, report_progress=lambda done, total: None):
        """
        Download the course from DEMO_URL and put it in self.folder, in place
        of any earlier copy. The archive's single top folder becomes the
        course folder, a REPO_MARKER file names DEMO_REPO so the course's
        published site is known, and the course's word list (DEMO_WORDS)
        becomes its cspell.json. The earlier copy is only replaced once the
        new one is complete; a failure leaves it as it was.

        Args:
            report_progress (Callable[[int, int | None], object]): Passed to
                fetch.

        Returns:
            Path: self.folder.

        Raises:
            DemoError: The download failed, the file is not a zip archive, or
                it holds a path that would land outside the folder.
        """
        try:
            data = self._fetch(DEMO_URL, report_progress)
        except OSError as error:
            raise DemoError(
                f"The demo course could not be downloaded: {error}"
            ) from error
        incoming = self.folder.with_name(self.folder.name + ".incoming")
        shutil.rmtree(incoming, ignore_errors=True)
        try:
            _unpack(data, incoming)
            (incoming / REPO_MARKER).write_text(DEMO_REPO + "\n", encoding="utf-8")
            words = files("birdwatcher.core").joinpath(DEMO_WORDS)
            (incoming / "cspell.json").write_text(
                words.read_text(encoding="utf-8"), encoding="utf-8"
            )
        except DemoError:
            shutil.rmtree(incoming, ignore_errors=True)
            raise
        shutil.rmtree(self.folder, ignore_errors=True)
        incoming.rename(self.folder)
        return self.folder


def _unpack(data, target):
    """Unpack a zip archive's single top folder into target, refusing any
    entry whose path would land outside it."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise DemoError("The demo download is not a zip archive.") from error
    with archive:
        root = target.resolve()
        for entry in archive.infolist():
            # Drop the archive's top folder ("CS212-CourseMaterials-main/").
            _, _, inside = entry.filename.partition("/")
            if not inside:
                continue
            destination = (target / inside).resolve()
            if not destination.is_relative_to(root):
                raise DemoError(
                    f"The demo download holds an unsafe path: {entry.filename}"
                )
            if entry.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(entry))
