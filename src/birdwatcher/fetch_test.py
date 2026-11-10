"""
Contract tests for birdwatcher.fetch. GitHub is replaced by an in-memory fake.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import io
import sys
import zipfile

import pytest

from birdwatcher.fetch import CourseFetchError, ensure_materials

SHA_1 = "1" * 40
SHA_2 = "2" * 40


def make_archive(sha, files):
    """Build a GitHub-style zip: every file under a "<repo>-<sha>/" top folder."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(f"CS212-CourseMaterials-{sha}/{name}", text)
    return buffer.getvalue()


class FakeGitHub:
    """Serves a latest-commit SHA and archives; records archive downloads.

    Set `latest` to None to make the commit lookup fail (offline), and
    `archive_fails` to make archive downloads fail.
    """

    def __init__(self, latest, archives):
        self.latest = latest
        self.archives = archives
        self.archive_fails = False
        self.archive_requests = 0

    def fetch(self, url, headers):
        if "api.github.com" in url:
            if self.latest is None:
                raise OSError("offline")
            return self.latest.encode()
        self.archive_requests += 1
        if self.archive_fails:
            raise OSError("download interrupted")
        sha = next(s for s in self.archives if s in url)
        return self.archives[sha]


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "cache"


def test_first_call_downloads_the_latest_commit(cache_dir):
    github = FakeGitHub(SHA_1, {SHA_1: make_archive(SHA_1, {"docs/a.md": "v1"})})

    snapshot = ensure_materials(cache_dir, fetch=github.fetch)

    assert snapshot.commit == SHA_1
    assert snapshot.downloaded
    assert not snapshot.stale
    assert (snapshot.root / "docs" / "a.md").read_text() == "v1"


def test_unchanged_commit_is_served_from_the_cache(cache_dir):
    github = FakeGitHub(SHA_1, {SHA_1: make_archive(SHA_1, {"docs/a.md": "v1"})})
    ensure_materials(cache_dir, fetch=github.fetch)

    snapshot = ensure_materials(cache_dir, fetch=github.fetch)

    assert github.archive_requests == 1
    assert not snapshot.downloaded
    assert not snapshot.stale
    assert (snapshot.root / "docs" / "a.md").read_text() == "v1"


def test_new_commit_is_downloaded(cache_dir):
    github = FakeGitHub(
        SHA_1,
        {
            SHA_1: make_archive(SHA_1, {"docs/a.md": "v1"}),
            SHA_2: make_archive(SHA_2, {"docs/a.md": "v2"}),
        },
    )
    ensure_materials(cache_dir, fetch=github.fetch)
    github.latest = SHA_2

    snapshot = ensure_materials(cache_dir, fetch=github.fetch)

    assert snapshot.commit == SHA_2
    assert snapshot.downloaded
    assert (snapshot.root / "docs" / "a.md").read_text() == "v2"


def test_offline_with_a_cache_returns_the_cached_copy_as_stale(cache_dir):
    github = FakeGitHub(SHA_1, {SHA_1: make_archive(SHA_1, {"docs/a.md": "v1"})})
    ensure_materials(cache_dir, fetch=github.fetch)
    github.latest = None

    snapshot = ensure_materials(cache_dir, fetch=github.fetch)

    assert snapshot.stale
    assert snapshot.commit == SHA_1
    assert (snapshot.root / "docs" / "a.md").read_text() == "v1"


def test_offline_with_an_empty_cache_raises(cache_dir):
    github = FakeGitHub(None, {})

    with pytest.raises(CourseFetchError):
        ensure_materials(cache_dir, fetch=github.fetch)


def test_failed_download_of_a_new_commit_keeps_the_old_copy(cache_dir):
    github = FakeGitHub(SHA_1, {SHA_1: make_archive(SHA_1, {"docs/a.md": "v1"})})
    ensure_materials(cache_dir, fetch=github.fetch)
    github.latest = SHA_2
    github.archive_fails = True

    snapshot = ensure_materials(cache_dir, fetch=github.fetch)

    assert snapshot.stale
    assert snapshot.commit == SHA_1
    assert (snapshot.root / "docs" / "a.md").read_text() == "v1"


def test_failed_first_download_leaves_nothing_a_later_call_trusts(cache_dir):
    github = FakeGitHub(SHA_1, {SHA_1: make_archive(SHA_1, {"docs/a.md": "v1"})})
    github.archive_fails = True
    with pytest.raises(CourseFetchError):
        ensure_materials(cache_dir, fetch=github.fetch)
    github.archive_fails = False

    snapshot = ensure_materials(cache_dir, fetch=github.fetch)

    assert snapshot.downloaded
    assert (snapshot.root / "docs" / "a.md").read_text() == "v1"


@pytest.mark.parametrize(
    "evil_name",
    ["../../evil.txt", "/evil.txt", "C:/evil.txt"],
    ids=["parent-traversal", "absolute-posix", "absolute-windows"],
)
def test_archive_escaping_the_cache_is_rejected(tmp_path, cache_dir, evil_name):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"CS212-CourseMaterials-{SHA_1}/docs/a.md", "v1")
        archive.writestr(evil_name, "gotcha")
    github = FakeGitHub(SHA_1, {SHA_1: buffer.getvalue()})

    with pytest.raises(CourseFetchError):
        ensure_materials(cache_dir, fetch=github.fetch)

    assert not (tmp_path / "evil.txt").exists()
    assert not list(tmp_path.rglob("evil.txt"))


def test_malformed_archive_is_rejected(cache_dir):
    github = FakeGitHub(SHA_1, {SHA_1: b"this is not a zip"})

    with pytest.raises(CourseFetchError):
        ensure_materials(cache_dir, fetch=github.fetch)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
