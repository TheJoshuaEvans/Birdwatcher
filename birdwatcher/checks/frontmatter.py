"""
Incomplete front matter: published pages without a title, description or
author in their YAML front matter.

The site uses a page's title for its breadcrumb and browser tab; the
description and author are what readers and search engines see.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

from pathlib import Path

from birdwatcher.checks.pages import front_matter, read_page, site_pages
from birdwatcher.core.course import DOCS_FOLDER
from birdwatcher.core.findings import Finding, Severity

CHECK = "incomplete-front-matter"
REQUIRED_KEYS = ("title", "description", "author")
README = "readme.md"  # GitHub Pages does not publish these as pages


def check_front_matter(repo_root):
    """
    Find published pages whose front matter lacks a required key.

    Looks at every site page under docs/ (see pages.site_pages) except
    README.md files, which GitHub Pages does not publish as pages. A key with
    an empty value counts as missing.

    Args:
        repo_root (Path): Root folder of the course repository.

    Returns:
        list[Finding]: One info finding per incomplete page, about the whole
            file (no line), in path order, naming the missing keys (or saying
            the page has no front matter at all); no fix (each needs real
            words). Empty when the repository has no docs/ folder.
    """
    repo_root = Path(repo_root).resolve()
    docs = repo_root / DOCS_FOLDER
    if not docs.is_dir():
        return []
    findings = []
    for page in site_pages(docs):
        if page.name.lower() == README:
            continue
        keys = front_matter(read_page(page))
        if keys is None:
            message = (
                "This page has no front matter, so it has no title (the site's "
                "breadcrumb and browser tab use it), description or author."
            )
        else:
            missing = [key for key in REQUIRED_KEYS if not _value(keys.get(key))]
            if not missing:
                continue
            message = f"The page's front matter is missing: {', '.join(missing)}."
        findings.append(
            Finding(
                check=CHECK,
                severity=Severity.INFO,
                path=page.relative_to(repo_root).as_posix(),
                line=None,
                message=message,
            )
        )
    return findings


def _value(raw):
    """A front matter value without its quotes; "" when missing or empty."""
    return "" if raw is None else raw.strip().strip("\"'").strip()
