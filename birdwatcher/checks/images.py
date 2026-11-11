"""
Images without alt text, which screen readers cannot describe.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import re
from pathlib import Path

from birdwatcher.checks.pages import prose_lines, read_page, site_pages
from birdwatcher.core.course import DOCS_FOLDER
from birdwatcher.core.findings import Finding, Severity

CHECK = "missing-alt-text"
MARKDOWN_IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^\s<>()]+)")
HTML_IMAGE = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)
ALT_ATTRIBUTE = re.compile(r"\balt\s*=", re.IGNORECASE)
SOURCE_ATTRIBUTE = re.compile(r"""\bsrc\s*=\s*(["'])(.*?)\1""", re.IGNORECASE)


def check_images(repo_root):
    """
    Find images that have no alternative text.

    Looks at every site page under docs/ (see pages.site_pages), outside front
    matter and code. A Markdown image counts when its brackets are empty or
    blank ("![](chart.png)"); an HTML <img> counts when it has no alt
    attribute at all. An HTML alt="" is not reported: it is the standard way
    to mark an image as decorative.

    Args:
        repo_root (Path): Root folder of the course repository.

    Returns:
        list[Finding]: A warning per image, at its line, in path and line
            order, naming the image's source; no fix (only a person can
            describe an image). Empty when the repository has no docs/ folder.
    """
    repo_root = Path(repo_root).resolve()
    docs = repo_root / DOCS_FOLDER
    if not docs.is_dir():
        return []
    findings = []
    for page in site_pages(docs):
        path = page.relative_to(repo_root).as_posix()
        for number, line in enumerate(prose_lines(read_page(page)), start=1):
            for source in _images_without_alt(line):
                findings.append(
                    Finding(
                        check=CHECK,
                        severity=Severity.WARNING,
                        path=path,
                        line=number,
                        message=(
                            f"The image {source} has no alt text, so screen readers "
                            "cannot describe it, and readers see nothing if it fails "
                            "to load. Describe what it shows; for a purely decorative "
                            'image, use HTML with alt="".'
                        ),
                    )
                )
    return findings


def _images_without_alt(line):
    """The sources of a line's images that lack alt text, in line order."""
    found = []
    for match in MARKDOWN_IMAGE.finditer(line):
        if not match.group(1).strip():
            found.append((match.start(), match.group(2)))
    for match in HTML_IMAGE.finditer(line):
        attributes = match.group(1)
        if not ALT_ATTRIBUTE.search(attributes):
            source = SOURCE_ATTRIBUTE.search(attributes)
            found.append((match.start(), source.group(2) if source else "(no src)"))
    return [source for _, source in sorted(found)]
