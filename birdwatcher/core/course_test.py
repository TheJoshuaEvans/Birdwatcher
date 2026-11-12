"""
Contract tests for birdwatcher.core.course.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.core.check import Check
from birdwatcher.core.course import (
    check_course,
    course_problem,
    github_repo,
    published_site_url,
    site_folder,
)
from birdwatcher.core.findings import Finding, Severity

SITE = "https://lcc-cit.github.io/CS212-CourseMaterials/"


def make_course(root, page="# Title\n"):
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "Page.md").write_text(page, encoding="utf-8")
    return root


def add_remote(root, url, name="origin"):
    git = root / ".git"
    git.mkdir()
    (git / "config").write_text(
        "[core]\n\trepositoryformatversion = 0\n"
        f'[remote "{name}"]\n\turl = {url}\n'
        f"\tfetch = +refs/heads/*:refs/remotes/{name}/*\n",
        encoding="utf-8",
    )


def test_a_folder_with_docs_can_be_used(tmp_path):
    assert course_problem(make_course(tmp_path)) is None


def test_a_missing_folder_cannot_be_used(tmp_path):
    problem = course_problem(tmp_path / "nowhere")
    assert problem and "nowhere" in problem


def test_a_file_cannot_be_used(tmp_path):
    file = tmp_path / "notes.txt"
    file.write_text("x", encoding="utf-8")
    assert course_problem(file)


def test_a_folder_without_pages_cannot_be_used(tmp_path):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    problem = course_problem(tmp_path)
    assert problem and "Markdown" in problem


def test_a_course_published_from_its_top_folder_can_be_used(tmp_path):
    (tmp_path / "Labs").mkdir()
    (tmp_path / "Labs" / "Lab01.md").write_text("# Lab 1\n", encoding="utf-8")
    assert course_problem(tmp_path) is None


def test_the_site_folder_is_docs_when_there_is_one(tmp_path):
    assert site_folder(make_course(tmp_path)) == tmp_path / "docs"


def test_the_site_folder_is_the_course_folder_without_docs(tmp_path):
    (tmp_path / "Page.md").write_text("# Page\n", encoding="utf-8")
    assert site_folder(tmp_path) == tmp_path


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/lcc-cit/CS212-CourseMaterials.git",
        "https://github.com/lcc-cit/CS212-CourseMaterials",
        "git@github.com:lcc-cit/CS212-CourseMaterials.git",
        "ssh://git@github.com/lcc-cit/CS212-CourseMaterials.git",
    ],
    ids=["https-git", "https", "scp-ssh", "ssh-url"],
)
def test_github_repo_reads_the_origin_remote(tmp_path, url):
    add_remote(tmp_path, url)
    assert github_repo(tmp_path) == "lcc-cit/CS212-CourseMaterials"


def test_github_repo_follows_a_submodule_git_file(tmp_path):
    parent_git = tmp_path / ".git" / "modules" / "course"
    parent_git.mkdir(parents=True)
    (parent_git / "config").write_text(
        '[remote "origin"]\n\turl = https://github.com/lcc-cit/CS212-CourseMaterials\n',
        encoding="utf-8",
    )
    course = tmp_path / "course"
    course.mkdir()
    (course / ".git").write_text("gitdir: ../.git/modules/course\n", encoding="utf-8")
    assert github_repo(course) == "lcc-cit/CS212-CourseMaterials"


def test_github_repo_is_none_without_a_git_folder(tmp_path):
    assert github_repo(tmp_path) is None


def test_github_repo_is_none_for_other_hosts(tmp_path):
    add_remote(tmp_path, "https://gitlab.com/someone/course.git")
    assert github_repo(tmp_path) is None


def test_github_repo_is_none_without_an_origin(tmp_path):
    add_remote(
        tmp_path, "https://github.com/lcc-cit/CS212-CourseMaterials.git", "upstream"
    )
    assert github_repo(tmp_path) is None


def test_published_site_url():
    assert published_site_url("lcc-cit/CS212-CourseMaterials") == SITE


def recording_check(seen):
    """A check that records the context it is given and finds one problem."""

    def run(context):
        seen.append(context)
        return [Finding("rec", Severity.INFO, "docs/Page.md", 1, "seen")]

    return Check(id="rec", title="Recorder", description="d", run=run)


def test_check_course_runs_the_checks_over_the_folder(tmp_path):
    course = make_course(tmp_path)
    seen = []
    run = check_course(course, [recording_check(seen)])
    assert run.course_dir == course
    assert [context.root for context in seen] == [course]
    assert len(run.findings) == 1


def test_checks_get_the_site_url_when_origin_is_on_github(tmp_path):
    course = make_course(tmp_path)
    add_remote(course, "https://github.com/lcc-cit/CS212-CourseMaterials.git")
    seen = []
    check_course(course, [recording_check(seen)])
    assert seen[0].site_url == SITE


def test_checks_get_no_site_url_without_a_github_origin(tmp_path):
    course = make_course(tmp_path)
    seen = []
    check_course(course, [recording_check(seen)])
    assert seen[0].site_url is None


def test_check_course_passes_on_the_link_look_up(tmp_path):
    course = make_course(tmp_path)
    seen = []

    def look_up(urls, report_progress):
        return {}

    check_course(course, [recording_check(seen)], look_up_links=look_up)
    assert seen[0].look_up_links is look_up


def test_check_course_can_be_stopped(tmp_path):
    course = make_course(tmp_path)
    seen = []
    run = check_course(course, [recording_check(seen)], should_stop=lambda: True)
    assert run.stopped is True
    assert seen == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
