"""
The course being watched: a local clone of the course repository.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import re
from pathlib import Path

from birdwatcher.core.run import run_checks

DOCS_FOLDER = "docs"  # where a course publishes its site from, when it has one
REPO_MARKER = ".birdwatcher-repo"  # names the GitHub repository of a copy without git
ORIGIN_SECTION = '[remote "origin"]'
GITDIR_PREFIX = "gitdir:"
GITHUB_REMOTE = re.compile(
    r"^(?:https://(?:[^@/]+@)?|ssh://git@|git@)github\.com[/:]"
    r"(?P<owner>[^/]+)/(?P<name>[^/]+?)(?:\.git)?/?$"
)


def site_folder(course_dir):
    """
    The folder a course's site is published from.

    Args:
        course_dir (Path): The course folder.

    Returns:
        Path: Its docs/ folder when it has one (GitHub Pages' "/docs"
            option), otherwise the course folder itself (the "/" option).
    """
    docs = Path(course_dir) / DOCS_FOLDER
    return docs if docs.is_dir() else Path(course_dir)


def course_problem(path):
    """
    Say why a folder cannot be used as the course, if it can't.

    Args:
        path (Path | str): The folder to check. "~" is not expanded.

    Returns:
        str | None: A sentence explaining the problem (no folder there, or
            no Markdown pages in its site folder, see site_folder), or None
            when the folder can be used.
    """
    path = Path(path)
    if not path.exists():
        return f"There is no folder at {path}."
    if not path.is_dir():
        return f"{path} is a file, not a folder."
    if next(site_folder(path).rglob("*.md"), None) is None:
        return (
            f"{path} has no Markdown pages (in {DOCS_FOLDER}/ or anywhere else), "
            "so it does not look like a course repository."
        )
    return None


def github_repo(course_dir):
    """
    The GitHub repository a local clone came from, read from the "origin"
    remote in its git config (git itself is not needed). Submodules and
    worktrees, whose .git is a file pointing elsewhere, are followed.

    Args:
        course_dir (Path): The clone's root folder.

    Returns:
        str | None: "owner/name" when origin is a github.com address (HTTPS or
            SSH, with or without ".git"); None when there is no git folder, no
            origin remote, or origin is not on GitHub. A copy without git (the
            demo course) can name its repository in a REPO_MARKER file instead.
    """
    try:
        text = (_git_dir(Path(course_dir)) / "config").read_text(encoding="utf-8")
    except OSError:
        try:
            marked = (Path(course_dir) / REPO_MARKER).read_text(encoding="utf-8")
        except OSError:
            return None
        return marked.strip() or None
    section = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("["):
            section = line
            continue
        key, _, value = line.partition("=")
        if section == ORIGIN_SECTION and key.strip() == "url":
            match = GITHUB_REMOTE.match(value.strip().strip('"'))
            return f"{match['owner']}/{match['name']}" if match else None
    return None


def _git_dir(course_dir):
    """The clone's git folder: .git itself, or where a .git file points (as in
    submodules and worktrees: "gitdir: <path>", relative to the clone)."""
    dot_git = course_dir / ".git"
    if dot_git.is_file():
        first_line = dot_git.read_text(encoding="utf-8").splitlines()[0]
        if first_line.startswith(GITDIR_PREFIX):
            return course_dir / first_line[len(GITDIR_PREFIX) :].strip()
    return dot_git


def published_site_url(repo):
    """
    Return the GitHub Pages address of a repository's published site.

    Args:
        repo (str): GitHub repository as "owner/name".

    Returns:
        str: "https://owner.github.io/name/", with the trailing slash.
    """
    owner, name = repo.split("/")
    return f"https://{owner.lower()}.github.io/{name}/"


def check_course(
    course_dir, checks, on_event=None, should_stop=None, look_up_links=None
):
    """
    Run checks over a local clone of the course.

    Each check's context carries the course's published site address when the
    clone's origin is on GitHub (see published_site_url), and None otherwise.

    Args:
        course_dir (Path): The clone's root folder.
        checks (Sequence[Check]): The checks to run, in order (usually
            checks.ALL_CHECKS).
        on_event (Callable[[CheckStarted | CheckProgress | CheckFinished],
            object] | None): Receives progress events.
        should_stop (Callable[[], bool] | None): Stops the run once it returns
            True (see run.run_checks).
        look_up_links (Callable | None): How checks ask web servers about
            addresses (see run.run_checks); None keeps them off the network.

    Returns:
        RunResult: The results.
    """
    repo = github_repo(course_dir)
    site_url = published_site_url(repo) if repo else None
    return run_checks(
        course_dir,
        checks,
        site_url=site_url,
        on_event=on_event,
        should_stop=should_stop,
        look_up_links=look_up_links,
    )
