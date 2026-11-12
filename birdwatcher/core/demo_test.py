"""
Contract tests for birdwatcher.core.demo, with a fake download.

Joshua Evans, 2026-11-12 (written with Claude Opus 5.5)
"""

import io
import re
import sys
import zipfile

import pytest

from birdwatcher.core.course import github_repo
from birdwatcher.core.demo import DEMO_REPO, DEMO_URL, DemoCourse, DemoError
from birdwatcher.core.dictionary import course_words


def archive(files):
    """A zip archive holding files ({name: text}) as GitHub's zipball does:
    under one top folder."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name, text in files.items():
            zipped.writestr(f"CS212-CourseMaterials-main/{name}", text)
    return buffer.getvalue()


class FakeFetch:
    """Returns `data` (or raises it) and records the addresses asked for."""

    def __init__(self, data):
        self.data = data
        self.urls = []

    def __call__(self, url, report_progress):
        self.urls.append(url)
        if isinstance(self.data, Exception):
            raise self.data
        report_progress(len(self.data) // 2, len(self.data))
        report_progress(len(self.data), len(self.data))
        return self.data


def test_downloading_unpacks_the_course_and_names_its_repository(tmp_path):
    fetch = FakeFetch(archive({"docs/Page.md": "# Page\n", "README.md": "hi\n"}))
    demo = DemoCourse(tmp_path, fetch)
    assert not demo.ready()
    folder = demo.download()
    assert folder == demo.folder
    assert (folder / "docs" / "Page.md").read_text(encoding="utf-8") == "# Page\n"
    assert demo.ready()
    assert fetch.urls == [DEMO_URL]
    assert github_repo(folder) == DEMO_REPO


def test_the_demo_is_pinned_to_one_commit_of_the_course():
    # A branch would follow the instructor's fixes; a commit keeps the
    # demo's findings to show.
    assert re.search(r"/zip/[0-9a-f]{40}$", DEMO_URL)


def test_the_demo_comes_with_the_course_s_word_list(tmp_path):
    folder = DemoCourse(tmp_path, FakeFetch(archive({"docs/A.md": "x"}))).download()
    words = course_words(folder)
    assert {"goodfellow", "stylometry", "pnames"} <= words


def test_progress_is_passed_on(tmp_path):
    reports = []
    DemoCourse(tmp_path, FakeFetch(archive({"docs/A.md": "x"}))).download(
        lambda done, total: reports.append((done, total))
    )
    assert reports and reports[-1][0] == reports[-1][1]


def test_downloading_again_replaces_the_old_copy(tmp_path):
    DemoCourse(tmp_path, FakeFetch(archive({"docs/Old.md": "x"}))).download()
    demo = DemoCourse(tmp_path, FakeFetch(archive({"docs/New.md": "y"})))
    folder = demo.download()
    assert (folder / "docs" / "New.md").exists()
    assert not (folder / "docs" / "Old.md").exists()


@pytest.mark.parametrize(
    "data",
    [OSError("no network"), b"not a zip archive"],
    ids=["download-fails", "not-a-zip"],
)
def test_a_failed_download_leaves_the_old_copy(tmp_path, data):
    DemoCourse(tmp_path, FakeFetch(archive({"docs/Old.md": "x"}))).download()
    demo = DemoCourse(tmp_path, FakeFetch(data))
    with pytest.raises(DemoError):
        demo.download()
    assert (demo.folder / "docs" / "Old.md").exists()


def test_a_path_leading_outside_the_folder_is_refused(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        zipped.writestr("CS212-CourseMaterials-main/docs/A.md", "x")
        zipped.writestr("CS212-CourseMaterials-main/../../escaped.txt", "x")
    demo = DemoCourse(tmp_path / "cache", FakeFetch(buffer.getvalue()))
    with pytest.raises(DemoError):
        demo.download()
    assert not list(tmp_path.rglob("escaped.txt"))
    assert not demo.ready()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
