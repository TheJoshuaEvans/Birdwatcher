"""
Broken section links: links to a #section that does not exist on the target page.

The course site is built by Jekyll with kramdown (GitHub-flavored input), which
gives each heading an id. Tables of contents written by other tools often expect
different ids, and nothing else checks the part after "#" (lychee does not).

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import difflib
import html
import re
import urllib.parse
from collections import Counter
from pathlib import Path

from birdwatcher.core.course import DOCS_FOLDER
from birdwatcher.core.findings import Finding, Severity

CHECK = "broken-section-link"
ALWAYS_PRESENT = frozenset({"", "top"})  # browsers scroll to the top for these
SUGGESTION_CUTOFF = 0.6  # difflib similarity needed to suggest an existing id

FRONT_MATTER = re.compile(r"\A---[ \t]*\n.*?\n---[ \t]*(?:\n|\Z)", re.DOTALL)
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
EXPLICIT_ID = re.compile(r"[ \t]*\{:?[ \t]*#([\w-]+)[^}]*\}[ \t]*$")
ID_ATTRIBUTE = re.compile(r"""\b(?:id|name)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
INLINE_CODE = re.compile(r"(`+)(.+?)\1")
INLINE_LINK = re.compile(
    r"(?<!!)\[(?:[^\[\]]|\[[^\[\]]*\])*\]"  # link text, allowing one level of brackets
    r"\(\s*<?([^\s<>()]+)>?(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)"  # target, optional title
)
REFERENCE_DEFINITION = re.compile(r"^ {0,3}\[[^\]]+\]:[ \t]*<?([^\s>]+)>?")
HREF = re.compile(r"""\bhref\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

# Reducing inline Markdown and HTML in a heading to its text
MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MARKDOWN_LINK = re.compile(r"\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])")
HTML_TAG = re.compile(r"<[^>]+>")
EMPHASIS_UNDERSCORES = re.compile(r"(?<!\w)_+|_+(?!\w)")  # not the ones inside words
BACKSLASH_ESCAPE = re.compile(r"\\(.)")
NOT_ID_CHARACTER = re.compile(r"[^\w\- \t]")


def heading_id(text):
    """
    Return the id kramdown's GFM parser gives a heading with this text.

    Inline Markdown and HTML tags are reduced to their text first. The id is that
    text lowercased, with every character that is not a letter, digit, "_", "-",
    space or tab removed, and each space or tab turned into "-". Numbering of
    repeated ids on one page is left to check_anchors.

    Args:
        text (str): The heading's Markdown source, without the leading "#"s.

    Returns:
        str: The id, e.g. "architect--planner" for "Architect & Planner".
    """
    text = INLINE_CODE.sub(lambda match: match.group(2), text)
    text = MARKDOWN_IMAGE.sub("", text)
    text = MARKDOWN_LINK.sub(r"\1", text)
    text = HTML_TAG.sub("", text)
    text = text.replace("*", "").replace("~~", "")
    text = EMPHASIS_UNDERSCORES.sub("", text)
    text = BACKSLASH_ESCAPE.sub(r"\1", html.unescape(text))
    text = NOT_ID_CHARACTER.sub("", text.lower())
    return re.sub(r"[ \t]", "-", text)


def check_anchors(repo_root, site_url):
    """
    Find links in the site's Markdown pages whose #section does not exist.

    Looks at every .md page under the repository's docs/ folder (the published
    site), outside fenced code blocks and inline code. A link counts when it
    points into the site: "#id" on the same page, a relative path to a .md or
    .html page or to a folder (its index page, or its README.md when it has no
    index), or a full address starting with site_url (when site_url is
    given; otherwise full addresses are left alone). A section exists when
    a heading has that id (kramdown's rule, repeats numbered "-1", "-2", ...),
    or an explicit id is given by "{#id}" after a heading or by an HTML id or
    name attribute. "#top" and a bare "#" always exist. Links to pages that do
    not exist are not reported (the site's link checker covers those).

    Args:
        repo_root (Path): Root folder of the course repository.
        site_url (str | None): Published site address, as from
            core.course.published_site_url, or None when it is not known.

    Returns:
        list[Finding]: One error per broken link, at the link's line, naming the
            closest existing id when there is a close one; in file and line
            order. Empty when the repository has no docs/ folder.
    """
    repo_root = Path(repo_root).resolve()
    docs = repo_root / DOCS_FOLDER
    if not docs.is_dir():
        return []

    anchors_by_page = {}

    def anchors_of(page):
        if page not in anchors_by_page:
            anchors_by_page[page] = _page_anchors(page)
        return anchors_by_page[page]

    findings = []
    for page in _site_pages(docs):
        for line_number, target in _links(_block_lines(page)):
            resolved = _resolve(page, target, docs, site_url)
            if resolved is None:
                continue
            target_page, fragment = resolved
            anchors = anchors_of(target_page)
            if fragment in anchors:
                continue
            findings.append(
                Finding(
                    check=CHECK,
                    severity=Severity.ERROR,
                    path=page.relative_to(repo_root).as_posix(),
                    line=line_number,
                    message=_message(
                        page, target, target_page, fragment, anchors, repo_root
                    ),
                )
            )
    return sorted(findings, key=lambda finding: (finding.path, finding.line))


def _site_pages(docs):
    """Markdown pages of the site, skipping Jekyll's _folders and hidden folders."""
    pages = (
        page
        for page in docs.rglob("*.md")
        if not any(
            part.startswith(("_", ".")) for part in page.relative_to(docs).parts[:-1]
        )
    )
    return sorted(pages, key=lambda page: page.relative_to(docs).as_posix())


def _read(page):
    return page.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def _block_lines(page):
    """The page's lines with front matter and fenced code blocks blanked out."""
    text = _read(page)
    lines = text.split("\n")
    front_matter = FRONT_MATTER.match(text)
    if front_matter:
        for index in range(front_matter.group(0).count("\n")):
            lines[index] = ""
    fence = None
    for index, line in enumerate(lines):
        if fence is not None:
            closing = re.match(
                rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", line
            )
            if closing:
                fence = None
            lines[index] = ""
            continue
        opening = FENCE_OPEN.match(line)
        if opening:
            fence = opening.group(1)
            lines[index] = ""
    return lines


def _links(lines):
    """Yield (line number, target) for every link outside inline code."""
    for number, line in enumerate(lines, start=1):
        line = INLINE_CODE.sub(lambda match: " " * len(match.group(0)), line)
        for pattern in (INLINE_LINK, HREF, REFERENCE_DEFINITION):
            for match in pattern.finditer(line):
                yield number, match.group(1)


def _page_anchors(page):
    """Every id a reader can jump to on a page."""
    if page.suffix.lower() != ".md":
        return ALWAYS_PRESENT | set(ID_ATTRIBUTE.findall(_read(page)))
    anchors = set(ALWAYS_PRESENT)
    seen = Counter()
    for line in _block_lines(page):
        heading = ATX_HEADING.match(line)
        if heading and heading.group(1):
            text = heading.group(1)
            explicit = EXPLICIT_ID.search(text)
            if explicit:
                anchors.add(explicit.group(1))
            else:
                base = heading_id(text)
                repeat = seen[base]
                seen[base] += 1
                anchors.add(base if repeat == 0 else f"{base}-{repeat}")
        anchors.update(ID_ATTRIBUTE.findall(line))
    return anchors


def _resolve(page, target, docs, site_url):
    """Map a link target to (site page, fragment), or None if this check doesn't own it."""
    target = target.strip()
    if "#" not in target:
        return None
    if site_url and target.startswith(site_url):
        base, target = docs, target[len(site_url) :]
    elif URL_SCHEME.match(target) or target.startswith("/"):
        return None
    else:
        base = page.parent
    path, _, fragment = target.partition("#")
    path = urllib.parse.unquote(path.split("?")[0])
    fragment = urllib.parse.unquote(fragment)
    if not path:
        return page, fragment
    candidate = (base / path).resolve()
    if not candidate.is_relative_to(docs):
        return None
    target_page = _existing_page(candidate, wants_folder=path.endswith("/"))
    return None if target_page is None else (target_page, fragment)


def _existing_page(candidate, wants_folder):
    """The site page a resolved link path refers to, or None if there isn't one."""
    if wants_folder or candidate.is_dir():
        # GitHub Pages publishes README.md as the folder's index when there is none
        options = [
            candidate / "index.md",
            candidate / "index.html",
            candidate / "README.md",
        ]
    elif candidate.suffix.lower() == ".html":
        options = [candidate.with_suffix(".md"), candidate]  # the .md is the source
    elif candidate.suffix.lower() == ".md":
        options = [candidate]
    elif not candidate.suffix:
        options = [candidate.with_suffix(".md"), candidate.with_suffix(".html")]
    else:
        return None  # PDFs, images and the like have no sections to check
    return next((option for option in options if option.is_file()), None)


def _message(page, target, target_page, fragment, anchors, repo_root):
    """Describe a broken link, suggesting the closest existing id."""
    where = (
        "on this page"
        if target_page == page
        else f"in {target_page.relative_to(repo_root).as_posix()}"
    )
    message = f"Section link '{target}' has no matching section {where}."
    candidates = sorted(anchors - ALWAYS_PRESENT)
    close = difflib.get_close_matches(
        fragment, candidates, n=1, cutoff=SUGGESTION_CUTOFF
    )
    if close:
        message += f" Did you mean '#{close[0]}'?"
    return message
