"""
Skipped heading levels: a heading more than one level below the heading before
it (an h2 followed by an h4).

Screen readers let readers move through a page by its headings; a skipped
level makes the outline look as if a section is missing.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import re
from pathlib import Path

from birdwatcher.checks.pages import prose_lines, read_page, site_pages
from birdwatcher.core.course import DOCS_FOLDER
from birdwatcher.core.findings import Finding, Fix, Severity

CHECK = "skipped-heading-level"
MARKDOWN_HEADING = re.compile(r"^ {0,3}(#{1,6}) ")
HTML_HEADING = re.compile(r"^\s*<h([1-6])\b", re.IGNORECASE)


def check_headings(repo_root):
    """
    Find headings that skip a level.

    Looks at every site page under docs/ (see pages.site_pages), outside front
    matter and code. Markdown headings ("#" to "######" followed by a space)
    and HTML headings (a line starting with "<h1>" to "<h6>") count alike, in
    page order. The first heading on a page is never reported.

    Args:
        repo_root (Path): Root folder of the course repository.

    Returns:
        list[Finding]: A warning per heading whose level is more than one
            below the previous heading's, at its line, in path and line order.
            A Markdown heading's finding carries a Fix that changes its "#"s to
            one level below the previous heading; an HTML heading's has no
            fix. Empty when the repository has no docs/ folder.
    """
    repo_root = Path(repo_root).resolve()
    docs = repo_root / DOCS_FOLDER
    if not docs.is_dir():
        return []
    findings = []
    for page in site_pages(docs):
        previous = None
        for number, line in enumerate(prose_lines(read_page(page)), start=1):
            markdown = MARKDOWN_HEADING.match(line)
            html = HTML_HEADING.match(line)
            if not (markdown or html):
                continue
            level = len(markdown.group(1)) if markdown else int(html.group(1))
            if previous is not None and level > previous + 1:
                findings.append(
                    _skip(page, repo_root, number, previous, level, markdown)
                )
            previous = level
    return findings


def _skip(page, repo_root, number, previous, level, markdown):
    fix = None
    if markdown:
        marker = markdown.group(1) + " "
        fix = Fix(line=number, before=marker, after="#" * (previous + 1) + " ")
    return Finding(
        check=CHECK,
        severity=Severity.WARNING,
        path=page.relative_to(repo_root).as_posix(),
        line=number,
        message=(
            f"This heading is level {level}, but the heading before it is level "
            f"{previous}, so level {previous + 1} is skipped. Screen readers move "
            "through a page by its headings, and a skipped level makes it look as "
            "if a section is missing."
        ),
        fix=fix,
    )
