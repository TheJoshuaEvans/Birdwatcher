"""
Contract tests for birdwatcher.course.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import sys

import pytest

from birdwatcher.course import check_course, course_problem, github_repo

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


def test_a_folder_without_docs_cannot_be_used(tmp_path):
    problem = course_problem(tmp_path)
    assert problem and "docs" in problem


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


def test_check_course_reports_broken_section_links(tmp_path):
    course = make_course(tmp_path, "[Jump](#nowhere)\n")
    run = check_course(course)
    assert run.course_dir == course
    assert [finding.line for finding in run.findings] == [1]


def test_full_site_links_are_checked_when_origin_is_on_github(tmp_path):
    course = make_course(tmp_path, f"[Jump]({SITE}Page.html#nowhere)\n")
    add_remote(course, "https://github.com/lcc-cit/CS212-CourseMaterials.git")
    assert len(check_course(course).findings) == 1


def test_full_site_links_are_ignored_without_a_github_origin(tmp_path):
    course = make_course(tmp_path, f"[Jump]({SITE}Page.html#nowhere)\n")
    assert check_course(course).findings == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
