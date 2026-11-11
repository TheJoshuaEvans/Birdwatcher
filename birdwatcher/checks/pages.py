"""
Reading the course site's Markdown pages: which pages there are, and which of
their lines are front matter, code fences, code, or prose.

Shared by the checks that read pages.

Joshua Evans, 2026-11-10 (written with Claude Opus 5.5)
"""

import re

FRONT_MATTER = re.compile(r"\A---[ \t]*\n(.*?)\n?---[ \t]*(?:\n|\Z)", re.DOTALL)
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
FRONT_KEY = re.compile(r"^([A-Za-z_][\w-]*)[ \t]*:[ \t]*(.*?)[ \t]*$")

FRONT, FENCE, CODE, TEXT = "front matter", "fence", "code", "text"  # line kinds


def site_pages(docs):
    """
    The site's Markdown pages: every .md file under docs/, except in folders
    whose names start with "_" (Jekyll's own) or "." (hidden).

    Args:
        docs (Path): The docs/ folder.

    Returns:
        list[Path]: In path order.
    """
    pages = (
        page
        for page in docs.rglob("*.md")
        if not any(
            part.startswith(("_", ".")) for part in page.relative_to(docs).parts[:-1]
        )
    )
    return sorted(pages, key=lambda page: page.relative_to(docs).as_posix())


def read_page(page):
    """
    A page's text, with Windows line endings turned into "\\n".

    Args:
        page (Path): The page.

    Returns:
        str: The text; undecodable bytes are replaced rather than raising.
    """
    return page.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def line_kinds(text):
    """
    What each line of a page is.

    Args:
        text (str): The page's text, as from read_page.

    Returns:
        list[tuple[str, str]]: (kind, line) for every line, in order. The kind
            is FRONT for the front matter block at the very top (both "---"
            lines included), FENCE for a line opening or closing a ``` or ~~~
            code block, CODE inside such a block (to the end of the page if it
            is never closed), and TEXT otherwise.
    """
    lines = text.split("\n")
    kinds = [TEXT] * len(lines)
    front = FRONT_MATTER.match(text)
    first = 0
    if front:
        first = front.group(0).rstrip("\n").count("\n") + 1
        kinds[:first] = [FRONT] * first
    fence = None
    for index in range(first, len(lines)):
        line = lines[index]
        if fence is not None:
            closing = re.match(
                rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", line
            )
            kinds[index] = FENCE if closing else CODE
            if closing:
                fence = None
            continue
        opening = FENCE_OPEN.match(line)
        if opening:
            fence = opening.group(1)
            kinds[index] = FENCE
    return list(zip(kinds, lines, strict=True))


def prose_lines(text):
    """
    A page's lines with everything but prose blanked out, so line numbers stay
    true while front matter and code are ignored.

    Args:
        text (str): The page's text.

    Returns:
        list[str]: One entry per line: the line itself for TEXT lines, "" for
            the others.
    """
    return [line if kind == TEXT else "" for kind, line in line_kinds(text)]


def front_matter(text):
    """
    The top-level keys of a page's front matter.

    Only simple "key: value" lines at the start of a line count; nested and
    list entries are ignored.

    Args:
        text (str): The page's text.

    Returns:
        dict[str, str] | None: Each key and its value as written (quotes
            kept), or None when the page has no front matter block.
    """
    match = FRONT_MATTER.match(text)
    if match is None:
        return None
    found = {}
    for line in match.group(1).split("\n"):
        key = FRONT_KEY.match(line)
        if key:
            found[key.group(1)] = key.group(2)
    return found
